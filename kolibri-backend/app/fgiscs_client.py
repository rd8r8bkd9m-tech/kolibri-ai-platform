"""Official FGIS CS price collector for Russian construction estimates.

The public FGIS CS API is the primary price source for estimate resources.
This adapter deliberately fails closed: an unavailable period, ambiguous
resource, unit mismatch or unpublished dataset produces no price evidence.
It never fabricates a replacement rate.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping
from urllib.parse import urlencode

import httpx

from app.estimate_evidence import attest_price_evidence


FGISCS_ORIGIN = "https://fgiscs.minstroyrf.ru"
FGISCS_API = f"{FGISCS_ORIGIN}/api"
PERIOD_RE = re.compile(r"(?P<quarter>[1-4])\s*квартал\s*(?P<year>20\d{2})", re.IGNORECASE)
TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
MAX_POSITIONS_PER_REQUEST = 200
# Fuzzy enrichment changes money, so it must behave like a strict resolver,
# not a search suggestion.  Looser matches stay unpriced for human review.
MIN_MATCH_SCORE = Decimal("0.90")

_TOKEN_STOP = {
    "для", "при", "работ", "работы", "материал", "материалы", "устройство",
    "комплекс", "комплект", "строительный", "строительные", "монтаж",
}
_CITY_TO_SUBJECT_HINT = {
    "лениногорск": "татарстан",
}


@dataclass(frozen=True)
class FgisRegion:
    subject_id: int
    subject_name: str
    price_zone_id: int
    price_zone_name: str


@dataclass(frozen=True)
class FgisPeriod:
    period_id: int
    name: str
    price_date: date


@dataclass(frozen=True)
class FgisResource:
    code: str
    name: str
    unit: str
    estimated_price: Decimal
    raw: Mapping[str, Any]
    match_score: Decimal
    kind: str
    endpoint: str
    flag: str


class FgisCsClient:
    """Small async client for the public, fixed-origin FGIS CS API."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        self._external_client = client
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))

    async def enrich_draft(
        self,
        draft: Mapping[str, Any],
        *,
        observed_at: datetime | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Replace only matched resource prices and return trusted evidence.

        Quantities and scope remain the provider's unverified draft.  Official
        resource prices cross the trust boundary only after an exact unit and
        sufficiently strong name/code match.
        """

        enriched = deepcopy(dict(draft))
        sections = enriched.get("sections")
        if not isinstance(sections, list):
            return enriched, []
        region_text = str(enriched.get("region") or "").strip()
        if not region_text:
            return enriched, []

        async with self._client_context() as client:
            region = await self._resolve_region(client, region_text)
            if region is None:
                return enriched, []
            periods = await self._periods(client, region.price_zone_id)
            if not periods:
                return enriched, []

            positions = [
                position
                for section in sections[:100]
                if isinstance(section, Mapping)
                for position in (section.get("positions") or [])[:500]
                if isinstance(position, dict)
            ][:MAX_POSITIONS_PER_REQUEST]
            if not positions:
                return enriched, []

            # Current means the newest period advertised by FGIS CS.  Never
            # silently backfill a previous quarter when the newest catalog is
            # empty or a resource disappeared: that would turn a stale rate
            # into an apparently current one.
            selected_period = periods[0]
            catalog = await self._load_catalog(client, region, selected_period)
            if not catalog:
                return enriched, []
            results = [self._match_position(position, catalog) for position in positions]

        timestamp = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        evidence: list[dict[str, Any]] = []
        for position, result in zip(positions, results, strict=True):
            if isinstance(result, BaseException) or result is None:
                continue
            resource = result
            period = selected_period
            price_text = _decimal_text(resource.estimated_price)
            record = self._evidence_record(
                position=position,
                resource=resource,
                region=region,
                period=period,
                observed_at=timestamp,
            )
            position["price"] = price_text
            position["comment"] = _append_comment(
                position.get("comment"),
                f"Цена ФГИС ЦС: {period.name}, {region.price_zone_name}, без НДС.",
            )
            evidence.append(record)
        return enriched, evidence

    async def _resolve_region(
        self, client: httpx.AsyncClient, region_text: str
    ) -> FgisRegion | None:
        subjects = await self._get_json(client, "/EstimatedPrice/CountrySubjects")
        if not isinstance(subjects, list):
            return None
        query_tokens = _region_tokens(region_text)
        for city, subject in _CITY_TO_SUBJECT_HINT.items():
            if city in region_text.casefold():
                query_tokens.add(subject)
        ranked: list[tuple[int, Mapping[str, Any]]] = []
        for subject in subjects:
            if not isinstance(subject, Mapping):
                continue
            subject_tokens = _region_tokens(str(subject.get("name") or ""))
            score = len(query_tokens & subject_tokens)
            if score:
                ranked.append((score, subject))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
        subject = ranked[0][1]
        subject_id = int(subject["id"])
        zones = await self._get_json(
            client,
            "/EstimatedPrice/PriceZones",
            params={"subjectId": subject_id},
        )
        if not isinstance(zones, list) or not zones:
            return None
        zone = zones[0]
        return FgisRegion(
            subject_id=subject_id,
            subject_name=str(subject["name"]),
            price_zone_id=int(zone["id"]),
            price_zone_name=str(zone["name"]),
        )

    async def _periods(self, client: httpx.AsyncClient, price_zone_id: int) -> list[FgisPeriod]:
        payload = await self._get_json(
            client,
            "/EstimatedPrice/Periods",
            params={"priceZoneId": price_zone_id},
        )
        periods: list[FgisPeriod] = []
        if not isinstance(payload, list):
            return periods
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            match = PERIOD_RE.search(str(item.get("name") or ""))
            if not match:
                continue
            quarter = int(match.group("quarter"))
            year = int(match.group("year"))
            month = quarter * 3
            day = 31 if month in {3, 12} else 30
            periods.append(
                FgisPeriod(
                    period_id=int(item["id"]),
                    name=str(item["name"]),
                    price_date=date(year, month, day),
                )
            )
        periods.sort(key=lambda period: period.price_date, reverse=True)
        return periods

    async def _load_catalog(
        self,
        client: httpx.AsyncClient,
        region: FgisRegion,
        period: FgisPeriod,
    ) -> list[FgisResource]:
        specs = (
            (
                "material",
                "/EstimatedPrice/BuildingResources/Search/Materials",
                "materials",
                {"periodId": period.period_id, "priceZoneId": region.price_zone_id, "materials": "true"},
            ),
            (
                "machine",
                "/EstimatedPrice/BuildingResources/Search/Machines",
                "machines",
                {"periodId": period.period_id, "priceZoneId": region.price_zone_id, "machines": "true"},
            ),
            (
                "labor",
                "/EstimatedPrice/RimWorkerSalaryRegistry",
                "labor",
                {"periodId": period.period_id, "priceZoneId": region.price_zone_id, "take": 1000, "skip": 0},
            ),
        )
        payloads = await asyncio.gather(
            *(self._get_json(client, endpoint, params=params) for _, endpoint, _, params in specs),
            return_exceptions=True,
        )
        catalog: list[FgisResource] = []
        for (kind, endpoint, flag, _params), payload in zip(specs, payloads, strict=True):
            if isinstance(payload, BaseException):
                continue
            rows = _catalog_rows(payload)
            for row in rows:
                resource = _resource_from_row(row, kind=kind, endpoint=endpoint, flag=flag)
                if resource is not None:
                    catalog.append(resource)
        return catalog

    def _match_position(
        self,
        position: Mapping[str, Any],
        catalog: list[FgisResource],
    ) -> FgisResource | None:
        code = str(position.get("code") or "").strip()
        name = str(position.get("name") or "").strip()
        unit = _normalise_unit(position.get("unit"))
        if not name or not unit:
            return None
        exact = next(
            (resource for resource in catalog if resource.code == code and _normalise_unit(resource.unit) == unit),
            None,
        )
        if exact is not None and _name_score(name, exact.name) >= MIN_MATCH_SCORE:
            return replace(exact, match_score=Decimal("1"))
        candidates = [
            replace(resource, match_score=_name_score(name, resource.name))
            for resource in catalog
            if _normalise_unit(resource.unit) == unit
        ]
        candidates.sort(key=lambda resource: resource.match_score, reverse=True)
        if not candidates or candidates[0].match_score < MIN_MATCH_SCORE:
            return None
        if (
            len(candidates) > 1
            and candidates[0].match_score - candidates[1].match_score < Decimal("0.05")
        ):
            return None
        return candidates[0]

    def _evidence_record(
        self,
        *,
        position: Mapping[str, Any],
        resource: FgisResource,
        region: FgisRegion,
        period: FgisPeriod,
        observed_at: datetime,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"periodId": period.period_id, "priceZoneId": region.price_zone_id}
        if resource.kind == "labor":
            params.update({"take": 1000, "skip": 0})
        else:
            params[resource.flag] = "true"
        url = f"{FGISCS_API}{resource.endpoint}?{urlencode(params)}"
        canonical = json.dumps(
            resource.raw,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        verification = "verified" if str(position.get("code") or "") == resource.code else "source_backed"
        return attest_price_evidence({
            "position_code": str(position.get("code") or ""),
            "source_id": f"fgiscs:{period.period_id}:{region.price_zone_id}:{resource.code}",
            "url": url,
            "source_title": (
                f"ФГИС ЦС — { _kind_title(resource.kind) }, "
                f"{region.price_zone_name}, {period.name}"
            ),
            "source_type": "official_catalog",
            "region": region.subject_name,
            "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
            "price_date": period.price_date.isoformat(),
            "unit": resource.unit,
            "vat_status": "excluded",
            "quote": (
                f"{resource.code}: {resource.name}; официальная ставка "
                f"{_decimal_text(resource.estimated_price)} руб./{resource.unit}, без НДС."
            )[:500],
            "unit_price": _decimal_text(resource.estimated_price),
            "currency": "RUB",
            "content_sha256": hashlib.sha256(canonical).hexdigest(),
            "verification": verification,
        })

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        response = await client.get(f"{FGISCS_API}{path}", params=params)
        response.raise_for_status()
        if "application/json" not in response.headers.get("content-type", ""):
            raise ValueError("fgiscs_non_json_response")
        return response.json()

    def _client_context(self):
        if self._external_client is not None:
            return _BorrowedClient(self._external_client)
        return httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "KolibriAI-Estimate/1.0"},
        )


class _BorrowedClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, *_args: Any) -> None:
        return None


def _catalog_rows(payload: Any) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return []
    rows: list[Mapping[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        nested = item.get("items")
        if isinstance(nested, list):
            rows.extend(row for row in nested if isinstance(row, Mapping))
        elif item.get("code"):
            rows.append(item)
    return rows


def _resource_from_row(
    row: Mapping[str, Any],
    *,
    kind: str,
    endpoint: str,
    flag: str,
) -> FgisResource | None:
    code = str(row.get("code") or "").strip()
    name = str(row.get("name") or row.get("salaryRateName") or "").strip()
    unit = str(row.get("unitName") or ("чел.-ч" if kind == "labor" else "")).strip()
    price = _decimal(row.get("salary") if kind == "labor" else row.get("estimatedPrice"))
    if not code or not name or not unit or price <= 0:
        return None
    if kind == "material" and not _material_formula_is_valid(row, price):
        return None
    return FgisResource(
        code=code,
        name=name,
        unit=unit,
        estimated_price=price,
        raw=row,
        match_score=Decimal("0"),
        kind=kind,
        endpoint=endpoint,
        flag=flag,
    )


def _material_formula_is_valid(row: Mapping[str, Any], estimated_price: Decimal) -> bool:
    aggregated = _decimal(row.get("aggregatedPrice"))
    delivery = _decimal(row.get("distancePrice"))
    storage_percent = _decimal(row.get("procureStorageCostPercent"))
    if aggregated <= 0 or storage_percent < 0:
        return False
    expected = ((aggregated + delivery) * (Decimal("1") + storage_percent / Decimal("100"))).quantize(
        Decimal("0.01")
    )
    return expected == estimated_price.quantize(Decimal("0.01"))


def _kind_title(kind: str) -> str:
    return {
        "material": "сметные цены строительных ресурсов",
        "machine": "сметные цены эксплуатации машин и механизмов",
        "labor": "сметные цены затрат труда работников",
    }.get(kind, "сметные цены")


def _name_score(expected: str, actual: str) -> Decimal:
    left = set(_tokens(expected)) - _TOKEN_STOP
    right = set(_tokens(actual)) - _TOKEN_STOP
    if not left or not right:
        return Decimal("0")
    intersection = left & right
    coverage = Decimal(len(intersection)) / Decimal(len(left))
    precision = Decimal(len(intersection)) / Decimal(min(len(right), max(len(left) * 2, 1)))
    score = coverage * Decimal("0.8") + min(precision, Decimal("1")) * Decimal("0.2")
    return score.quantize(Decimal("0.0001"))


def _tokens(value: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(value)]


def _region_tokens(value: str) -> set[str]:
    stop = {"республика", "область", "край", "город", "г", "россия", "рф"}
    return {token for token in _tokens(value) if len(token) > 1 and token not in stop}


def _normalise_unit(value: Any) -> str:
    unit = " ".join(str(value or "").split()).strip().casefold()
    aliases = {
        "м2": "м²",
        "м^2": "м²",
        "м3": "м³",
        "м^3": "м³",
        "кв.м": "м²",
        "куб.м": "м³",
        "тонна": "т",
        "комплект": "компл",
    }
    return aliases.get(unit, unit)


def _decimal(value: Any) -> Decimal:
    raw = str(value if value is not None else "").strip().replace(" ", "").replace(",", ".")
    try:
        parsed = Decimal(raw)
        return parsed if parsed.is_finite() else Decimal("0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f") if normalized != normalized.to_integral() else str(normalized.quantize(Decimal("1")))


def _append_comment(current: Any, note: str) -> str:
    text = " ".join(str(current or "").split()).strip()
    if not text:
        return note
    if note.casefold() in text.casefold():
        return text
    return f"{text} {note}"[:1_000]
