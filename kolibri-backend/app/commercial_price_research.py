"""HTTPS commercial/public price collector for unmatched estimate rows.

This fallback is deliberately narrower than a general shopping scraper.  It
uses search only to discover candidate HTTPS pages, fetches those pages, and
emits evidence only when the fetched bytes contain a parseable RUB unit price
for the requested resource/unit and a compatible project region.  Search rank,
snippets and provider prose are never converted into prices.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
from html import unescape
import inspect
import ipaddress
import json
import re
import socket
from typing import Any, Awaitable, Callable, Iterable, Mapping
from urllib.parse import urljoin, urlsplit

import httpx

from app.estimate_evidence import attest_price_evidence
from app.web_search import web_search


Search = Callable[[str, int], Awaitable[list[dict[str, str]]]]
DnsResolver = Callable[[str], Awaitable[Iterable[str]] | Iterable[str]]

MAX_CANDIDATES_PER_POSITION = 5
MAX_FETCHED_BYTES = 1_000_000
MAX_CONCURRENT_PRICE_ROWS = 6
MAX_RESEARCH_SECONDS = 25.0
MAX_REDIRECTS = 5
COMMERCIAL_PRICE_TTL_DAYS = 30
MIN_NAME_COVERAGE = Decimal("0.45")
LOCAL_PRICE_WINDOW_CHARS = 160
MAX_SEARCH_QUERIES_PER_POSITION = 3
MAX_FETCHED_CANDIDATES_PER_POSITION = 10

TOKEN_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript)[^>]*>.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")
JSON_LD_RE = re.compile(
    r"<script\b[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)
PRICE_TEXT_RE = (
    r"(?<![A-Za-zА-Яа-яЁё0-9])"
    r"(?:\d{1,3}(?:[\s\u00a0]\d{3})+|\d+)(?:[,.]\d{1,2})?"
    r"(?!\d)"
)
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
_FEDERAL_REGION_RE = re.compile(
    r"(?:"
    r"по\s+всей\s+россии|"
    r"доставк\w*\s+по\s+россии|"
    r"доставк\w*\s+во\s+все\s+регионы|"
    r"все\s+регионы\s+россии|"
    r"на\s+территории\s+(?:рф|российской\s+федерации)|"
    r"федеральн\w*\s+цен\w*"
    r")",
    re.IGNORECASE,
)
_QUERY_UNSAFE_RE = re.compile(r"[^a-zа-яё0-9²³+./\-]+", re.IGNORECASE)


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
    evidence_region: str
    extraction_method: str


@dataclass(frozen=True)
class ExtractedOffer:
    unit_price: Decimal
    quote: str
    vat_status: str
    evidence_region: str
    price_date: date
    fresh_until: date
    confidence: Decimal
    method: str


class CommercialPriceResearchClient:
    """Fetch and verify public HTTPS price pages for rows FGIS did not price."""

    def __init__(
        self,
        *,
        searcher: Search | None = None,
        client: httpx.AsyncClient | None = None,
        dns_resolver: DnsResolver | None = None,
        timeout_seconds: float = 12.0,
        ttl_days: int = COMMERCIAL_PRICE_TTL_DAYS,
        max_concurrent_rows: int = MAX_CONCURRENT_PRICE_ROWS,
        research_budget_seconds: float = MAX_RESEARCH_SECONDS,
    ) -> None:
        self._searcher = searcher or web_search
        self._external_client = client
        self._dns_resolver = dns_resolver or _default_dns_resolver
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 5.0))
        self._ttl_days = ttl_days
        self._max_concurrent_rows = max(
            1,
            min(MAX_CONCURRENT_PRICE_ROWS, int(max_concurrent_rows)),
        )
        self._research_budget_seconds = max(
            0.0,
            min(MAX_RESEARCH_SECONDS, float(research_budget_seconds)),
        )

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
            priced_rows = await self._research_positions(
                client,
                unmatched,
                region=region_text,
                observed_at=timestamp,
            )
            for position, parsed in priced_rows:
                price_text = _decimal_text(parsed.unit_price)
                position["price"] = price_text
                position["comment"] = _append_comment(
                    position.get("comment"),
                    (
                        "Цена из публичного HTTPS-источника: "
                        f"{parsed.source_name}; регион источника: {parsed.evidence_region}; "
                        f"действует до {parsed.fresh_until.isoformat()}."
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
                            "region": parsed.evidence_region,
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

    async def _research_positions(
        self,
        client: httpx.AsyncClient,
        positions: list[dict[str, Any]],
        *,
        region: str,
        observed_at: datetime,
    ) -> list[tuple[dict[str, Any], ParsedPagePrice]]:
        if not positions or self._research_budget_seconds <= 0:
            return []

        semaphore = asyncio.Semaphore(self._max_concurrent_rows)

        async def worker(
            index: int,
            position: dict[str, Any],
        ) -> tuple[int, dict[str, Any], ParsedPagePrice | None]:
            async with semaphore:
                parsed = await self._research_position(
                    client,
                    position,
                    region=region,
                    observed_at=observed_at,
                )
                return index, position, parsed

        tasks = [
            asyncio.create_task(worker(index, position))
            for index, position in enumerate(positions)
        ]
        done, pending = await asyncio.wait(tasks, timeout=self._research_budget_seconds)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        completed: list[tuple[int, dict[str, Any], ParsedPagePrice]] = []
        for task in done:
            try:
                index, position, parsed = task.result()
            except asyncio.CancelledError:
                continue
            except Exception:
                continue
            if parsed is not None:
                completed.append((index, position, parsed))

        completed.sort(key=lambda item: item[0])
        return [(position, parsed) for _index, position, parsed in completed]

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
        queries = _build_search_queries(name, unit, region)
        seen_urls: set[str] = set()
        fetched_candidates = 0
        federal_candidate: ParsedPagePrice | None = None
        for query in queries[:MAX_SEARCH_QUERIES_PER_POSITION]:
            try:
                results = await self._searcher(query, MAX_CANDIDATES_PER_POSITION)
            except Exception:
                continue
            for result in results[:MAX_CANDIDATES_PER_POSITION]:
                url = _safe_https_url(result.get("url"))
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                fetched_candidates += 1
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
                    if _is_federal_region(parsed.evidence_region):
                        federal_candidate = federal_candidate or parsed
                    else:
                        return parsed
                if fetched_candidates >= MAX_FETCHED_CANDIDATES_PER_POSITION:
                    return federal_candidate
        return federal_candidate

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
        fetched = await self._fetch_response(client, url)
        if fetched is None:
            return None
        response, final_url = fetched
        try:
            response.raise_for_status()
        except Exception:
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
        extracted = _parse_json_ld_offer(
            html,
            title=title,
            visible_text=visible_text,
            resource_name=resource_name,
            unit=unit,
            region=region,
            observed_at=observed_at,
            ttl_days=self._ttl_days,
        )
        if extracted is None:
            if name_coverage < MIN_NAME_COVERAGE:
                return None
            evidence_region = _resolve_evidence_region(searchable, region)
            if evidence_region is None:
                return None
            price_match = _parse_unit_price(visible_text, unit, resource_name=resource_name)
            if price_match is None:
                return None
            unit_price, quote = price_match
            price_date = _extract_price_date(visible_text) or observed_at.date()
            fresh_until = price_date + timedelta(days=self._ttl_days)
            if observed_at.date() > fresh_until:
                return None
            vat_status = _vat_status(quote)
            extracted = ExtractedOffer(
                unit_price=unit_price,
                quote=quote,
                vat_status=vat_status,
                evidence_region=evidence_region,
                price_date=price_date,
                fresh_until=fresh_until,
                confidence=_confidence(
                    name_coverage,
                    vat_status,
                    evidence_region=evidence_region,
                ),
                method="visible_text",
            )
        return ParsedPagePrice(
            unit_price=extracted.unit_price,
            quote=extracted.quote,
            vat_status=extracted.vat_status,
            title=title,
            source_name=_source_name(final_url),
            final_url=final_url,
            content_sha256=hashlib.sha256(body).hexdigest(),
            price_date=extracted.price_date,
            fresh_until=extracted.fresh_until,
            confidence=extracted.confidence,
            evidence_region=extracted.evidence_region,
            extraction_method=extracted.method,
        )

    async def _fetch_response(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> tuple[httpx.Response, str] | None:
        current_url = await _safe_public_https_url(url, self._dns_resolver)
        if current_url is None:
            return None

        headers = {
            "Accept": "text/html, text/plain;q=0.9, */*;q=0.1",
            "User-Agent": "KolibriAI-EstimatePriceResearch/1.0",
        }
        for _redirect_count in range(MAX_REDIRECTS + 1):
            try:
                response = await client.get(
                    current_url,
                    headers=headers,
                    follow_redirects=False,
                )
            except Exception:
                return None

            if not response.is_redirect:
                return response, current_url

            location = response.headers.get("location")
            await response.aclose()
            if not location:
                return None
            redirected_url = urljoin(current_url, location)
            current_url = await _safe_public_https_url(
                redirected_url,
                self._dns_resolver,
            )
            if current_url is None:
                return None
        return None

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


async def _default_dns_resolver(hostname: str) -> list[str]:
    def resolve() -> list[str]:
        results = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        return sorted({str(item[4][0]) for item in results})

    return await asyncio.to_thread(resolve)


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


async def _safe_public_https_url(
    value: Any,
    dns_resolver: DnsResolver,
) -> str | None:
    candidate = _safe_https_url(value)
    if not candidate:
        return None
    hostname = urlsplit(candidate).hostname
    if not hostname or not await _hostname_resolves_publicly(hostname, dns_resolver):
        return None
    return candidate


async def _hostname_resolves_publicly(
    hostname: str,
    dns_resolver: DnsResolver,
) -> bool:
    host = hostname.rstrip(".")
    if not host:
        return False

    literal = _ip_address(host)
    if literal is not None:
        return _public_ip_address(literal)

    try:
        resolved = dns_resolver(host)
        if inspect.isawaitable(resolved):
            resolved = await resolved
        addresses = [address for address in (_ip_address(item) for item in resolved) if address]
    except Exception:
        return False
    return bool(addresses) and all(_public_ip_address(address) for address in addresses)


def _ip_address(value: Any) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(str(value).strip())
    except ValueError:
        return None


def _public_ip_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        address = mapped
    return not (
        address.is_loopback
        or address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or address.is_reserved
    )


def _extract_title(html: str) -> str:
    match = TITLE_RE.search(html)
    return _clean_text(unescape(match.group(1)), limit=500) if match else ""


def _visible_text(html: str) -> str:
    without_scripts = SCRIPT_STYLE_RE.sub(" ", html)
    text = TAG_RE.sub(" ", without_scripts)
    return _clean_text(unescape(text), limit=200_000)


def _build_search_queries(resource_name: str, unit: str, region: str) -> list[str]:
    """Build locality-ordered, bounded search phrases from user facts.

    The collector searches the exact locality first, then an explicitly
    supplied federal subject (for values such as ``City, Subject``), and only
    then a nationwide delivery route.  It never silently rewrites an unknown
    city into a guessed subject.
    """

    resource = _normalise_resource_query(resource_name)
    normalized_unit = _normalise_search_term(_normalise_unit(unit), maximum=40)
    project_region = _normalise_search_term(region, maximum=160)
    if not resource or not normalized_unit or not project_region:
        return []

    localities = _region_search_tiers(str(region or ""))
    queries: list[str] = []
    for index, locality in enumerate(localities):
        if index == 0:
            raw = f"{resource} {normalized_unit} цена руб {locality}"
        elif _is_federal_region(locality):
            raw = f"{resource} {normalized_unit} цена доставка по России {project_region}"
        else:
            raw = f"{resource} {normalized_unit} прайс поставщик {locality}"
        query = _clean_text(raw, limit=500)
        if query and query not in queries:
            queries.append(query)
    return queries


def _normalise_resource_query(value: Any) -> str:
    text = _normalise_search_term(value, maximum=320).casefold()
    replacements = (
        (r"\bпрофилированн\w*\s+лист\w*\b", "профнастил"),
        (r"\bпрофлист\w*\b", "профнастил"),
        (r"\bпогонн\w*\s+метр\w*\b", "пог.м"),
        (r"\bквадратн\w*\s+метр\w*\b", "м²"),
        (r"\bкубическ\w*\s+метр\w*\b", "м³"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    # Long provider-generated row labels hurt commercial search precision.
    # Preserve the leading resource/specification tokens but remove duplicate
    # words and cap the phrase so locality/unit terms remain influential.
    tokens: list[str] = []
    seen: set[str] = set()
    for token in text.split():
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= 14:
            break
    return " ".join(tokens)


def _normalise_search_term(value: Any, *, maximum: int) -> str:
    text = unescape(str(value or "")).replace("×", "x")
    text = _QUERY_UNSAFE_RE.sub(" ", text)
    return _clean_text(text, limit=maximum)


def _region_search_tiers(region: str) -> list[str]:
    exact = _normalise_search_term(region, maximum=160)
    tiers = [exact] if exact else []
    parts = [
        _normalise_search_term(part, maximum=160)
        for part in re.split(r"[,;/]", str(region or ""))
        if _normalise_search_term(part, maximum=160)
    ]
    if len(parts) > 1:
        subject = parts[-1]
        if subject.casefold() != exact.casefold() and subject not in tiers:
            tiers.append(subject)
    if exact and not _is_federal_region(exact):
        tiers.append("Россия")
    return tiers[:MAX_SEARCH_QUERIES_PER_POSITION]


def _parse_json_ld_offer(
    html: str,
    *,
    title: str,
    visible_text: str,
    resource_name: str,
    unit: str,
    region: str,
    observed_at: datetime,
    ttl_days: int,
) -> ExtractedOffer | None:
    """Extract a RUB schema.org Product/Offer bound to resource, unit and area."""

    candidates: list[tuple[Decimal, ExtractedOffer]] = []
    for payload in _json_ld_payloads(html):
        for product_name, offer, context in _schema_offer_nodes(payload):
            coverage = _name_coverage(resource_name, product_name or title)
            if coverage < MIN_NAME_COVERAGE:
                continue
            price_spec = offer.get("priceSpecification")
            specifications = price_spec if isinstance(price_spec, list) else [price_spec]
            specifications = [item for item in specifications if isinstance(item, Mapping)] or [{}]
            for specification in specifications:
                price = _decimal(
                    offer.get("price")
                    or offer.get("lowPrice")
                    or specification.get("price")
                    or specification.get("minPrice")
                )
                if price <= 0:
                    continue
                currency = _clean_text(
                    offer.get("priceCurrency") or specification.get("priceCurrency"),
                    limit=16,
                ).upper()
                if currency not in {"RUB", "RUR"}:
                    continue
                structured_unit = _schema_offer_unit(offer, specification)
                if not _units_compatible(unit, structured_unit):
                    continue

                area_text = " ".join(
                    part
                    for part in (
                        _json_ld_text(context.get("areaServed")),
                        _json_ld_text(offer.get("areaServed")),
                        _json_ld_text(offer.get("eligibleRegion")),
                        _json_ld_text(offer.get("shippingDetails")),
                    )
                    if part
                )
                evidence_region = _resolve_evidence_region(
                    f"{title} {visible_text} {area_text}",
                    region,
                )
                if evidence_region is None:
                    continue

                price_date = (
                    _parse_json_ld_date(specification.get("validFrom"), observed_at)
                    or _parse_json_ld_date(offer.get("validFrom"), observed_at)
                    or _parse_json_ld_date(context.get("dateModified"), observed_at)
                    or _extract_price_date(visible_text)
                    or observed_at.date()
                )
                valid_until = (
                    _parse_json_ld_date(specification.get("priceValidUntil"), observed_at, allow_future=True)
                    or _parse_json_ld_date(offer.get("priceValidUntil"), observed_at, allow_future=True)
                )
                fresh_until = price_date + timedelta(days=ttl_days)
                if valid_until is not None:
                    fresh_until = min(fresh_until, valid_until)
                if observed_at.date() > fresh_until:
                    continue

                vat_status = _json_ld_vat_status(offer, specification)
                quote = _clean_text(
                    "Schema.org Product/Offer: "
                    f"{product_name or title}; {price} RUB/{_normalise_unit(unit)}; "
                    f"регион {evidence_region}; НДС {_vat_label(vat_status)}.",
                    limit=500,
                )
                confidence = _confidence(
                    coverage,
                    vat_status,
                    evidence_region=evidence_region,
                    structured=True,
                )
                candidates.append(
                    (
                        confidence,
                        ExtractedOffer(
                            unit_price=price,
                            quote=quote,
                            vat_status=vat_status,
                            evidence_region=evidence_region,
                            price_date=price_date,
                            fresh_until=fresh_until,
                            confidence=confidence,
                            method="schema_org_offer",
                        ),
                    )
                )
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _json_ld_payloads(html: str) -> Iterable[Any]:
    for raw in JSON_LD_RE.findall(html):
        candidate = unescape(raw).strip()
        if not candidate:
            continue
        try:
            yield json.loads(candidate)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue


def _schema_offer_nodes(payload: Any) -> Iterable[tuple[str, Mapping[str, Any], Mapping[str, Any]]]:
    if isinstance(payload, list):
        for item in payload:
            yield from _schema_offer_nodes(item)
        return
    if not isinstance(payload, Mapping):
        return

    graph = payload.get("@graph")
    if isinstance(graph, (list, Mapping)):
        yield from _schema_offer_nodes(graph)

    types = _schema_types(payload.get("@type"))
    if "product" in types:
        product_name = _clean_text(payload.get("name"), limit=500)
        offers = payload.get("offers")
        offer_items = offers if isinstance(offers, list) else [offers]
        for offer in offer_items:
            if isinstance(offer, Mapping) and _schema_types(offer.get("@type")) & {"offer", "aggregateoffer"}:
                yield product_name, offer, payload
    elif types & {"offer", "aggregateoffer"}:
        item = payload.get("itemOffered")
        item_name = _json_ld_text(item.get("name")) if isinstance(item, Mapping) else ""
        item_name = item_name or _clean_text(payload.get("name"), limit=500)
        if item_name:
            yield item_name, payload, payload


def _schema_types(value: Any) -> set[str]:
    values = value if isinstance(value, list) else [value]
    return {
        str(item or "").rstrip("/").rsplit("/", 1)[-1].casefold()
        for item in values
        if str(item or "").strip()
    }


def _schema_offer_unit(offer: Mapping[str, Any], specification: Mapping[str, Any]) -> str:
    reference = specification.get("referenceQuantity") or offer.get("referenceQuantity")
    reference = reference if isinstance(reference, Mapping) else {}
    raw = (
        specification.get("unitText")
        or specification.get("unitCode")
        or offer.get("unitText")
        or offer.get("unitCode")
        or reference.get("unitText")
        or reference.get("unitCode")
    )
    unit_codes = {
        "MTK": "м²",
        "MTQ": "м³",
        "MTR": "м",
        "PCE": "шт",
        "H87": "шт",
        "KGM": "кг",
        "TNE": "т",
        "SET": "компл",
    }
    text = _clean_text(raw, limit=40)
    return unit_codes.get(text.upper(), _normalise_unit(text))


def _units_compatible(requested: Any, offered: Any) -> bool:
    return bool(offered) and _normalise_unit(requested) == _normalise_unit(offered)


def _parse_json_ld_date(value: Any, observed_at: datetime, *, allow_future: bool = False) -> date | None:
    raw = _clean_text(value, limit=64)
    if not raw:
        return None
    try:
        parsed = date.fromisoformat(raw[:10])
    except ValueError:
        return None
    if not allow_future and parsed > observed_at.date():
        return None
    return parsed


def _json_ld_vat_status(offer: Mapping[str, Any], specification: Mapping[str, Any]) -> str:
    value = specification.get("valueAddedTaxIncluded")
    if value is None:
        value = offer.get("valueAddedTaxIncluded")
    if isinstance(value, bool):
        return "included" if value else "excluded"
    normalized = str(value or "").strip().casefold()
    if normalized in {"true", "1", "yes"}:
        return "included"
    if normalized in {"false", "0", "no"}:
        return "excluded"
    return "unknown"


def _json_ld_text(value: Any) -> str:
    if isinstance(value, Mapping):
        preferred = [
            value.get("name"),
            value.get("addressRegion"),
            value.get("addressLocality"),
            value.get("addressCountry"),
        ]
        nested = " ".join(_json_ld_text(item) for item in preferred if item)
        return _clean_text(nested, limit=500)
    if isinstance(value, list):
        return _clean_text(" ".join(_json_ld_text(item) for item in value), limit=500)
    return _clean_text(value, limit=500)


def _vat_label(status: str) -> str:
    return {
        "included": "включён",
        "excluded": "не включён",
        "not_applicable": "не применяется",
        "unknown": "не указан",
    }.get(status, "не указан")


def _parse_unit_price(
    text: str,
    unit: str,
    *,
    resource_name: str,
) -> tuple[Decimal, str] | None:
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
        for match in pattern.finditer(text):
            price = _decimal(match.group("price"))
            if price <= 0:
                continue
            start = max(0, match.start() - LOCAL_PRICE_WINDOW_CHARS)
            end = min(len(text), match.end() + LOCAL_PRICE_WINDOW_CHARS)
            quote = _clean_text(text[start:end], limit=500)
            if not _window_mentions_resource(resource_name, quote):
                continue
            return price, quote
    return None


def _window_mentions_resource(resource_name: str, text: str) -> bool:
    expected = set(_tokens(resource_name)) - _STOP_WORDS
    if not expected:
        return False
    actual = set(_tokens(text)) - _STOP_WORDS
    actual_stems = {_stem(token) for token in actual}
    return all(token in actual or _stem(token) in actual_stems for token in expected)


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


def _confidence(
    name_coverage: Decimal,
    vat_status: str,
    *,
    evidence_region: str = "",
    structured: bool = False,
) -> Decimal:
    score = Decimal("0.55") + min(name_coverage, Decimal("1")) * Decimal("0.30") + Decimal("0.10")
    if vat_status != "unknown":
        score += Decimal("0.05")
    if structured:
        score += Decimal("0.02")
    cap = Decimal("0.78") if _is_federal_region(evidence_region) else Decimal("0.95")
    return min(score, cap).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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
    return _resolve_evidence_region(text, region) is not None


def _resolve_evidence_region(text: str, project_region: str) -> str | None:
    if _is_federal_region(project_region) and re.search(
        r"\b(?:россия|рф|российск\w*\s+федерац\w*)\b",
        text,
        re.IGNORECASE,
    ):
        return "Россия"
    expected = [token for token in _tokens(project_region) if token not in _REGION_STOP_WORDS]
    actual = [token for token in _tokens(text) if token not in _REGION_STOP_WORDS]
    matched = [
        token
        for token in expected
        if any(_region_word_matches(token, candidate) for candidate in actual)
    ]
    if matched:
        if len(matched) == len(expected):
            return _clean_text(project_region, limit=240)
        return ", ".join(_display_region_token(token) for token in matched)
    if _FEDERAL_REGION_RE.search(text):
        return "Россия"
    return None


def _region_word_matches(left: str, right: str) -> bool:
    left = left.casefold()
    right = right.casefold()
    if left == right:
        return True
    if min(len(left), len(right)) < 5:
        return False
    # City case inflections: Москва/Москве, Казань/Казани.
    if len(left) == len(right) and left[:-1] == right[:-1]:
        return True
    if (left.startswith(right) or right.startswith(left)) and abs(len(left) - len(right)) <= 2:
        return True
    common = 0
    for left_char, right_char in zip(left, right):
        if left_char != right_char:
            break
        common += 1
    shortest = min(len(left), len(right))
    return shortest >= 8 and common >= max(7, shortest - 2)


def _display_region_token(token: str) -> str:
    return token[:1].upper() + token[1:]


def _is_federal_region(value: str) -> bool:
    normalized = " ".join(_tokens(value))
    return normalized in {"россия", "рф", "российская федерация"}


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
