"""Immutable estimate snapshots and official document-pack issuance.

The estimate draft/version is the calculation authority.  This module takes
one exact version plus the tenant/project context, freezes a JSON snapshot,
validates every monetary invariant, and renders/persists derived files.  A
renderer never reads mutable project data after the snapshot is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
import sqlite3
from typing import Any, Iterable, Literal, Mapping, Sequence
import uuid

from .attachment_store import ATTACHMENT_CONTRACT_MAX_BYTES, StoredContent, store_content_bytes
from .database import transaction
from .estimate_artifact import (
    canonical_estimate_json,
    estimate_content_hash,
    estimate_required_fields,
    estimate_lifecycle_status,
    parse_estimate_document,
)


RENDERER_VERSION = "official_ru_v1"
MONEY_QUANTUM = Decimal("0.01")
_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]{15,159}$")
_DOCUMENT_KIND_RE = re.compile(
    r"^(?:pack|commercial_offer|local_estimate|resource_statement|"
    r"conjunctural_analysis|appendix|invoice)$"
)
_ISSUE_KIND: dict[str, str] = {
    "pack": "pack",
    "commercial_offer": "commercial_offer",
    "local_estimate": "local_estimate",
    "conjunctural_analysis": "conjunctural_analysis",
    "invoice": "invoice",
}
_DOCUMENT_PREFIX: dict[str, str] = {
    "pack": "КП",
    "commercial_offer": "КП",
    "local_estimate": "ЛС",
    "conjunctural_analysis": "КА",
    "invoice": "СЧ",
}
_READY_CONFIDENCE = frozenset({"source_backed", "verified"})


def _preview_from_snapshot(snapshot: Mapping[str, Any]) -> dict[str, object]:
    document = snapshot.get("document") if isinstance(snapshot.get("document"), Mapping) else {}
    project = snapshot.get("project") if isinstance(snapshot.get("project"), Mapping) else {}
    object_info = snapshot.get("object") if isinstance(snapshot.get("object"), Mapping) else {}
    terms = snapshot.get("commercialTerms") if isinstance(snapshot.get("commercialTerms"), Mapping) else {}

    def party_name(value: object) -> str | None:
        return value.get("displayName") if isinstance(value, Mapping) and isinstance(value.get("displayName"), str) else None

    lines = []
    for line in snapshot.get("lines", []):
        if not isinstance(line, Mapping):
            continue
        lines.append(
            {
                "position": int(line.get("position", len(lines) + 1)),
                "section": str(line.get("section", "Прочее"))[:160],
                "description": str(line.get("description", "Позиция без наименования"))[:300],
                "unit": str(line.get("unit", "шт."))[:40],
                "quantity": str(line.get("quantity", "0"))[:40],
                "unitPrice": str(line.get("unitPrice", "0.00"))[:40],
                "lineTotal": str(line.get("lineTotal", "0.00"))[:40],
                "confidence": str(line.get("confidence", ""))[:40],
            }
        )
    return {
        "title": str(project.get("title", "Сметный документ"))[:240],
        "objectName": str(object_info.get("name", "Объект уточняется"))[:240],
        "region": str(object_info.get("resolvedLocation") or "Требуется уточнить")[:160],
        "date": str(document.get("date", ""))[:32],
        "validUntil": str(document.get("validUntil", ""))[:32],
        "number": str(document.get("number", ""))[:64],
        "status": str(document.get("status", "preliminary"))[:24],
        "mode": str(document.get("mode", "preliminary"))[:24],
        "customerName": party_name(snapshot.get("customer")),
        "contractorName": party_name(snapshot.get("contractor")),
        "sections": [
            {"name": str(item.get("name", "Прочее"))[:160], "total": str(item.get("total", "0.00"))[:40]}
            for item in snapshot.get("sections", [])
            if isinstance(item, Mapping)
        ][:50],
        "lines": lines[:60],
        "totalLines": len(lines),
        "truncated": len(lines) > 60,
        "directTotal": str(terms.get("directTotal", "0.00"))[:40],
        "reserve": str(terms.get("reserve", "0.00"))[:40],
        "tax": str(terms.get("tax", "0.00"))[:40],
        "total": str(terms.get("total", "0.00"))[:40],
        "totalWords": str(terms.get("totalWords", ""))[:300],
        "taxMode": str(terms.get("taxMode", "НДС не выделен"))[:120],
        "conditions": [str(value)[:500] for value in snapshot.get("calculationConditions", []) if isinstance(value, str)][:20],
        "exclusions": [str(value)[:500] for value in snapshot.get("scopeExclusions", []) if isinstance(value, str)][:20],
        "paymentSchedule": [
            {"label": str(item.get("label", "Этап оплаты"))[:240], "percent": str(item.get("percent", "0.00"))[:40]}
            for item in terms.get("paymentSchedule", [])
            if isinstance(item, Mapping)
        ][:20],
    }


class DocumentPackError(RuntimeError):
    """A safe, typed failure that can be returned by API and Tool UI."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        required_fields: Sequence[str] = (),
        status_code: int = 422,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
        self.required_fields = tuple(required_fields)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class RenderedDocumentFile:
    kind: Literal["pdf", "xlsx", "docx", "zip"]
    filename: str
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class DocumentPackIssue:
    issue_id: str
    project_id: str
    document_id: str
    estimate_version: int
    status: Literal["preliminary", "issued", "revoked"]
    document_number: str
    renderer_version: str
    source_hash: str
    required_fields: tuple[str, ...]
    files: tuple[dict[str, object], ...]
    preview: dict[str, object]

    def view(self) -> dict[str, object]:
        return {
            "schemaId": "kolibri.estimate-document-pack",
            "schemaVersion": "1.0",
            "issueId": self.issue_id,
            "projectId": self.project_id,
            "documentId": self.document_id,
            "estimateVersion": self.estimate_version,
            "status": self.status,
            "documentNumber": self.document_number,
            "rendererVersion": self.renderer_version,
            "sourceHash": self.source_hash,
            "requiredFields": list(self.required_fields),
            "files": list(self.files),
            "preview": self.preview,
        }


