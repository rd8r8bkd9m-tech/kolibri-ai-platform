from __future__ import annotations

import asyncio
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal, Mapping
from urllib.parse import urlencode, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator


FGIS_API_ORIGIN = "https://fgiscs.minstroyrf.ru"
FGIS_API_BASE = f"{FGIS_API_ORIGIN}/api"
FGIS_PUBLIC_PRICES_URL = f"{FGIS_API_ORIGIN}/prices"
FGIS_PUBLISHER = "ФАУ «Главгосэкспертиза России» / ФГИС ЦС"
PARSER_VERSION = "fgis_estimated_price_v1"
FGIS_SOURCE_POLICY_VERSION = "fgis_public_read_only_2026-07-29"
SUPPLIER_SOURCE_POLICY_VERSION = "user_attested_supplier_offer_v1"
MONEY_QUANTUM = Decimal("0.01")
PERIOD_PATTERN = re.compile(
    r"(?P<quarter>[1-4])\s*квартал[^0-9]*(?P<year>20\d{2})",
    re.IGNORECASE,
)
TOKEN_PATTERN = re.compile(r"[0-9a-zа-яё]+", re.IGNORECASE)
MAX_MATERIAL_ROWS = 12
MAX_SEARCH_ATTEMPTS_PER_ROW = 3
MAX_CONCURRENT_FGIS_REQUESTS = 3
MAX_FGIS_HTTP_ATTEMPTS = 2
MAX_FGIS_RETRY_DELAY_SECONDS = 1.0
RETRYABLE_FGIS_STATUS_CODES = frozenset({429, 502, 503, 504})

FGIS_SOURCE_POLICY: Mapping[str, Any] = {
    "version": FGIS_SOURCE_POLICY_VERSION,
    "authority": FGIS_PUBLISHER,
    "authorityInformationUrl": "https://minstroyrf.gov.ru/trades/tsenoobrazovanie/",
    "publicSurfaceUrl": FGIS_PUBLIC_PRICES_URL,
    "accessClass": "public_read_only_application_endpoint",
    "purpose": "interactive_user_requested_estimate_enrichment",
    "scheduledCrawling": False,
    "formalMachineApiTermsReview": "not_located_2026-07-29",
    "productionReleaseGate": "source_owner_or_legal_review_required",
    "limits": {
        "materialRowsPerCommand": MAX_MATERIAL_ROWS,
        "searchAttemptsPerRow": MAX_SEARCH_ATTEMPTS_PER_ROW,
        "concurrentRequests": MAX_CONCURRENT_FGIS_REQUESTS,
        "httpAttempts": MAX_FGIS_HTTP_ATTEMPTS,
        "timeoutSeconds": 12,
    },
}

SUPPLIER_SOURCE_POLICY: Mapping[str, Any] = {
    "version": SUPPLIER_SOURCE_POLICY_VERSION,
    "accessClass": "user_attested_reference",
    "purpose": "attach_supplier_offer_to_estimate",
    "sourceFetchedByKolibri": False,
    "supplierVerifiedByKolibri": False,
}

_GENERIC_TOKENS = {
    "для",
    "материал",
    "материалы",
    "монтаж",
    "поставка",
    "работа",
    "работы",
    "устройство",
    "комплект",
    "строительный",
    "строительство",
}
_RUSSIAN_ENDINGS = tuple(
    sorted(
        {
            "иями",
            "ями",
            "ами",
            "ого",
            "ему",
            "ому",
            "ими",
            "ыми",
            "ая",
            "яя",
            "ое",
            "ее",
            "ые",
            "ие",
            "ий",
            "ый",
            "ой",
            "ых",
            "их",
            "ую",
            "юю",
            "ам",
            "ям",
            "ах",
            "ях",
            "ов",
            "ев",
            "ом",
            "ем",
            "а",
            "я",
            "ы",
            "и",
            "у",
            "ю",
            "е",
            "о",
        },
        key=len,
        reverse=True,
    )
)
_ADMINISTRATIVE_WORDS = {
    "автономная",
    "автономный",
    "город",
    "значения",
    "край",
    "область",
    "округ",
    "республика",
    "федерального",
}
_UNIT_ALIASES = {
    "м2": "м2",
    "м²": "м2",
    "квм": "м2",
    "м3": "м3",
    "м³": "м3",
    "кубм": "м3",
    "шт": "шт",
    "шт.": "шт",
    "кг": "кг",
    "т": "т",
    "тонна": "т",
    "л": "л",
    "литр": "л",
    "м": "м",
    "пм": "м",
    "п.м": "м",
    "рул": "рул",
    "рулон": "рул",
    "упак": "упак",
    "упаковка": "упак",
}


