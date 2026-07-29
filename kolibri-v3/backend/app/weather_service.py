from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from threading import RLock
from time import monotonic
from typing import Any

import httpx

from .config import Settings


class WeatherServiceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WeatherQuery:
    location: str
    forecast_days: int


_WORD = re.compile(r"[^\W_]+(?:-[^\W_]+)*", re.UNICODE)
_WEATHER_STEMS = (
    "погод",
    "температур",
    "прогноз",
    "дожд",
    "осад",
    "снег",
    "ветер",
    "зонт",
    "weather",
    "forecast",
    "temperature",
    "rain",
    "snow",
    "wind",
    "umbrella",
)
_LOCATION_PREPOSITIONS = frozenset({"в", "во", "для", "по"})
_LOCATION_STOP_WORDS = frozenset(
    {
        "а",
        "будет",
        "будут",
        "выходные",
        "выходных",
        "градусов",
        "день",
        "дней",
        "дня",
        "завтра",
        "ли",
        "на",
        "неделю",
        "неделя",
        "ночью",
        "пожалуйста",
        "послезавтра",
        "сейчас",
        "сегодня",
        "утром",
        "вечером",
        "today",
        "tomorrow",
        "week",
        "now",
    }
)
_QUERY_FILLERS = frozenset(
    {
        "какая",
        "какой",
        "какие",
        "как",
        "влияет",
        "влияние",
        "мне",
        "нужно",
        "нужен",
        "ожидается",
        "покажи",
        "скажи",
        "стоит",
        "там",
        "что",
        "what",
        "show",
        "tell",
        "is",
        "the",
    }
)


def _is_weather_word(token: str) -> bool:
    return any(token.startswith(stem) for stem in _WEATHER_STEMS)


def _forecast_days(tokens: list[str]) -> int:
    if any(token.startswith("недел") or token == "week" for token in tokens):
        return 7
    if "послезавтра" in tokens:
        return 3
    if "завтра" in tokens or "tomorrow" in tokens:
        return 2
    for index, token in enumerate(tokens[:-1]):
        if (
            token.isdigit()
            and tokens[index + 1] in {"день", "дней", "дня", "days"}
        ):
            return min(max(int(token), 1), 7)
    return 5


def _clean_location_tokens(tokens: list[str]) -> list[str]:
    result: list[str] = []
    for token in tokens:
        normalized = token.casefold()
        if (
            normalized in _LOCATION_STOP_WORDS
            or normalized in _QUERY_FILLERS
            or normalized in _LOCATION_PREPOSITIONS
            or _is_weather_word(normalized)
            or normalized.isdigit()
        ):
            if result:
                break
            continue
        result.append(token)
        if len(result) == 4:
            break
    return result


def try_parse_weather_query(prompt: str) -> WeatherQuery | None:
    """Resolve only explicit, unambiguous weather requests.

    This is a latency fast path, not a city allowlist. Ambiguous text returns
    ``None`` so the selected model can make the normal tool decision.
    """

    original_tokens = _WORD.findall(prompt)
    tokens = [token.casefold() for token in original_tokens]
    weather_indexes = [
        index for index, token in enumerate(tokens) if _is_weather_word(token)
    ]
    if not weather_indexes:
        return None
    if any(token.startswith("влия") or token == "impact" for token in tokens):
        return None

    location_tokens: list[str] = []
    for index in range(len(tokens) - 1, -1, -1):
        if tokens[index] not in _LOCATION_PREPOSITIONS:
            continue
        location_tokens = _clean_location_tokens(original_tokens[index + 1 :])
        if location_tokens:
            break

    if not location_tokens:
        weather_index = weather_indexes[-1]
        location_tokens = _clean_location_tokens(
            original_tokens[weather_index + 1 :]
        )
    if not location_tokens:
        weather_index = weather_indexes[0]
        before = _clean_location_tokens(
            list(reversed(original_tokens[:weather_index]))
        )
        location_tokens = list(reversed(before))
    if not location_tokens:
        return None

    return WeatherQuery(
        location=" ".join(location_tokens),
        forecast_days=_forecast_days(tokens),
    )