def _money(value: Decimal | str | int | float) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise DocumentPackError(
            "document_money_invalid",
            "В документе обнаружена некорректная денежная сумма.",
        ) from None
    if not parsed.is_finite() or parsed < 0:
        raise DocumentPackError(
            "document_money_invalid",
            "Денежные суммы должны быть неотрицательными.",
        )
    return format(parsed.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def money_words(value: Decimal | str | int) -> str:
    """Return deterministic Russian ruble words for the final total."""

    parsed = Decimal(str(value)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if parsed < 0:
        raise DocumentPackError(
            "document_money_invalid",
            "Сумма прописью не может быть отрицательной.",
        )
    rubles = int(parsed)
    kopeks = int((parsed - Decimal(rubles)) * 100)

    def plural(number: int, forms: tuple[str, str, str]) -> str:
        tail = number % 100
        if 11 <= tail <= 14:
            return forms[2]
        tail = number % 10
        if tail == 1:
            return forms[0]
        if 2 <= tail <= 4:
            return forms[1]
        return forms[2]

    def triad(number: int, feminine: bool = False) -> list[str]:
        hundreds = (
            "", "сто", "двести", "триста", "четыреста", "пятьсот",
            "шестьсот", "семьсот", "восемьсот", "девятьсот",
        )
        tens = (
            "", "", "двадцать", "тридцать", "сорок", "пятьдесят",
            "шестьдесят", "семьдесят", "восемьдесят", "девяносто",
        )
        teens = (
            "десять", "одиннадцать", "двенадцать", "тринадцать",
            "четырнадцать", "пятнадцать", "шестнадцать", "семнадцать",
            "восемнадцать", "девятнадцать",
        )
        units = (
            "", "одна" if feminine else "один", "две" if feminine else "два",
            "три", "четыре", "пять", "шесть", "семь", "восемь", "девять",
        )
        words: list[str] = []
        if number // 100:
            words.append(hundreds[number // 100])
        remainder = number % 100
        if 10 <= remainder <= 19:
            words.append(teens[remainder - 10])
            return words
        if remainder // 10:
            words.append(tens[remainder // 10])
        if remainder % 10:
            words.append(units[remainder % 10])
        return words

    if rubles == 0:
        ruble_words = "ноль"
    else:
        groups = (
            (1_000_000_000, ("миллиард", "миллиарда", "миллиардов"), False),
            (1_000_000, ("миллион", "миллиона", "миллионов"), False),
            (1_000, ("тысяча", "тысячи", "тысяч"), True),
        )
        remainder = rubles
        parts: list[str] = []
        for divisor, forms, feminine in groups:
            group, remainder = divmod(remainder, divisor)
            if group:
                parts.extend(triad(group, feminine=feminine))
                parts.append(plural(group, forms))
        if remainder:
            parts.extend(triad(remainder))
        ruble_words = " ".join(parts)
    return (
        f"{ruble_words[:1].upper() + ruble_words[1:]} "
        f"{plural(rubles, ('рубль', 'рубля', 'рублей'))} "
        f"{kopeks:02d} {plural(kopeks, ('копейка', 'копейки', 'копеек'))}."
    )


def _iso_now(value: str | None = None) -> datetime:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = canonical_estimate_json(dict(value)).encode("utf-8", "strict")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _text(value: object, fallback: str = "") -> str:
    return str(value).strip() if isinstance(value, str) else fallback


def _party(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    role: Literal["client", "contractor"],
) -> dict[str, object] | None:
    row = database.execute(
        """
        SELECT counterparties.id, counterparties.entity_type,
               counterparties.display_name, counterparties.tax_id,
               counterparties.registration_code
        FROM project_parties
        JOIN counterparties
          ON counterparties.tenant_id = project_parties.tenant_id
         AND counterparties.id = project_parties.counterparty_id
        WHERE project_parties.tenant_id = ? AND project_parties.project_id = ?
          AND project_parties.role = ? AND project_parties.status = 'active'
          AND project_parties.is_primary = 1
        LIMIT 1
        """,
        (tenant_id, project_id, role),
    ).fetchone()
    if row is None:
        return None
    requisites = database.execute(
        """
        SELECT legal_name, tax_id, registration_code, bank_name,
               bank_identification_code, settlement_account,
               correspondent_account, legal_address, basis
        FROM counterparty_requisites
        WHERE tenant_id = ? AND counterparty_id = ?
        LIMIT 1
        """,
        (tenant_id, row["id"]),
    ).fetchone()
    value: dict[str, object] = {
        "id": str(row["id"]),
        "role": role,
        "entityType": str(row["entity_type"]),
        "displayName": str(row["display_name"]),
        "taxId": str(row["tax_id"]) if row["tax_id"] is not None else None,
        "registrationCode": (
            str(row["registration_code"])
            if row["registration_code"] is not None
            else None
        ),
    }
    if requisites is not None:
        value["requisites"] = {
            "legalName": str(requisites["legal_name"]),
            "taxId": str(requisites["tax_id"]),
            "registrationCode": (
                str(requisites["registration_code"])
                if requisites["registration_code"] is not None
                else None
            ),
            "bankName": str(requisites["bank_name"]),
            "bankIdentificationCode": str(requisites["bank_identification_code"]),
            "settlementAccount": str(requisites["settlement_account"]),
            "correspondentAccount": str(requisites["correspondent_account"]),
            "legalAddress": requisites["legal_address"],
            "basis": str(requisites["basis"]),
        }
    return value


def _line_source(row: Mapping[str, Any], *, observed_at: str) -> dict[str, object]:
    evidence = row.get("price_evidence")
    if isinstance(evidence, Mapping):
        source_type = _text(evidence.get("source_type"), "source_backed")
        source_hash = _text(evidence.get("snapshot_hash"), "")
        if not _HASH_RE.fullmatch(source_hash):
            source_hash = _canonical_hash({k: evidence[k] for k in sorted(evidence)})
        return {
            "sourceType": source_type,
            "label": _text(evidence.get("source_label"), "Источник Kolibri"),
            "referenceId": evidence.get("source_reference") or evidence.get("quote_id"),
            "documentId": evidence.get("quote_id"),
            "region": evidence.get("region"),
            "observedAt": evidence.get("price_date") or evidence.get("retrieved_at") or observed_at,
            "validUntil": evidence.get("fresh_until"),
            "confidence": _text(row.get("line_confidence"), "source_backed"),
            "stale": evidence.get("status") == "stale",
            "sourceHash": source_hash,
            "taxStatus": evidence.get("tax_status"),
            "deliveryPerUnit": evidence.get("delivery_per_unit"),
        }
    provenance = row.get("engine_price_provenance")
    if isinstance(provenance, Mapping) and provenance.get("verified") is True:
        return {
            "sourceType": "verified",
            "label": _text(provenance.get("sourceLabel"), "Проверенный источник"),
            "referenceId": provenance.get("sourceReference") or provenance.get("reference"),
            "documentId": provenance.get("documentId"),
            "region": provenance.get("region"),
            "observedAt": provenance.get("observedAt") or observed_at,
            "validUntil": provenance.get("validUntil"),
            "confidence": "verified",
            "stale": False,
            "sourceHash": _canonical_hash(dict(provenance)),
            "taxStatus": provenance.get("taxStatus"),
            "deliveryPerUnit": provenance.get("deliveryPerUnit"),
        }
    return {
        "sourceType": "ai_preliminary",
        "label": "Предварительная цена AI",
        "referenceId": None,
        "documentId": None,
        "region": None,
        "observedAt": observed_at,
        "validUntil": None,
        "confidence": _text(row.get("line_confidence"), "preliminary"),
        "stale": False,
        "sourceHash": _canonical_hash({"rowId": row.get("id"), "observedAt": observed_at}),
        "taxStatus": None,
        "deliveryPerUnit": None,
    }


def _normalise_schedule(raw: object) -> list[dict[str, str]]:
    if not isinstance(raw, list) or not raw:
        return [{"label": "Оплата по выпуску документа", "percent": "100.00"}]
    schedule: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise DocumentPackError("document_schedule_invalid", "График платежей имеет неверный формат.")
        label = _text(item.get("label"), "Этап оплаты")[:240]
        percent = _money(item.get("percent", "0"))
        schedule.append({"label": label, "percent": percent})
    total = sum((Decimal(item["percent"]) for item in schedule), Decimal("0"))
    if total != Decimal("100.00"):
        raise DocumentPackError("document_schedule_invalid", "Сумма графика платежей должна быть равна 100%.")
    return schedule


def _document_terms(document: Mapping[str, Any]) -> dict[str, object]:
    raw = document.get("commercial_terms")
    raw = raw if isinstance(raw, Mapping) else {}
    reserve_percent = _money(raw.get("reserve_percent", raw.get("reservePercent", "0")))
    tax_percent = _money(raw.get("tax_percent", raw.get("taxPercent", "0")))
    if Decimal(reserve_percent) > Decimal("100.00") or Decimal(tax_percent) > Decimal("100.00"):
        raise DocumentPackError("document_terms_invalid", "Проценты резерва и налога должны быть от 0 до 100.")
    discount = _money(raw.get("discount", "0"))
    delivery = _money(raw.get("delivery", "0"))
    tax_mode = _text(raw.get("tax_mode", raw.get("taxMode")), "НДС не выделен")
    return {
        "currency": "RUB",
        "reservePercent": reserve_percent,
        "taxPercent": tax_percent,
        "discount": discount,
        "delivery": delivery,
        "taxMode": tax_mode,
        "paymentSchedule": _normalise_schedule(raw.get("payment_schedule", raw.get("paymentSchedule"))),
    }


def build_estimate_document_snapshot(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    document_id: str,
    estimate_version: int,
    document_number: str,
    mode: Literal["preliminary", "issue"],
    renderer_version: str = RENDERER_VERSION,
    now: str | None = None,
) -> dict[str, Any]:
    version_row = database.execute(
        """
        SELECT content_json, content_hash, lifecycle_status, status, created_at
        FROM estimate_versions
        WHERE tenant_id = ? AND project_id = ? AND document_id = ? AND version = ?
        LIMIT 1
        """,
        (tenant_id, project_id, document_id, estimate_version),
    ).fetchone()
    if version_row is None:
        raise DocumentPackError("estimate_version_missing", "Точная версия сметы не найдена.", status_code=404)
    parsed = parse_estimate_document(version_row["content_json"], now=str(version_row["created_at"]))
    rows = parsed.get("rows")
    required = estimate_required_fields(parsed)
    if not isinstance(rows, list) or not rows:
        raise DocumentPackError("estimate_needs_input", "Для документа нужна непустая смета.", required_fields=required or ("Состав работ",))
    lifecycle = estimate_lifecycle_status(parsed, str(version_row["lifecycle_status"] or version_row["status"]))
    if mode == "issue" and lifecycle not in {"ready", "draft"}:
        if lifecycle == "needs_input":
            raise DocumentPackError("estimate_needs_input", "Смета ещё требует исходных данных.", required_fields=required)
        raise DocumentPackError("estimate_not_ready", "Официальный выпуск доступен только для готовой версии сметы.")
    if required and mode == "issue":
        raise DocumentPackError("estimate_needs_input", "Заполните обязательные поля сметы.", required_fields=required)

    project = database.execute(
        """
        SELECT title, status, updated_at
        FROM projects
        WHERE tenant_id = ? AND id = ?
        LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
    if project is None:
        raise DocumentPackError("project_not_found", "Проект не найден.", status_code=404)
    object_row = database.execute(
        """
        SELECT name, name_source
        FROM construction_objects
        WHERE tenant_id = ? AND project_id = ?
        LIMIT 1
        """,
        (tenant_id, project_id),
    ).fetchone()
    observed_at = str(parsed.get("updated_at") or version_row["created_at"] or now or datetime.now(timezone.utc).isoformat())
    if any(not isinstance(row, Mapping) for row in rows):
        raise DocumentPackError("document_arithmetic_mismatch", "Строки сметы имеют неверный формат.")
    parsed_rows = list(rows)
    line_values: list[dict[str, object]] = []
    section_totals: dict[str, Decimal] = {}
    direct_total = Decimal("0")
    stale_rows = 0
    preliminary_rows = 0
    for index, row in enumerate(parsed_rows, start=1):
        try:
            quantity = Decimal(str(row.get("quantity", "0")))
            unit_price = Decimal(str(row.get("unit_price", "0")))
            declared = Decimal(str(row.get("line_total", "0")))
        except (InvalidOperation, ValueError):
            raise DocumentPackError("document_arithmetic_mismatch", "В строке сметы обнаружено нечисловое значение.") from None
        if not all(value.is_finite() and value >= 0 for value in (quantity, unit_price, declared)):
            raise DocumentPackError("document_money_invalid", "Количество и цены не могут быть отрицательными.")
        expected = (quantity * unit_price).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        if expected != declared.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP):
            raise DocumentPackError("document_arithmetic_mismatch", "Расхождение quantity × unitPrice и lineTotal.")
        line_total = expected
        section = _text(row.get("section"), "Прочее")
        section_totals[section] = section_totals.get(section, Decimal("0")) + line_total
        direct_total += line_total
        source = _line_source(row, observed_at=observed_at)
        stale_rows += int(bool(source.get("stale")))
        confidence = _text(source.get("confidence"), "missing")
        preliminary_rows += int(confidence not in _READY_CONFIDENCE)
        line_values.append(
            {
                "position": index,
                "id": _text(row.get("id"), f"row_{index}"),
                "section": section,
                "kind": _text(row.get("kind"), "service"),
                "description": _text(row.get("description"), "Позиция без наименования"),
                "unit": _text(row.get("unit"), "шт."),
                "quantity": format(quantity.normalize(), "f"),
                "unitPrice": _money(unit_price),
                "lineTotal": _money(line_total),
                "catalogEntryId": row.get("catalog_entry_id"),
                "catalogEntryVersion": row.get("catalog_entry_version"),
                "technologyCardVersion": row.get("technology_card_version"),
                "priceObservationId": row.get("price_observation_id"),
                "marketAggregateId": row.get("market_aggregate_id"),
                "confidence": confidence,
                "source": source,
            }
        )
    terms = _document_terms(parsed)
    reserve_percent = Decimal(str(terms["reservePercent"]))
    tax_percent = Decimal(str(terms["taxPercent"]))
    discount = Decimal(str(terms["discount"]))
    delivery = Decimal(str(terms["delivery"]))
    reserve = (direct_total * reserve_percent / Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    taxable = direct_total + reserve + delivery - discount
    tax = (taxable * tax_percent / Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    final_total = taxable + tax
    try:
        declared_total = Decimal(str((parsed.get("totals") or {}).get("total", direct_total)))
    except (InvalidOperation, ValueError):
        raise DocumentPackError("document_arithmetic_mismatch", "Итоговая сумма сметы имеет неверный формат.") from None
    raw_terms = parsed.get("commercial_terms")
    declared_terms_total = raw_terms.get("total") if isinstance(raw_terms, Mapping) else None
    if declared_terms_total is not None:
        try:
            terms_total = Decimal(str(declared_terms_total))
        except (InvalidOperation, ValueError):
            raise DocumentPackError("document_arithmetic_mismatch", "Итог коммерческих условий имеет неверный формат.") from None
        if terms_total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) != final_total:
            raise DocumentPackError("document_arithmetic_mismatch", "Итог коммерческих условий не совпадает с расчётом документа.")
    elif declared_total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) != direct_total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP):
        raise DocumentPackError("document_arithmetic_mismatch", "Итог версии сметы не совпадает с суммой строк.")
    if mode == "issue" and (stale_rows or preliminary_rows):
        raise DocumentPackError("stale_prices_block_ready", "Устаревшие или неподтверждённые цены блокируют официальный выпуск.", required_fields=("Обновить и подтвердить цены",))
    if mode == "issue" and lifecycle != "ready":
        raise DocumentPackError("estimate_not_ready", "Официальный выпуск доступен только для готовой версии сметы.")
    document_date = _iso_now(now or observed_at).date()
    calculation_conditions = parsed.get("calculation_conditions", parsed.get("assumptions", []))
    if not isinstance(calculation_conditions, list):
        calculation_conditions = []
    scope_exclusions = parsed.get("scope_exclusions", [])
    if not isinstance(scope_exclusions, list):
        scope_exclusions = []
    snapshot: dict[str, Any] = {
        "schemaId": "kolibri.estimate_document_snapshot",
        "schemaVersion": "1.0",
        "tenantId": tenant_id,
        "projectId": project_id,
        "documentId": document_id,
        "estimateVersion": estimate_version,
        "document": {
            "number": document_number,
            "date": document_date.isoformat(),
            "validUntil": (document_date + timedelta(days=14)).isoformat(),
            "status": "preliminary" if mode == "preliminary" else "issued",
            "mode": mode,
            "rendererVersion": renderer_version,
        },
        "object": {
            "name": str(object_row["name"]) if object_row is not None else str(project["title"]),
            "address": parsed.get("address"),
            "resolvedLocation": parsed.get("region"),
            "country": "Россия",
            "region": parsed.get("region"),
            "timezone": parsed.get("timezone") or "Europe/Moscow",
            "confidence": "source_backed" if isinstance(parsed.get("region"), str) and parsed.get("region") != "Регион не указан" else "missing",
            "observedAt": observed_at,
        },
        "project": {
            "title": str(project["title"]),
            "status": str(project["status"]),
            "updatedAt": str(project["updated_at"]),
        },
        "customer": _party(database, tenant_id=tenant_id, project_id=project_id, role="client"),
        "contractor": _party(database, tenant_id=tenant_id, project_id=project_id, role="contractor"),
        "lines": line_values,
        "sections": [
            {"name": name, "total": _money(total)}
            for name, total in section_totals.items()
        ],
        "commercialTerms": {
            **terms,
            "directTotal": _money(direct_total),
            "reserve": _money(reserve),
            "tax": _money(tax),
            "total": _money(final_total),
            "totalWords": money_words(final_total),
        },
        "calculationConditions": [str(item)[:500] for item in calculation_conditions if isinstance(item, str)][:50],
        "scopeExclusions": [str(item)[:500] for item in scope_exclusions if isinstance(item, str)][:50],
        "requiredFields": required,
        "sourceEstimateHash": str(version_row["content_hash"] or estimate_content_hash(parsed)),
        "priceQuality": {
            "staleRows": stale_rows,
            "preliminaryRows": preliminary_rows,
            "totalRows": len(line_values),
        },
        "sourceHash": "",
    }
    source_hash = _canonical_hash({key: value for key, value in snapshot.items() if key != "sourceHash"})
    snapshot["sourceHash"] = source_hash
    return snapshot


def validate_snapshot(snapshot: Mapping[str, Any]) -> None:
    if snapshot.get("schemaId") != "kolibri.estimate_document_snapshot":
        raise DocumentPackError("snapshot_invalid", "Неизвестная схема снимка документа.")
    lines = snapshot.get("lines")
    if not isinstance(lines, list) or not lines:
        raise DocumentPackError("estimate_needs_input", "Снимок не содержит строк сметы.")
    expected_hash = _canonical_hash({key: value for key, value in snapshot.items() if key != "sourceHash"})
    if snapshot.get("sourceHash") != expected_hash or not _HASH_RE.fullmatch(str(snapshot.get("sourceHash"))):
        raise DocumentPackError("snapshot_hash_mismatch", "Снимок документа повреждён.")
    direct = Decimal(str(snapshot["commercialTerms"]["directTotal"]))
    sections = sum((Decimal(str(item["total"])) for item in snapshot.get("sections", []) if isinstance(item, Mapping)), Decimal("0"))
    if direct != sections:
        raise DocumentPackError("document_arithmetic_mismatch", "Суммы разделов не совпадают с прямыми затратами.")
    terms = snapshot["commercialTerms"]
    reserve = Decimal(str(terms["reserve"]))
    reserve_expected = (direct * Decimal(str(terms["reservePercent"])) / Decimal("100")).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if reserve != reserve_expected:
        raise DocumentPackError("document_arithmetic_mismatch", "Расхождение суммы резерва.")
    total = Decimal(str(terms["total"]))
    expected_total = direct + reserve + Decimal(str(terms["delivery"])) - Decimal(str(terms["discount"])) + Decimal(str(terms["tax"]))
    if total != expected_total or money_words(total) != str(terms["totalWords"]):
        raise DocumentPackError("document_arithmetic_mismatch", "Расхождение итоговой суммы документа.")
    schedule = terms.get("paymentSchedule")
    if not isinstance(schedule, list) or sum((Decimal(str(item["percent"])) for item in schedule), Decimal("0")) != Decimal("100.00"):
        raise DocumentPackError("document_schedule_invalid", "Сумма графика платежей должна быть равна 100%.")
    for line in lines:
        quantity = Decimal(str(line["quantity"]))
        unit_price = Decimal(str(line["unitPrice"]))
        line_total = Decimal(str(line["lineTotal"]))
        if (quantity * unit_price).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP) != line_total:
            raise DocumentPackError("document_arithmetic_mismatch", "Расхождение строки сметы.")


def _prefix_number(kind: str, year: int, number: int) -> str:
    return f"{_DOCUMENT_PREFIX[kind]}-{year:04d}-{number:06d}"


def _issue_from_row(
    database: sqlite3.Connection,
    row: sqlite3.Row,
) -> DocumentPackIssue:
    artifacts = database.execute(
        """
        SELECT id, artifact_kind, filename, media_type, size_bytes, artifact_hash
        FROM estimate_document_artifacts
        WHERE tenant_id = ? AND issue_id = ?
        ORDER BY artifact_kind
        """,
        (row["tenant_id"], row["id"]),
    ).fetchall()
    snapshot = json.loads(str(row["snapshot_json"]))
    return DocumentPackIssue(
        issue_id=str(row["id"]),
        project_id=str(row["project_id"]),
        document_id=str(row["document_id"]),
        estimate_version=int(row["estimate_version"]),
        status=str(row["status"]),  # type: ignore[arg-type]
        document_number=str(row["document_number"]),
        renderer_version=str(row["renderer_version"]),
        source_hash=str(row["source_hash"]),
        required_fields=tuple(str(item) for item in snapshot.get("requiredFields", []) if isinstance(item, str)),
        preview=_preview_from_snapshot(snapshot),
        files=tuple(
            {
                "artifactId": str(artifact["id"]),
                "kind": str(artifact["artifact_kind"]),
                "filename": str(artifact["filename"]),
                "mediaType": str(artifact["media_type"]),
                "sizeBytes": int(artifact["size_bytes"]),
                "artifactHash": str(artifact["artifact_hash"]),
                "downloadUrl": f"/api/v3/projects/{row['project_id']}/estimate/document-pack/{row['id']}/artifacts/{artifact['id']}",
            }
            for artifact in artifacts
        ),
    )


def load_document_issue(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    issue_id: str,
) -> DocumentPackIssue | None:
    row = database.execute(
        """
        SELECT *
        FROM estimate_document_issues
        WHERE tenant_id = ? AND project_id = ? AND id = ?
        LIMIT 1
        """,
        (tenant_id, project_id, issue_id),
    ).fetchone()
    return None if row is None else _issue_from_row(database, row)


def get_document_artifact(
    database: sqlite3.Connection,
    *,
    tenant_id: str,
    project_id: str,
    issue_id: str,
    artifact_id: str,
) -> sqlite3.Row | None:
    return database.execute(
        """
        SELECT artifact.*
        FROM estimate_document_artifacts AS artifact
        JOIN estimate_document_issues AS issue
          ON issue.tenant_id = artifact.tenant_id AND issue.id = artifact.issue_id
        WHERE artifact.tenant_id = ? AND artifact.project_id = ?
          AND artifact.issue_id = ? AND artifact.id = ?
        LIMIT 1
        """,
        (tenant_id, project_id, issue_id, artifact_id),
    ).fetchone()


def _required_invoice_fields(snapshot: Mapping[str, Any]) -> tuple[str, ...]:
    contractor = snapshot.get("contractor")
    customer = snapshot.get("customer")
    requisites = contractor.get("requisites") if isinstance(contractor, Mapping) else None
    missing: list[str] = []
    if not isinstance(contractor, Mapping):
        missing.append("Исполнитель")
    if not isinstance(customer, Mapping):
        missing.append("Заказчик")
    if not isinstance(requisites, Mapping):
        missing.extend(["Юридическое наименование исполнителя", "ИНН", "Банк", "БИК", "Расчётный счёт", "Корреспондентский счёт", "Основание платежа"])
        return tuple(dict.fromkeys(missing))
    labels = {
        "legalName": "Юридическое наименование исполнителя",
        "taxId": "ИНН",
        "bankName": "Банк",
        "bankIdentificationCode": "БИК",
        "settlementAccount": "Расчётный счёт",
        "correspondentAccount": "Корреспондентский счёт",
        "basis": "Основание платежа",
    }
    for key, label in labels.items():
        if not _text(requisites.get(key)):
            missing.append(label)
    return tuple(dict.fromkeys(missing))


def issue_document_pack(
    database: sqlite3.Connection,
    *,
    settings: Any,
    tenant_id: str,
    user_id: str,
    project_id: str,
    document_id: str,
    estimate_version: int,
    requested_kinds: Iterable[str],
    mode: Literal["preliminary", "issue"],
    idempotency_key: str,
    renderer_version: str = RENDERER_VERSION,
    now: str | None = None,
) -> DocumentPackIssue:
    if _IDEMPOTENCY_RE.fullmatch(idempotency_key) is None:
        raise DocumentPackError("idempotency_key_invalid", "Ключ идемпотентности документа имеет неверный формат.")
    kinds = tuple(dict.fromkeys(str(kind) for kind in requested_kinds))
    if not kinds:
        kinds = ("pack",)
    if any(_DOCUMENT_KIND_RE.fullmatch(kind) is None for kind in kinds):
        raise DocumentPackError("document_kind_invalid", "Запрошен неподдерживаемый вид документа.")
    if "pack" in kinds:
        expanded = [
            "pack",
            "commercial_offer",
            "local_estimate",
            "resource_statement",
            "conjunctural_analysis",
            "appendix",
        ]
        if "invoice" in kinds:
            expanded.append("invoice")
        kinds = tuple(expanded)
    issue_kind = _ISSUE_KIND.get(kinds[0], "pack")
    current = _iso_now(now)
    year = current.year
    replay = database.execute(
        "SELECT * FROM estimate_document_issues WHERE tenant_id = ? AND idempotency_key = ? LIMIT 1",
        (tenant_id, idempotency_key),
    ).fetchone()
    if replay is not None:
        return _issue_from_row(database, replay)
    with transaction(database, immediate=True):
        replay = database.execute(
            "SELECT * FROM estimate_document_issues WHERE tenant_id = ? AND idempotency_key = ? LIMIT 1",
            (tenant_id, idempotency_key),
        ).fetchone()
        if replay is not None:
            return _issue_from_row(database, replay)
        same_scope = database.execute(
            """
            SELECT * FROM estimate_document_issues
            WHERE tenant_id = ? AND project_id = ? AND document_id = ?
              AND estimate_version = ? AND document_kind = ? AND mode = ?
              AND renderer_version = ?
            LIMIT 1
            """,
            (
                tenant_id,
                project_id,
                document_id,
                estimate_version,
                issue_kind,
                mode,
                renderer_version,
            ),
        ).fetchone()
        if same_scope is not None:
            return _issue_from_row(database, same_scope)
        sequence = database.execute(
            """
            INSERT INTO estimate_document_sequences(tenant_id, document_kind, document_year, next_number, updated_at)
            VALUES (?, ?, ?, 2, ?)
            ON CONFLICT(tenant_id, document_kind, document_year)
            DO UPDATE SET next_number = estimate_document_sequences.next_number + 1, updated_at = excluded.updated_at
            RETURNING next_number - 1 AS allocated
            """,
            (tenant_id, issue_kind, year, current.isoformat()),
        ).fetchone()
        if sequence is None:
            raise DocumentPackError("document_number_failed", "Не удалось выделить номер документа.", status_code=503)
        sequence_number = int(sequence["allocated"])
        document_number = _prefix_number(issue_kind, year, sequence_number)
        snapshot = build_estimate_document_snapshot(
            database,
            tenant_id=tenant_id,
            project_id=project_id,
            document_id=document_id,
            estimate_version=estimate_version,
            document_number=document_number,
            mode=mode,
            renderer_version=renderer_version,
            now=current.isoformat(),
        )
        if "invoice" in kinds:
            invoice_missing = _required_invoice_fields(snapshot)
            if invoice_missing:
                raise DocumentPackError("invoice_required_fields", "Счёт не создаётся без реквизитов сторон.", required_fields=invoice_missing)
        validate_snapshot(snapshot)
        from .official_document_renderer import render_document_files
        files = render_document_files(snapshot, requested_kinds=kinds)
        issue_id = f"estimate_issue_{uuid.uuid4().hex}"
        status: Literal["preliminary", "issued"] = "preliminary" if mode == "preliminary" else "issued"
        snapshot_json = canonical_estimate_json(snapshot)
        database.execute(
            """
            INSERT INTO estimate_document_issues(
                tenant_id, id, project_id, document_id, estimate_version,
                document_kind, mode, status, document_year, sequence_number,
                document_number, snapshot_json, source_hash, renderer_version,
                requested_kinds_json, idempotency_key, created_by_user_id,
                created_at, issued_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tenant_id, issue_id, project_id, document_id, estimate_version,
                issue_kind, mode, status, year, sequence_number, document_number,
                snapshot_json, str(snapshot["sourceHash"]), renderer_version,
                json.dumps(kinds, ensure_ascii=False, separators=(",", ":")),
                idempotency_key, user_id, current.isoformat(),
                current.isoformat() if status == "issued" else None,
            ),
        )
        for file in files:
            if len(file.content) > ATTACHMENT_CONTRACT_MAX_BYTES:
                raise DocumentPackError("document_too_large", "Сформированный документ превышает допустимый размер.")
            stored: StoredContent = store_content_bytes(
                settings,
                tenant_id=tenant_id,
                content=file.content,
                max_bytes=ATTACHMENT_CONTRACT_MAX_BYTES,
            )
            artifact_id = f"estimate_artifact_{uuid.uuid4().hex}"
            database.execute(
                """
                INSERT INTO estimate_document_artifacts(
                    tenant_id, id, issue_id, project_id, artifact_kind,
                    filename, media_type, size_bytes, storage_ref, artifact_hash,
                    created_by_user_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tenant_id, artifact_id, issue_id, project_id, file.kind,
                    file.filename, file.media_type, len(file.content),
                    stored.storage_ref, stored.content_hash, user_id,
                    current.isoformat(),
                ),
            )
        row = database.execute(
            "SELECT * FROM estimate_document_issues WHERE tenant_id = ? AND id = ? LIMIT 1",
            (tenant_id, issue_id),
        ).fetchone()
        if row is None:
            raise DocumentPackError("document_issue_failed", "Выпуск документа не сохранён.", status_code=503)
        return _issue_from_row(database, row)


__all__ = [
    "DocumentPackError",
    "DocumentPackIssue",
    "RENDERER_VERSION",
    "build_estimate_document_snapshot",
    "get_document_artifact",
    "issue_document_pack",
    "load_document_issue",
    "money_words",
    "validate_snapshot",
]
