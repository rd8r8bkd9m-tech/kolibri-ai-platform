"""HTTPS commercial/public price collector for unmatched estimate rows.

This fallback is deliberately narrower than a general shopping scraper.  It
uses search only to discover candidate HTTPS pages, fetches those pages, and
emits evidence only when the fetched bytes contain a parseable RUB unit price
for the requested resource/unit and a compatible project region.  Search rank,
snippets and provider prose are never converted into prices.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
from html import unescape
import re
from typing import Any, Awaitable, Callable, Iterable, Mapping
from urllib.parse import urlsplit

import httpx

from app.estimate_evidence import attest_price_evidence
from app.web_search import web_search


Search = Callable[[str, int], Awaitable[list[dict[str, str]]]]

MAX_CANDIDATES_PER_POSITION = 5
MAX_FETCHED_BYTES = 1_000_000
COMMERCIAL_PRICE_TTL_DAYS = 30
MIN_NAME_COVERAGE = Decimal("0.45")

TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
PRICE_TEXT_RE = r"(?:\d{1,3}(?:[\s\u00a0]\d{3})+|\d+)(?:[,.]\d{1,2})?"
CURRENCY_RE = r"(?:₽|руб(?:\.|лей|ля|ль)?|р\.)"
PAGE_DATE_RE = re.compile(
    r"(?:актуальн\w*|обновлен\w*|обновлено|цена\s+от|прайс\s+от|дата|действует\s+с)"
    r"[^0-9]{0,30}"
    r"(?P<day>[0-3]?\d)[./-](?P<month>[01]?\d)[./-](?P<year>20\d{2})",
    re.IGNORECASE,
)

_STOP_WORDS = {
    "для", "при", "работ", "работы", "материал", "материалы", "строительный",
    "строительные", "монтаж", "устройство", "цена", "купить", "руб", "ндс",
}
_REGION_STOP_WORDS = {"республика", "область", "край", "город", "россия", "рф"}


@dataclass(frozen=True)
class ParsedPagePrice:
    unit_price: Decimal
    quote: str
    vat_status: str
    title: str
    source_name: str
    final_url: str
    content_sha256: str
    price_date: date
    fresh_until: date
    confidence: Decimal


class CommercialPriceResearchClient:
    """Fetch and verify public HTTPS price pages for rows FGIS did not price."""

    def __init__(
        self,
        *,
        searcher: Search | None = None,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 12.0,
        ttl_days: int = COMMERCIAL_PRICE_TTL_DAYS,
    ) -> None:
        self._searcher = searcher or web_search
        self._external_client = client
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
        self._ttl_days = ttl_days

    async def enrich_draft(
        self,
        draft: Mapping[str, Any],
        *,
        observed_at: datetime | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        enriched = deepcopy(dict(draft))
        sections = enriched.get("sections")
        region_text = str(enriched.get("region") or "").strip()
        if not isinstance(sections, list) or not region_text:
            return enriched, []

        positions = [
            position
            for section in sections[:100]
            if isinstance(section, Mapping)
            for position in (section.get("positions") or [])[:500]
            if isinstance(position, dict)
        ]
        unmatched = [
            position for position in positions
            if _decimal(position.get("price")) <= 0
            and _decimal(position.get("quantity")) > 0
            and str(position.get("name") or "").strip()
            and str(position.get("unit") or "").strip()
        ]
        if not unmatched:
            return enriched, []

        timestamp = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        evidence: list[dict[str, Any]] = []
        async with self._client_context() as client:
            for position in unmatched:
                parsed = await self._research_position(
                    client,
                    position,
                    region=region_text,
                    observed_at=timestamp,
                )
                if parsed is None:
                    continue
                price_text = _decimal_text(parsed.unit_price)
                position["price"] = price_text
                position["comment"] = _append_comment(
                    position.get("comment"),
                    (
                        "Цена из публичного HTTPS-источника: "
                        f"{parsed.source_name}, действует до {parsed.fresh_until.isoformat()}."
                    ),
                )
                evidence.append(
                    attest_price_evidence(
                        {
                            "position_code": str(position.get("code") or ""),
                            "source_id": _source_id(
                                parsed.final_url,
                                str(position.get("code") or ""),
                                parsed.content_sha256,
                            ),
                            "url": parsed.final_url,
                            "source_title": parsed.title,
                            "source_name": parsed.source_name,
                            "source_type": _source_type(parsed.final_url),
                            "region": region_text,
                            "project_region": region_text,
                            "observed_at": timestamp.isoformat().replace("+00:00", "Z"),
                            "retrieved_at": timestamp.isoformat().replace("+00:00", "Z"),
                            "price_date": parsed.price_date.isoformat(),
                            "fresh_until": parsed.fresh_until.isoformat(),
                            "ttl_days": self._ttl_days,
                            "unit": str(position.get("unit") or ""),
                            "vat_status": parsed.vat_status,
                            "confidence": _decimal_text(parsed.confidence),
                            "quote": parsed.quote,
                            "unit_price": price_text,
                            "currency": "RUB",
                            "content_sha256": parsed.content_sha256,
                            "verification": "source_backed",
                        }
                    )
                )
        return enriched, evidence

    async def _research_position(
        self,
        client: httpx.AsyncClient,
        position: Mapping[str, Any],
        *,
        region: str,
        observed_at: datetime,
    ) -> ParsedPagePrice | None:
        name = " ".join(str(position.get("name") or "").split()).strip()
        unit = " ".join(str(position.get("unit") or "").split()).strip()
        query = f"{name} {unit} цена руб {region}"
        try:
            results = await self._searcher(query, MAX_CANDIDATES_PER_POSITION)
        except Exception:
            return None

        seen_urls: set[str] = set()
        for result in results[:MAX_CANDIDATES_PER_POSITION]:
            url = _safe_https_url(result.get("url"))
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            parsed = await self._fetch_and_parse(
                client,
                url,
                result_title=str(result.get("title") or ""),
                resource_name=name,
                unit=unit,
                region=region,
                observed_at=observed_at,
            )
            if parsed is not None:
                return parsed
        return None

    async def _fetch_and_parse(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        result_title: str,
        resource_name: str,
        unit: str,
        region: str,
        observed_at: datetime,
    ) -> ParsedPagePrice | None:
        try:
            response = await client.get(
                url,
                headers={
                    "Accept": "text/html, text/plain;q=0.9, */*;q=0.1",
                    "User-Agent": "KolibriAI-EstimatePriceResearch/1.0",
                },
            )
            response.raise_for_status()
        except Exception:
            return None

        final_url = _safe_https_url(str(response.url))
        if not final_url:
            return None
        content_type = response.headers.get("content-type", "").casefold()
        if content_type and not any(
            allowed in content_type
            for allowed in ("text/html", "text/plain", "application/xhtml+xml")
        ):
            return None
        body = response.content
        if not body or len(body) > MAX_FETCHED_BYTES:
            return None
        try:
            html = body.decode(response.encoding or "utf-8", errors="replace")
        except LookupError:
            html = body.decode("utf-8", errors="replace")

        title = _clean_text(_extract_title(html) or result_title or _source_name(final_url), limit=500)
        visible_text = _visible_text(html)
        searchable = f"{title} {visible_text}"
        name_coverage = _name_coverage(resource_name, searchable)
        if name_coverage < MIN_NAME_COVERAGE:
            return None
        if not _text_mentions_region(searchable, region):
            return None
        price_match = _parse_unit_price(visible_text, unit)
        if price_match is None:
            return None

        unit_price, quote = price_match
        price_date = _extract_price_date(visible_text) or observed_at.date()
        fresh_until = price_date + timedelta(days=self._ttl_days)
        if observed_at.date() > fresh_until:
            return None
        vat_status = _vat_status(quote)
        confidence = _confidence(name_coverage, vat_status)
        return ParsedPagePrice(
            unit_price=unit_price,
            quote=quote,
            vat_status=vat_status,
            title=title,
            source_name=_source_name(final_url),
            final_url=final_url,
            content_sha256=hashlib.sha256(body).hexdigest(),
            price_date=price_date,
            fresh_until=fresh_until,
            confidence=confidence,
        )

    def _client_context(self):
        if self._external_client is not None:
            return _BorrowedClient(self._external_client)
        return httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
        )


class _BorrowedClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def __aenter__(self) -> httpx.AsyncClient:
        return self.client

    async def __aexit__(self, *_args: Any) -> None:
        return None


def _safe_https_url(value: Any) -> str | None:
    candidate = str(value or "").strip()
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        return None
    return candidate


def _extract_title(html: str) -> str:
    match = TITLE_RE.search(html)
    return _clean_text(unescape(match.group(1)), limit=500) if match else ""


def _visible_text(html: str) -> str:
    without_scripts = SCRIPT_STYLE_RE.sub(" ", html)
    text = TAG_RE.sub(" ", without_scripts)
    return _clean_text(unescape(text), limit=200_000)


def _parse_unit_price(text: str, unit: str) -> tuple[Decimal, str] | None:
    unit_re = _unit_regex(_normalise_unit(unit))
    if not unit_re:
        return None
    patterns = (
        re.compile(
            rf"(?P<price>{PRICE_TEXT_RE})\s*{CURRENCY_RE}\s*(?:/|\bза\b\s*(?:1\s*)?)\s*(?P<unit>{unit_re})",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<unit>{unit_re})\s*(?:-|:|—|–)?\s*(?P<price>{PRICE_TEXT_RE})\s*{CURRENCY_RE}",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?P<price>{PRICE_TEXT_RE})\s*{CURRENCY_RE}.{0,24}(?P<unit>{unit_re})",
            re.IGNORECASE,
        ),
    )
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        price = _decimal(match.group("price"))
        if price <= 0:
            continue
        start = max(0, match.start() - 120)
        end = min(len(text), match.end() + 180)
        quote = _clean_text(text[start:end], limit=500)
        return price, quote
    return None


def _unit_regex(unit: str) -> str:
    aliases = {
        "м²": r"(?:м\s*(?:²|2|\^2)|кв\.?\s*м)",
        "м³": r"(?:м\s*(?:³|3|\^3)|куб\.?\s*м)",
        "шт": r"(?:шт\.?|штук[аи]?|штука|ед\.?)",
        "т": r"(?:т\.?|тонн[аы]?)",
        "кг": r"(?:кг\.?|килограмм[аы]?)",
        "м": r"(?:м\.?|метр[аы]?)",
        "пог.м": r"(?:пог\.?\s*м|погонн\w*\s*м)",
        "компл": r"(?:компл\.?|комплект[аы]?)",
        "чел.-ч": r"(?:чел\.?\s*[- ]?\s*ч)",
    }
    return aliases.get(unit, re.escape(unit)) if unit else ""


def _normalise_unit(value: Any) -> str:
    unit = " ".join(str(value or "").split()).strip().casefold()
    aliases = {
        "м2": "м²",
        "м^2": "м²",
        "кв.м": "м²",
        "м3": "м³",
        "м^3": "м³",
        "куб.м": "м³",
        "тонна": "т",
        "комплект": "компл",
    }
    return aliases.get(unit, unit)


def _extract_price_date(text: str) -> date | None:
    match = PAGE_DATE_RE.search(text)
    if not match:
        return None
    try:
        return date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return None


def _vat_status(quote: str) -> str:
    text = quote.casefold()
    if re.search(r"(?:без|не\s+включ)\s+ндс", text):
        return "excluded"
    if re.search(r"(?:с\s+ндс|ндс\s+включ)", text):
        return "included"
    if re.search(r"ндс\s+не\s+облага", text):
        return "not_applicable"
    return "unknown"


def _confidence(name_coverage: Decimal, vat_status: str) -> Decimal:
    score = Decimal("0.55") + min(name_coverage, Decimal("1")) * Decimal("0.30") + Decimal("0.10")
    if vat_status != "unknown":
        score += Decimal("0.05")
    return min(score, Decimal("0.95")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _name_coverage(resource_name: str, text: str) -> Decimal:
    expected = set(_tokens(resource_name)) - _STOP_WORDS
    actual = set(_tokens(text)) - _STOP_WORDS
    if not expected or not actual:
        return Decimal("0")
    matched = {
        token for token in expected
        if token in actual or _stem(token) in {_stem(item) for item in actual}
    }
    return (Decimal(len(matched)) / Decimal(len(expected))).quantize(Decimal("0.0001"))


def _text_mentions_region(text: str, region: str) -> bool:
    expected = set(_tokens(region)) - _REGION_STOP_WORDS
    actual_stems = {_stem(token) for token in _tokens(text)}
    return bool(expected and any(_stem(token) in actual_stems for token in expected))


def _tokens(value: str) -> list[str]:
    return [token.casefold() for token in TOKEN_RE.findall(value)]


def _stem(value: str) -> str:
    return value[:5] if len(value) > 5 else value


def _source_name(url: str) -> str:
    host = urlsplit(url).hostname or "unknown-source"
    return host.removeprefix("www.")[:240]


def _source_type(url: str) -> str:
    host = _source_name(url).casefold()
    marketplace_markers = ("market", "ozon", "wildberries", "avito", "leroy", "satom")
    return "marketplace" if any(marker in host for marker in marketplace_markers) else "supplier_catalog"


def _source_id(url: str, position_code: str, content_sha256: str) -> str:
    digest = hashlib.sha256(f"{url}\n{position_code}\n{content_sha256}".encode("utf-8")).hexdigest()
    return f"commercial:https:{digest[:32]}"


def _clean_text(value: Any, *, limit: int | None = None) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit] if limit is not None else text


def _decimal(value: Any) -> Decimal:
    raw = str(value if value is not None else "").strip().replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    try:
        parsed = Decimal(raw)
        return parsed if parsed.is_finite() else Decimal("0")
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    return format(normalized, "f") if normalized != normalized.to_integral() else str(normalized.quantize(Decimal("1")))


def _append_comment(current: Any, note: str) -> str:
    text = _clean_text(current)
    if not text:
        return note
    if note.casefold() in text.casefold():
        return text
    return f"{text} {note}"[:1_000]