WEATHER_CONDITIONS = {
    0: "Ясно",
    1: "Преимущественно ясно",
    2: "Переменная облачность",
    3: "Пасмурно",
    45: "Туман",
    48: "Изморозь",
    51: "Небольшая морось",
    53: "Морось",
    55: "Сильная морось",
    56: "Ледяная морось",
    57: "Сильная ледяная морось",
    61: "Небольшой дождь",
    63: "Дождь",
    65: "Сильный дождь",
    66: "Ледяной дождь",
    67: "Сильный ледяной дождь",
    71: "Небольшой снег",
    73: "Снег",
    75: "Сильный снег",
    77: "Снежные зёрна",
    80: "Небольшие ливни",
    81: "Ливни",
    82: "Сильные ливни",
    85: "Небольшой снегопад",
    86: "Сильный снегопад",
    95: "Гроза",
    96: "Гроза с небольшим градом",
    99: "Гроза с сильным градом",
}

_WEATHER_CACHE_TTL_SECONDS = 5 * 60
_WEATHER_CACHE_MAX_ENTRIES = 256
_WEATHER_CACHE_LOCK = RLock()
_WEATHER_CACHE: dict[
    tuple[str, int],
    tuple[float, dict[str, Any]],
] = {}


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherServiceError("Погодный сервис вернул некорректное число.")
    return round(float(value), 1)


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherServiceError("Погодный сервис вернул некорректное число.")
    return int(value)


def _location_candidates(location: str) -> list[str]:
    """Generate bounded Russian case-form fallbacks for geocoding.

    Open-Meteo accepts many inflected names, but not all common prepositional
    forms (for example, ``Казани``). This remains city-agnostic: candidates are
    derived from the user's words and the geocoder still owns place resolution.
    """

    candidates = [location]
    words = location.split()
    if not words:
        return candidates

    last = words[-1]
    stem_candidates: list[str] = []
    folded = last.casefold()
    if len(last) >= 4 and folded.endswith("е"):
        stem = last[:-1]
        stem_candidates.extend((stem, f"{stem}а", f"{stem}я"))
    if len(last) >= 4 and folded.endswith("и"):
        stem = last[:-1]
        stem_candidates.extend((f"{stem}ь", f"{stem}я", stem))
    if len(last) >= 4 and folded.endswith("у"):
        stem = last[:-1]
        stem_candidates.extend((f"{stem}а", f"{stem}я", stem))

    for candidate_last in stem_candidates:
        candidate = " ".join((*words[:-1], candidate_last))
        if candidate.casefold() not in {
            existing.casefold() for existing in candidates
        }:
            candidates.append(candidate)
        if len(candidates) == 5:
            break
    return candidates


