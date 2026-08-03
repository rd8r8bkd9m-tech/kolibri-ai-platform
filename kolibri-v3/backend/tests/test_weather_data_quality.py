from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.weather_service import (
    WeatherServiceError,
    _normalize_observed_at,
    _select_geocoding_result,
    get_weather,
)
from app.config import Settings


@pytest.mark.parametrize("location", ["Питер", "Самар", "СПБ", "Ростов"])
def test_ambiguous_aliases_are_rejected_before_network(
    tmp_path, location: str
) -> None:
    with pytest.raises(WeatherServiceError, match="официальное название и регион"):
        get_weather(
            Settings.for_testing(database_url=tmp_path / "weather.db"),
            location=location,
            forecast_days=1,
        )


def test_ambiguous_same_name_requires_region_instead_of_selecting_first() -> None:
    with pytest.raises(WeatherServiceError, match="Уточните населённый пункт"):
        _select_geocoding_result(
            requested_location="Самара",
            candidate="Самара",
            locations=[
                {"name": "Самара", "admin1": "Самарская область", "country": "Россия"},
                {"name": "Самара", "admin1": "Карагандинская область", "country": "Казахстан"},
            ],
        )


def test_partial_geocoder_match_cannot_silently_resolve_wrong_region() -> None:
    with pytest.raises(WeatherServiceError, match="укажите регион или страну"):
        _select_geocoding_result(
            requested_location="Самар",
            candidate="Самар",
            locations=[
                {"name": "Самара", "admin1": "Самарская область", "country": "Россия"}
            ],
        )


def test_weather_observation_requires_valid_timezone_and_fresh_timestamp() -> None:
    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    assert _normalize_observed_at(
        "2026-08-01T14:55:00",
        timezone_name="Europe/Moscow",
        now=now,
    ) == "2026-08-01T14:55+03:00"

    with pytest.raises(WeatherServiceError, match="устарели"):
        _normalize_observed_at(
            (now - timedelta(hours=3)).isoformat(),
            timezone_name="UTC",
            now=now,
        )
    with pytest.raises(WeatherServiceError, match="часовой пояс"):
        _normalize_observed_at(
            now.isoformat(),
            timezone_name="Mars/Olympus",
            now=now,
        )