class PricingSourceError(RuntimeError):
    pass


class PricingSourceUnavailable(PricingSourceError):
    pass


class PricingSourceProtocolError(PricingSourceError):
    pass


class PricingRegionUnresolved(PricingSourceError):
    pass


class SupplierOfferInput(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    version: int = Field(ge=1)
    row_id: str = Field(alias="rowId", pattern=r"^row_[A-Za-z0-9._~-]{8,96}$")
    supplier_name: str = Field(alias="supplierName", min_length=1, max_length=240)
    source_url: HttpUrl = Field(alias="sourceUrl", max_length=1_000)
    quote_reference: str = Field(
        alias="quoteReference",
        min_length=1,
        max_length=160,
    )
    observed_on: date = Field(alias="observedOn")
    valid_until: date | None = Field(default=None, alias="validUntil")
    unit_price: str = Field(
        alias="unitPrice",
        pattern=r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$",
    )
    delivery_per_unit: str = Field(
        default="0.00",
        alias="deliveryPerUnit",
        pattern=r"^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$",
    )
    vat_included: bool | None = Field(default=None, alias="vatIncluded")
    offer_kind: Literal["indicative", "binding"] = Field(
        default="indicative",
        alias="offerKind",
    )
    availability: Literal["available", "unknown", "unavailable"] = "unknown"
    lead_time_days: int | None = Field(
        default=None,
        alias="leadTimeDays",
        ge=0,
        le=3650,
    )

    @field_validator("source_url")
    @classmethod
    def reject_source_url_credentials(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlsplit(str(value))
        if parsed.username or parsed.password:
            raise ValueError("sourceUrl must not contain credentials")
        return value

    @field_validator("observed_on", "valid_until", mode="before")
    @classmethod
    def parse_iso_dates(cls, value: Any) -> Any:
        if value is None or isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return date.fromisoformat(value)
            except ValueError:
                return value
        return value

    @model_validator(mode="after")
    def validate_offer_window(self) -> "SupplierOfferInput":
        if self.valid_until is not None and self.valid_until < self.observed_on:
            raise ValueError("validUntil must not precede observedOn")
        if self.offer_kind == "binding" and self.valid_until is None:
            raise ValueError("binding offer requires validUntil")
        if Decimal(self.unit_price) <= 0:
            raise ValueError("unitPrice must be greater than zero")
        return self


class PricingRefreshInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)

    version: int = Field(ge=1)


@dataclass(frozen=True, slots=True)
class FgisContext:
    subject_id: int
    subject_name: str
    price_zone_id: int
    price_zone_name: str
    period_id: int
    period_label: str
    price_date: date
    fresh_until: date


@dataclass(frozen=True, slots=True)
class FgisCandidate:
    resource_id: int
    code: str
    name: str
    unit: str
    unit_price: Decimal
    aggregated_price: Decimal | None
    distance_price: Decimal | None
    procurement_storage_percent: Decimal | None
    score: Decimal


@dataclass(frozen=True, slots=True)
class FgisMatch:
    row_id: str
    context: FgisContext
    candidate: FgisCandidate
    source_uri: str
    fetched_at: datetime
    payload_hash: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class FgisRefreshResult:
    context: FgisContext
    matches: tuple[FgisMatch, ...]
    unmatched_row_ids: tuple[str, ...]


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()}"