def get_weather(
    settings: Settings,
    *,
    location: str,
    forecast_days: int,
) -> dict[str, Any]:
    normalized_location = location.strip()
    if not normalized_location or len(normalized_location) > 160:
        raise WeatherServiceError("Укажите населённый пункт.")
    days = min(max(forecast_days, 1), 7)
    cache_key = (" ".join(normalized_location.casefold().split()), days)
    now = monotonic()
    with _WEATHER_CACHE_LOCK:
        cached = _WEATHER_CACHE.get(cache_key)
        if cached is not None:
            expires_at, result = cached
            if expires_at > now:
                return deepcopy(result)
            _WEATHER_CACHE.pop(cache_key, None)

    timeout = min(max(settings.direct_model_timeout_seconds, 5), 15)

    try:
        with httpx.Client(
            timeout=httpx.Timeout(timeout, connect=5),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            locations: object = None
            for candidate in _location_candidates(normalized_location):
                geocoding = client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={
                        "name": candidate,
                        "count": 1,
                        "language": "ru",
                        "format": "json",
                    },
                    headers={"Accept": "application/json"},
                )
                geocoding.raise_for_status()
                geocoding_payload = geocoding.json()
                locations = (
                    geocoding_payload.get("results")
                    if isinstance(geocoding_payload, dict)
                    else None
                )
                if isinstance(locations, list) and locations:
                    break
            if not isinstance(locations, list) or not locations:
                raise WeatherServiceError(
                    f"Не удалось найти населённый пункт «{normalized_location}»."
                )
            place = locations[0]
            if not isinstance(place, dict):
                raise WeatherServiceError("Погодный сервис вернул неизвестный город.")

            latitude = _number(place.get("latitude"))
            longitude = _number(place.get("longitude"))
            forecast_response = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": (
                        "temperature_2m,apparent_temperature,"
                        "relative_humidity_2m,precipitation,"
                        "weather_code,wind_speed_10m,is_day"
                    ),
                    "daily": (
                        "weather_code,temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max"
                    ),
                    "timezone": "auto",
                    "forecast_days": days,
                },
                headers={"Accept": "application/json"},
            )
            forecast_response.raise_for_status()
            forecast = forecast_response.json()
    except WeatherServiceError:
        raise
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        raise WeatherServiceError(
            "Погодный сервис сейчас недоступен. Повторите запрос."
        ) from exc

    if not isinstance(forecast, dict):
        raise WeatherServiceError("Погодный сервис вернул неизвестный ответ.")
    current = forecast.get("current")
    daily = forecast.get("daily")
    if not isinstance(current, dict) or not isinstance(daily, dict):
        raise WeatherServiceError("В ответе погодного сервиса нет прогноза.")

    dates = daily.get("time")
    codes = daily.get("weather_code")
    maximums = daily.get("temperature_2m_max")
    minimums = daily.get("temperature_2m_min")
    probabilities = daily.get("precipitation_probability_max")
    if not all(
        isinstance(value, list)
        for value in (dates, codes, maximums, minimums, probabilities)
    ):
        raise WeatherServiceError("Погодный сервис вернул неполный прогноз.")

    daily_forecast: list[dict[str, object]] = []
    for date, code, maximum, minimum, probability in zip(
        dates[:days],
        codes[:days],
        maximums[:days],
        minimums[:days],
        probabilities[:days],
        strict=False,
    ):
        if not isinstance(date, str):
            continue
        weather_code = _integer(code)
        daily_forecast.append(
            {
                "date": date,
                "condition": WEATHER_CONDITIONS.get(
                    weather_code,
                    "Погодные условия",
                ),
                "weatherCode": weather_code,
                "temperatureMax": _number(maximum),
                "temperatureMin": _number(minimum),
                "precipitationProbability": _integer(probability),
            }
        )

    weather_code = _integer(current.get("weather_code"))
    temperature = _number(current.get("temperature_2m"))
    place_name = str(place.get("name") or normalized_location)
    condition = WEATHER_CONDITIONS.get(weather_code, "Погодные условия")
    result: dict[str, Any] = {
        "$type": "WeatherWidget",
        "location": place_name,
        "region": str(place.get("admin1") or ""),
        "country": str(place.get("country") or ""),
        "timezone": str(forecast.get("timezone") or ""),
        "observedAt": str(current.get("time") or ""),
        "condition": condition,
        "summary": f"Сейчас в {place_name}: {temperature:+g} °C, {condition.lower()}.",
        "weatherCode": weather_code,
        "temperature": temperature,
        "feelsLike": _number(current.get("apparent_temperature")),
        "humidity": _integer(current.get("relative_humidity_2m")),
        "windSpeed": _number(current.get("wind_speed_10m")),
        "precipitation": _number(current.get("precipitation")),
        "isDay": bool(_integer(current.get("is_day"))),
        "forecast": daily_forecast,
        "sources": [
            {
                "label": "Open-Meteo",
                "sourceUrl": "https://open-meteo.com/",
            }
        ],
    }
    with _WEATHER_CACHE_LOCK:
        if len(_WEATHER_CACHE) >= _WEATHER_CACHE_MAX_ENTRIES:
            expired = [
                key
                for key, (expires_at, _) in _WEATHER_CACHE.items()
                if expires_at <= now
            ]
            for key in expired:
                _WEATHER_CACHE.pop(key, None)
            if len(_WEATHER_CACHE) >= _WEATHER_CACHE_MAX_ENTRIES:
                oldest_key = min(
                    _WEATHER_CACHE,
                    key=lambda key: _WEATHER_CACHE[key][0],
                )
                _WEATHER_CACHE.pop(oldest_key, None)
        _WEATHER_CACHE[cache_key] = (
            monotonic() + _WEATHER_CACHE_TTL_SECONDS,
            deepcopy(result),
        )
    return result