def money(value: Decimal | str) -> str:
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("money value is invalid") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError("money value must be finite and non-negative")
    return format(parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def _normalize_text(value: str) -> str:
    normalized = (
        unicodedata.normalize("NFKC", value)
        .casefold()
        .replace("ё", "е")
        .replace("²", "2")
        .replace("³", "3")
    )
    return " ".join(TOKEN_PATTERN.findall(normalized))


def _stem(value: str) -> str:
    for ending in _RUSSIAN_ENDINGS:
        if len(value) >= len(ending) + 4 and value.endswith(ending):
            return value[: -len(ending)]
    return value


def _tokens(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for token in TOKEN_PATTERN.findall(_normalize_text(value)):
        if token in _GENERIC_TOKENS or (
            len(token) < 3 and not token.isdigit()
        ):
            continue
        stemmed = _stem(token)
        if stemmed not in result:
            result.append(stemmed)
    return tuple(result)


def _search_terms(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for token in TOKEN_PATTERN.findall(_normalize_text(value)):
        if token in _GENERIC_TOKENS or len(token) < 3:
            continue
        if token not in result:
            result.append(token)
    return tuple(result)


def _region_key(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in _tokens(value)
        if token not in _ADMINISTRATIVE_WORDS
    )


def normalize_unit(value: str) -> str:
    compact = _normalize_text(value).replace(" ", "")
    return _UNIT_ALIASES.get(compact, compact)


def _parse_decimal(value: Any, *, field: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise PricingSourceProtocolError(
            f"FGIS CS field {field} is not decimal"
        ) from exc
    if not parsed.is_finite() or parsed < 0:
        raise PricingSourceProtocolError(
            f"FGIS CS field {field} is not a non-negative finite decimal"
        )
    return parsed


def _period_date(label: str) -> date | None:
    match = PERIOD_PATTERN.search(label)
    if match is None:
        return None
    quarter = int(match.group("quarter"))
    year = int(match.group("year"))
    if quarter == 1:
        return date(year, 3, 31)
    if quarter == 2:
        return date(year, 6, 30)
    if quarter == 3:
        return date(year, 9, 30)
    return date(year, 12, 31)


def _flatten_material_rows(payload: Any) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        raise PricingSourceProtocolError("FGIS CS material response must be an object")
    groups = payload.get("items")
    if not isinstance(groups, list):
        raise PricingSourceProtocolError("FGIS CS material response has no items")
    rows: list[Mapping[str, Any]] = []
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        nested = group.get("items")
        if isinstance(nested, list):
            rows.extend(item for item in nested if isinstance(item, Mapping))
        elif "code" in group:
            rows.append(group)
    return rows


def _score_candidate(
    *,
    description: str,
    unit: str,
    candidate: Mapping[str, Any],
) -> FgisCandidate | None:
    candidate_unit = str(candidate.get("unitName") or "").strip()
    if not candidate_unit or normalize_unit(candidate_unit) != normalize_unit(unit):
        return None
    query_tokens = set(_tokens(description))
    candidate_tokens = set(_tokens(str(candidate.get("name") or "")))
    if not query_tokens or not candidate_tokens:
        return None
    overlap = query_tokens & candidate_tokens
    minimum_matches = 1 if len(query_tokens) == 1 else 2
    if len(overlap) < minimum_matches:
        return None
    score = Decimal(len(overlap)) / Decimal(len(query_tokens))
    if score < Decimal("0.66"):
        return None
    estimated_price = _parse_decimal(
        candidate.get("estimatedPrice"),
        field="estimatedPrice",
    )
    aggregated_price = _parse_decimal(
        candidate.get("aggregatedPrice"),
        field="aggregatedPrice",
    )
    unit_price = estimated_price if estimated_price is not None else aggregated_price
    if unit_price is None or unit_price <= 0:
        return None
    try:
        resource_id = int(candidate.get("id"))
    except (TypeError, ValueError) as exc:
        raise PricingSourceProtocolError("FGIS CS material id is invalid") from exc
    if resource_id <= 0:
        raise PricingSourceProtocolError("FGIS CS material id is invalid")
    code = str(candidate.get("code") or "").strip()
    name = str(candidate.get("name") or "").strip()
    if not code or not name:
        raise PricingSourceProtocolError("FGIS CS material identity is incomplete")
    return FgisCandidate(
        resource_id=resource_id,
        code=code,
        name=name,
        unit=candidate_unit,
        unit_price=unit_price,
        aggregated_price=aggregated_price,
        distance_price=_parse_decimal(
            candidate.get("distancePrice"),
            field="distancePrice",
        ),
        procurement_storage_percent=_parse_decimal(
            candidate.get("procureStorageCostPercent"),
            field="procureStorageCostPercent",
        ),
        score=score,
    )


def _select_unambiguous_candidate(
    *,
    description: str,
    unit: str,
    payload: Any,
) -> FgisCandidate | None:
    candidates = [
        candidate
        for row in _flatten_material_rows(payload)
        if (
            candidate := _score_candidate(
                description=description,
                unit=unit,
                candidate=row,
            )
        )
        is not None
    ]
    candidates.sort(key=lambda item: (-item.score, item.code, item.name))
    if not candidates:
        return None
    if len(candidates) > 1 and candidates[0].score - candidates[1].score < Decimal(
        "0.08"
    ):
        return None
    return candidates[0]


class FgisPriceAdapter:
    """Read-only, fail-closed adapter for official regional FGIS CS prices."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 12.0,
        freshness_days: int = 120,
    ) -> None:
        self._transport = transport
        self._timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(timeout_seconds, 4.0),
        )
        self._freshness_days = freshness_days

    async def refresh_material_rows(
        self,
        *,
        region: str,
        rows: list[Mapping[str, Any]],
    ) -> FgisRefreshResult:
        material_rows = [
            row
            for row in rows
            if row.get("kind") == "material"
            and isinstance(row.get("id"), str)
            and isinstance(row.get("description"), str)
            and isinstance(row.get("unit"), str)
        ][:MAX_MATERIAL_ROWS]
        async with httpx.AsyncClient(
            base_url=FGIS_API_BASE,
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "KolibriAI-Estimate/1.0 (+https://kolibriai.ru)",
            },
        ) as client:
            context = await self._resolve_context(client, region)
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_FGIS_REQUESTS)

            async def search(row: Mapping[str, Any]) -> FgisMatch | None:
                async with semaphore:
                    return await self._search_row(client, context, row)

            searched = await asyncio.gather(
                *(search(row) for row in material_rows),
            )
        matches = tuple(match for match in searched if match is not None)
        matched_ids = {match.row_id for match in matches}
        return FgisRefreshResult(
            context=context,
            matches=matches,
            unmatched_row_ids=tuple(
                str(row["id"])
                for row in material_rows
                if str(row["id"]) not in matched_ids
            ),
        )

    async def _resolve_context(
        self,
        client: httpx.AsyncClient,
        region: str,
    ) -> FgisContext:
        subjects, _ = await self._get_json(client, "EstimatedPrice/CountrySubjects")
        if not isinstance(subjects, list):
            raise PricingSourceProtocolError("FGIS CS region response must be a list")
        query_key = set(_region_key(region))
        ranked: list[tuple[int, Mapping[str, Any]]] = []
        for row in subjects:
            if not isinstance(row, Mapping):
                continue
            candidate_key = set(_region_key(str(row.get("name") or "")))
            if not candidate_key:
                continue
            if query_key == candidate_key:
                score = 100
            elif candidate_key.issubset(query_key):
                score = 50 + len(candidate_key)
            else:
                score = len(query_key & candidate_key)
            if score > 0:
                ranked.append((score, row))
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
        if not ranked or (len(ranked) > 1 and ranked[0][0] == ranked[1][0]):
            raise PricingRegionUnresolved(
                "Регион не сопоставлен с субъектом ФГИС ЦС."
            )
        subject = ranked[0][1]
        try:
            subject_id = int(subject["id"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PricingSourceProtocolError("FGIS CS region id is invalid") from exc

        zones, _ = await self._get_json(
            client,
            "EstimatedPrice/PriceZones",
            params={"subjectId": subject_id},
        )
        if not isinstance(zones, list) or len(zones) != 1:
            raise PricingRegionUnresolved(
                "Для региона требуется явный выбор ценовой зоны ФГИС ЦС."
            )
        zone = zones[0]
        periods, _ = await self._get_json(
            client,
            "EstimatedPrice/Periods",
            params={"priceZoneId": int(zone["id"])},
        )
        if not isinstance(periods, list):
            raise PricingSourceProtocolError("FGIS CS periods response must be a list")
        dated_periods: list[tuple[date, Mapping[str, Any]]] = []
        for period in periods:
            if not isinstance(period, Mapping):
                continue
            parsed = _period_date(str(period.get("name") or ""))
            if parsed is not None:
                dated_periods.append((parsed, period))
        dated_periods.sort(key=lambda item: item[0], reverse=True)
        if not dated_periods:
            raise PricingRegionUnresolved(
                "В ФГИС ЦС нет опубликованного периода для региона."
            )
        price_date, period = dated_periods[0]
        return FgisContext(
            subject_id=subject_id,
            subject_name=str(subject["name"]),
            price_zone_id=int(zone["id"]),
            price_zone_name=str(zone["name"]),
            period_id=int(period["id"]),
            period_label=str(period["name"]),
            price_date=price_date,
            fresh_until=price_date + timedelta(days=self._freshness_days),
        )

    async def _search_row(
        self,
        client: httpx.AsyncClient,
        context: FgisContext,
        row: Mapping[str, Any],
    ) -> FgisMatch | None:
        description = str(row["description"])
        query_candidates = [description]
        query_candidates.extend(
            token
            for token in sorted(_search_terms(description), key=len, reverse=True)
            if len(token) >= 5
        )
        seen_queries: set[str] = set()
        for query in query_candidates:
            normalized_query = _normalize_text(query)
            if not normalized_query or normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)
            if len(seen_queries) > MAX_SEARCH_ATTEMPTS_PER_ROW:
                break
            payload, response_meta = await self._get_json(
                client,
                "EstimatedPrice/BuildingResources/Search/Materials",
                params={
                    "countrySubjectId": context.subject_id,
                    "priceZoneId": context.price_zone_id,
                    "periodId": context.period_id,
                    "search": query,
                    "value": query,
                    "materials": "true",
                    "page": 1,
                    "pageSize": 25,
                },
            )
            selected = _select_unambiguous_candidate(
                description=description,
                unit=str(row["unit"]),
                payload=payload,
            )
            if selected is None:
                continue
            return FgisMatch(
                row_id=str(row["id"]),
                context=context,
                candidate=selected,
                source_uri=response_meta["url"],
                fetched_at=response_meta["fetched_at"],
                payload_hash=sha256_json(payload),
                payload=payload,
            )
        return None

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        expected_url = f"{FGIS_API_BASE}/{path.lstrip('/')}"
        if params:
            expected_url = f"{expected_url}?{urlencode(params)}"
        response: httpx.Response | None = None
        for attempt in range(MAX_FGIS_HTTP_ATTEMPTS):
            try:
                response = await client.get(path, params=params)
            except httpx.HTTPError as exc:
                if attempt + 1 >= MAX_FGIS_HTTP_ATTEMPTS:
                    raise PricingSourceUnavailable(
                        "ФГИС ЦС сейчас недоступна."
                    ) from exc
                await asyncio.sleep(0.25)
                continue
            if (
                response.status_code not in RETRYABLE_FGIS_STATUS_CODES
                or attempt + 1 >= MAX_FGIS_HTTP_ATTEMPTS
            ):
                break
            retry_after = response.headers.get("retry-after")
            try:
                retry_delay = float(retry_after) if retry_after else 0.25
            except ValueError:
                retry_delay = 0.25
            await asyncio.sleep(
                max(0.0, min(retry_delay, MAX_FGIS_RETRY_DELAY_SECONDS))
            )
        if response is None:
            raise PricingSourceUnavailable("ФГИС ЦС сейчас недоступна.")
        if response.status_code != 200:
            raise PricingSourceUnavailable(
                f"ФГИС ЦС вернула HTTP {response.status_code}."
            )
        if response.url.host != "fgiscs.minstroyrf.ru":
            raise PricingSourceProtocolError("FGIS CS response origin changed")
        if "json" not in response.headers.get("content-type", "").casefold():
            raise PricingSourceProtocolError("FGIS CS response is not JSON")
        try:
            value = response.json()
        except ValueError as exc:
            raise PricingSourceProtocolError("FGIS CS returned invalid JSON") from exc
        return value, {
            "url": str(response.url) if response.url else expected_url,
            "fetched_at": datetime.now(timezone.utc),
        }


def fgis_price_evidence(
    match: FgisMatch,
    *,
    quote_id: str,
    today: date | None = None,
) -> dict[str, Any]:
    candidate = match.candidate
    context = match.context
    effective_today = today or date.today()
    return {
        "status": "stale" if context.fresh_until < effective_today else "current",
        "source_type": "fgis_cs",
        "source_label": FGIS_PUBLISHER,
        "source_url": FGIS_PUBLIC_PRICES_URL,
        "source_reference": candidate.code,
        "snapshot_hash": match.payload_hash,
        "quote_id": quote_id,
        "material_code": candidate.code,
        "material_name": candidate.name,
        "region": context.subject_name,
        "price_zone": context.price_zone_name,
        "period": context.period_label,
        "price_date": context.price_date.isoformat(),
        "retrieved_at": match.fetched_at.isoformat(),
        "fresh_until": context.fresh_until.isoformat(),
        "freshness_basis": "kolibri_policy_window",
        "tax_status": "unknown",
        "price_scope": "official_reference",
        "unit_price": money(candidate.unit_price),
        "delivery_per_unit": "0.00",
        "landed_unit_price": money(candidate.unit_price),
        "landed_cost_status": "not_calculated",
        "source_distance_price": (
            money(candidate.distance_price)
            if candidate.distance_price is not None
            else None
        ),
        "source_procurement_storage_percent": (
            str(candidate.procurement_storage_percent)
            if candidate.procurement_storage_percent is not None
            else None
        ),
        "binding_status": "indicative",
        "availability": "unknown",
        "lead_time_days": None,
    }


def supplier_price_evidence(
    payload: SupplierOfferInput,
    *,
    quote_id: str,
    snapshot_hash: str,
    region: str,
    unit: str,
    now: date,
) -> dict[str, Any]:
    valid_until = payload.valid_until or (payload.observed_on + timedelta(days=30))
    unit_price = Decimal(payload.unit_price)
    delivery = Decimal(payload.delivery_per_unit)
    landed = unit_price + delivery
    is_stale = valid_until < now
    return {
        "status": "stale" if is_stale else "current",
        "source_type": "supplier_offer",
        "source_label": payload.supplier_name,
        "source_url": str(payload.source_url),
        "source_reference": payload.quote_reference,
        "snapshot_hash": snapshot_hash,
        "quote_id": quote_id,
        "material_code": None,
        "material_name": None,
        "region": region,
        "price_zone": None,
        "period": None,
        "price_date": payload.observed_on.isoformat(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "fresh_until": valid_until.isoformat(),
        "freshness_basis": "supplier_valid_until",
        "tax_status": (
            "included"
            if payload.vat_included is True
            else "excluded"
            if payload.vat_included is False
            else "unknown"
        ),
        "price_scope": "landed",
        "unit_price": money(unit_price),
        "delivery_per_unit": money(delivery),
        "landed_unit_price": money(landed),
        "landed_cost_status": "calculated",
        "source_distance_price": None,
        "source_procurement_storage_percent": None,
        "binding_status": (
            "user_attested_binding"
            if payload.offer_kind == "binding"
            else "user_attested_indicative"
        ),
        "availability": payload.availability,
        "lead_time_days": payload.lead_time_days,
        "unit": unit,
    }
