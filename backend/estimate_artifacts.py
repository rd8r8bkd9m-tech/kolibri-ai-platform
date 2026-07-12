"""Ephemeral estimate inputs and immutable PDF artifacts for the public Shell.

The provider may propose scope, quantities, prices and provenance.  This
module revalidates the typed estimate, recalculates every monetary value with
the deterministic minor-unit engine, persists an optimistic-lock revision and
materializes a content-addressed PDF.  When trustworthy calculation inputs are
missing, it instead materializes a non-monetary readiness checklist bound to
the request and gate proof.  Session tokens and provider credentials never
enter estimate content or public artifact records.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from collections import defaultdict
from decimal import Decimal
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    LongTable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from artifact_runtime import EstimateSpec, deterministic_estimate
from data_paths import DATA_DIR, DB_PATH
from sqlite_lifecycle import closing_sqlite_transaction


ARTIFACT_SCHEMA = "kolibri.estimate-artifact.v1"
READINESS_ARTIFACT_SCHEMA = "kolibri.estimate-readiness-artifact.v1"
ESTIMATE_SCHEMA = "kolibri.editable-estimate.v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_FONT_LOCK = threading.Lock()
_FONTS: tuple[str, str] | None = None

_REGULAR_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)
_BOLD_FONTS = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
)
_CATEGORY_LABELS = {
    "labor": "Работы",
    "material": "Материалы",
    "equipment": "Оборудование",
    "service": "Услуги",
    "other": "Прочее",
}


class EstimateArtifactError(RuntimeError):
    pass


class EstimateVersionConflict(EstimateArtifactError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: bytes | str) -> str:
    body = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(body).hexdigest()


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _estimate_pdf_name(title: Any, version: int) -> str:
    """Return a readable, filesystem-neutral filename for public estimate PDFs."""

    clean_title = re.sub(r'[\x00-\x1f\x7f<>:"/\\|?*]+', " ", str(title or "")).strip()
    clean_title = re.sub(r"\s+", " ", clean_title).strip(" .—-")[:120]
    if not clean_title:
        clean_title = "Смета"
    elif not clean_title.casefold().startswith("смет"):
        clean_title = f"Смета — {clean_title}"
    return f"{clean_title} — версия {version}.pdf"


def _font_pair() -> tuple[str, str]:
    global _FONTS
    if _FONTS is not None:
        return _FONTS
    with _FONT_LOCK:
        if _FONTS is not None:
            return _FONTS
        regular_path = next((Path(path) for path in _REGULAR_FONTS if Path(path).is_file()), None)
        bold_path = next((Path(path) for path in _BOLD_FONTS if Path(path).is_file()), None)
        if regular_path is None:
            raise EstimateArtifactError("cyrillic_pdf_font_missing")
        regular_name = "KolibriEstimateRegular"
        bold_name = "KolibriEstimateBold" if bold_path else regular_name
        pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
        if bold_path:
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
        _FONTS = (regular_name, bold_name)
        return _FONTS


def _styles() -> dict[str, ParagraphStyle]:
    regular, bold = _font_pair()
    base = getSampleStyleSheet()
    return {
        "eyebrow": ParagraphStyle(
            "KolibriEstimateEyebrow", parent=base["Normal"], fontName=bold,
            fontSize=7.5, leading=10, textColor=colors.HexColor("#078B9A"),
            uppercase=True, spaceAfter=3,
        ),
        "title": ParagraphStyle(
            "KolibriEstimateTitle", parent=base["Title"], fontName=bold,
            fontSize=20, leading=24, textColor=colors.HexColor("#102126"),
            alignment=TA_LEFT, spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "KolibriEstimateH2", parent=base["Heading2"], fontName=bold,
            fontSize=11, leading=14, textColor=colors.HexColor("#102126"),
            spaceBefore=8, spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "KolibriEstimateBody", parent=base["BodyText"], fontName=regular,
            fontSize=8.5, leading=12, textColor=colors.HexColor("#28373B"),
        ),
        "small": ParagraphStyle(
            "KolibriEstimateSmall", parent=base["BodyText"], fontName=regular,
            fontSize=7.2, leading=9.5, textColor=colors.HexColor("#4D5B60"),
        ),
        "small_bold": ParagraphStyle(
            "KolibriEstimateSmallBold", parent=base["BodyText"], fontName=bold,
            fontSize=7.2, leading=9.5, textColor=colors.HexColor("#28373B"),
        ),
        "money": ParagraphStyle(
            "KolibriEstimateMoney", parent=base["BodyText"], fontName=bold,
            fontSize=9, leading=12, textColor=colors.HexColor("#102126"),
            alignment=TA_RIGHT,
        ),
        "hash": ParagraphStyle(
            "KolibriEstimateHash", parent=base["BodyText"], fontName=regular,
            fontSize=6.2, leading=8.2, textColor=colors.HexColor("#4D5B60"),
            wordWrap="CJK",
        ),
        "warning": ParagraphStyle(
            "KolibriEstimateWarning", parent=base["BodyText"], fontName=bold,
            fontSize=9, leading=12, textColor=colors.HexColor("#7A3A00"),
        ),
    }


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(value or "")), style)


def _money(minor: int, minor_unit: int, currency: str) -> str:
    amount = Decimal(minor) / (Decimal(10) ** minor_unit)
    formatted = f"{amount:,.{minor_unit}f}".replace(",", " ").replace(".", ",")
    return f"{formatted} {currency}"


def _rate(bps: int) -> str:
    return f"{Decimal(bps) / Decimal(100):.2f}".replace(".", ",") + "%"


def _page_footer(binding_sha256: str, label: str = "Расчёт"):
    def draw(canvas, doc):
        regular, bold = _font_pair()
        width, _ = A4
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D8E2E4"))
        canvas.setLineWidth(0.4)
        canvas.line(15 * mm, 13 * mm, width - 15 * mm, 13 * mm)
        canvas.setFont(bold, 7)
        canvas.setFillColor(colors.HexColor("#078B9A"))
        canvas.drawString(15 * mm, 8.5 * mm, "KOLIBRI AI")
        canvas.setFont(regular, 6.5)
        canvas.setFillColor(colors.HexColor("#657176"))
        canvas.drawCentredString(width / 2, 8.5 * mm, f"{label} {binding_sha256[:16]}")
        canvas.drawRightString(width - 15 * mm, 8.5 * mm, f"Страница {doc.page}")
        canvas.restoreState()
    return draw


def generate_estimate_pdf(
    spec: EstimateSpec,
    calculation: dict[str, Any],
    output_path: str | Path,
    *,
    estimate_id: str,
    version: int,
) -> Path:
    """Generate a polished PDF from a validated deterministic calculation."""

    expected = deterministic_estimate(spec)
    if expected != calculation:
        raise EstimateArtifactError("estimate_calculation_mismatch")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    regular, bold = _font_pair()
    calculation_sha = str(calculation["calculation_sha256"])
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=18 * mm,
        title=spec.title, author="Kolibri AI",
        subject=f"Смета {estimate_id}, версия {version}",
    )
    story: list[Any] = [
        _p("KOLIBRI AI / СМЕТА", styles["eyebrow"]),
        _p(spec.title, styles["title"]),
    ]
    meta_rows = [
        [_p("Регион", styles["small_bold"]), _p(spec.region, styles["small"])],
        [_p("Версия", styles["small_bold"]), _p(str(version), styles["small"])],
        [_p("Валюта", styles["small_bold"]), _p(spec.currency, styles["small"])],
        [_p("Источник цен", styles["small_bold"]), _p(spec.source_summary, styles["small"])],
    ]
    independently_verified = bool(
        spec.normative_basis is not None
        and spec.normative_basis.validation_status == "verified"
        and all(line.provenance.validation_status == "verified" for line in spec.lines)
    )
    meta_rows.insert(0, [
        _p("Статус", styles["small_bold"]),
        _p(
            "Проверенная смета" if independently_verified else "Предварительная редактируемая смета",
            styles["small_bold"] if independently_verified else styles["warning"],
        ),
    ])
    if spec.client_name:
        meta_rows.insert(0, [_p("Клиент", styles["small_bold"]), _p(spec.client_name, styles["small"])])
    if spec.object_name or spec.object_address:
        value = " / ".join(item for item in (spec.object_name, spec.object_address) if item)
        meta_rows.insert(1, [_p("Объект", styles["small_bold"]), _p(value, styles["small"])])
    meta = Table(meta_rows, colWidths=[31 * mm, 149 * mm], hAlign="LEFT")
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E5F8FA")),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C5D5D8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D8E2E4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(meta)
    if not independently_verified:
        story.extend([
            Spacer(1, 2.5 * mm),
            _p(
                "Суммы рассчитаны детерминированно из указанных объёмов и цен, но источники "
                "ещё не прошли независимую проверку. Документ нельзя выдавать за точную "
                "договорную или нормативно подтверждённую стоимость.",
                styles["warning"],
            ),
        ])
    story.append(Spacer(1, 7 * mm))

    calculated_lines = {item["id"]: item for item in calculation["lines"]}
    sections: dict[str, list[Any]] = defaultdict(list)
    for line in spec.lines:
        sections[line.section].append(line)
    line_number = 0
    for section, lines in sections.items():
        story.append(_p(section, styles["h2"]))
        rows: list[list[Any]] = [[
            _p("№", styles["small_bold"]),
            _p("Позиция", styles["small_bold"]),
            _p("Тип", styles["small_bold"]),
            _p("Ед.", styles["small_bold"]),
            _p("Кол-во", styles["small_bold"]),
            _p("Цена", styles["small_bold"]),
            _p("Сумма", styles["small_bold"]),
        ]]
        for line in lines:
            line_number += 1
            result = calculated_lines[line.id]
            source_parts = [line.provenance.source_ref or line.provenance.source]
            if line.provenance.price_level_date:
                source_parts.append(f"уровень цен {line.provenance.price_level_date}")
            if line.provenance.applicable_region:
                source_parts.append(line.provenance.applicable_region)
            if line.provenance.source_url:
                source_parts.append(line.provenance.source_url)
            source = "; ".join(item for item in source_parts if item)
            rows.append([
                _p(line_number, styles["small"]),
                Paragraph(escape(line.description) + (
                    f"<br/><font size='6.5' color='#657176'>Источник: {escape(source)}</font>"
                    if source else ""
                ), styles["small"]),
                _p(_CATEGORY_LABELS.get(line.category, "Прочее"), styles["small"]),
                _p(line.unit, styles["small"]),
                _p(result["quantity"], styles["small"]),
                _p(_money(line.unit_price_minor, spec.minor_unit, spec.currency), styles["small"]),
                _p(_money(result["line_total_minor"], spec.minor_unit, spec.currency), styles["small_bold"]),
            ])
        table = LongTable(
            rows,
            colWidths=[8 * mm, 59 * mm, 24 * mm, 13 * mm, 18 * mm, 27 * mm, 31 * mm],
            repeatRows=1,
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F5")),
            ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C5D5D8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E2E4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
        ]))
        story.extend([table, Spacer(1, 3 * mm)])

    totals = calculation["totals"]
    summary_rows: list[list[Any]] = []
    for category, amount in totals["categories_minor"].items():
        summary_rows.append([
            _p(_CATEGORY_LABELS.get(category, category), styles["body"]),
            _p(_money(amount, spec.minor_unit, spec.currency), styles["money"]),
        ])
    if calculation["overhead_rate_bps"]:
        summary_rows.append([
            _p(f"Накладные, {_rate(calculation['overhead_rate_bps'])}", styles["body"]),
            _p(_money(totals["overhead_minor"], spec.minor_unit, spec.currency), styles["money"]),
        ])
    if calculation["tax_rate_bps"]:
        summary_rows.append([
            _p(f"Налог, {_rate(calculation['tax_rate_bps'])}", styles["body"]),
            _p(_money(totals["tax_minor"], spec.minor_unit, spec.currency), styles["money"]),
        ])
    summary_rows.append([
        _p("Итого", styles["small_bold"]),
        _p(_money(totals["grand_total_minor"], spec.minor_unit, spec.currency), styles["money"]),
    ])
    summary = Table(summary_rows, colWidths=[105 * mm, 75 * mm], hAlign="RIGHT")
    summary.setStyle(TableStyle([
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.HexColor("#17B7C7")),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E5F8FA")),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([Spacer(1, 3 * mm), summary])

    closing: list[Any] = []
    if spec.assumptions or spec.questions:
        closing.extend([Spacer(1, 3 * mm), _p("Допущения и вопросы", styles["h2"])])
        assumptions = "<br/>".join(
            f"{index}. {escape(item)}" for index, item in enumerate(spec.assumptions, 1)
        ) or "Нет"
        questions = "<br/>".join(
            f"{index}. {escape(item)}" for index, item in enumerate(spec.questions, 1)
        ) or "Нет"
        notes = Table([
            [_p("Допущения", styles["small_bold"]), _p("Нужно уточнить", styles["small_bold"])],
            [Paragraph(assumptions, styles["small"]), Paragraph(questions, styles["small"])],
        ], colWidths=[90 * mm, 90 * mm])
        notes.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F5")),
            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#C5D5D8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E2E4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        closing.append(notes)

    closing.extend([
        Spacer(1, 5 * mm),
        _p(
            "Денежные итоги рассчитаны движком kolibri.decimal-minor-unit.v1. "
            "Модель предлагает состав, количество и цены, но не определяет итоговую сумму.",
            styles["small"],
        ),
        _p(f"Estimate ID: {estimate_id} / Version: {version}", styles["small"]),
        _p(f"Calculation SHA-256: {calculation_sha}", styles["small"]),
    ])
    story.append(KeepTogether(closing))
    footer = _page_footer(calculation_sha)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    if not path.is_file() or path.stat().st_size < 1_000:
        raise EstimateArtifactError("estimate_pdf_not_materialized")
    return path


def _display_hash(value: str) -> str:
    return " ".join(value[index:index + 8] for index in range(0, len(value), 8))


def generate_estimate_readiness_pdf(
    readiness: dict[str, Any],
    proof: dict[str, Any],
    output_path: str | Path,
) -> Path:
    """Generate a non-monetary input checklist bound to the readiness proof."""

    if readiness.get("status") != "needs_input":
        raise EstimateArtifactError("estimate_readiness_status_invalid")
    if readiness.get("monetary_status") != "not_calculated":
        raise EstimateArtifactError("estimate_readiness_money_status_invalid")
    if readiness.get("normative_verified") is not False:
        raise EstimateArtifactError("estimate_readiness_normative_status_invalid")
    readiness_sha = str(proof.get("readiness_sha256") or "").lower()
    task_binding_sha = str(proof.get("binding_sha256") or "").lower()
    input_facts_sha = str(proof.get("input_facts_sha256") or "").lower()
    if not all(_SHA256.fullmatch(value) for value in (
        readiness_sha, task_binding_sha, input_facts_sha,
    )):
        raise EstimateArtifactError("estimate_readiness_binding_invalid")
    if readiness_sha != _sha(_canonical_json(readiness)):
        raise EstimateArtifactError("estimate_readiness_hash_mismatch")

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    title = str(readiness.get("title") or "Исходные данные для сметы")
    doc = SimpleDocTemplate(
        str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=18 * mm,
        title=title, author="Kolibri AI",
        subject="Чеклист исходных данных для достоверной сметы",
    )
    story: list[Any] = [
        _p("KOLIBRI AI / ПРОВЕРКА ГОТОВНОСТИ СМЕТЫ", styles["eyebrow"]),
        _p(title, styles["title"]),
    ]

    status = Table([
        [_p("Статус", styles["small_bold"]), _p("Нужны исходные данные", styles["warning"])],
        [_p("Денежный итог", styles["small_bold"]), _p("Не рассчитан", styles["warning"])],
        [_p("Нормативная проверка", styles["small_bold"]), _p("Не пройдена", styles["warning"])],
    ], colWidths=[48 * mm, 132 * mm], hAlign="LEFT")
    status.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#FFF4E8")),
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#FFF9F2")),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E1A86F")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#EFD0B2")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([
        status,
        Spacer(1, 4 * mm),
        _p(
            "Этот PDF не является сметой, коммерческим предложением или основанием для договора. "
            "Он фиксирует известные факты и полный перечень документов, без которых денежный "
            "расчёт был бы неподтверждённым.",
            styles["body"],
        ),
        Spacer(1, 3 * mm),
        _p("Зафиксированные факты", styles["h2"]),
    ])

    fact_labels = {
        "object_type_label": "Объект",
        "storeys": "Этажность",
        "gross_area_m2": "Общая площадь, м²",
        "region": "Регион",
        "locality": "Населённый пункт",
        "estimate_title": "Название",
        "object_name": "Наименование объекта",
        "object_address": "Адрес объекта",
        "currency": "Валюта будущего расчёта",
    }
    facts = readiness.get("known_facts") if isinstance(readiness.get("known_facts"), dict) else {}
    fact_rows = [
        [_p(fact_labels[key], styles["small_bold"]), _p(value, styles["small"])]
        for key, value in facts.items()
        if key in fact_labels and value not in (None, "")
    ]
    if not fact_rows:
        fact_rows = [[_p("Факты", styles["small_bold"]), _p("Требуют подтверждения", styles["small"])]]
    facts_table = Table(fact_rows, colWidths=[48 * mm, 132 * mm], hAlign="LEFT")
    facts_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#E5F8FA")),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C5D5D8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E2E4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([facts_table, Spacer(1, 4 * mm), _p("Что нужно предоставить", styles["h2"])])

    editor = readiness.get("editor") if isinstance(readiness.get("editor"), dict) else {}
    fields = editor.get("fields") if isinstance(editor.get("fields"), list) else []
    field_labels = {
        str(item.get("id")): str(item.get("label") or item.get("id"))
        for item in fields if isinstance(item, dict) and item.get("id")
    }
    required_inputs = readiness.get("required_inputs")
    if not isinstance(required_inputs, list) or not required_inputs:
        raise EstimateArtifactError("estimate_readiness_inputs_missing")
    input_rows: list[list[Any]] = [[
        _p("Раздел", styles["small_bold"]),
        _p("Нужные данные", styles["small_bold"]),
        _p("Подтверждение", styles["small_bold"]),
    ]]
    for group in required_inputs:
        if not isinstance(group, dict):
            raise EstimateArtifactError("estimate_readiness_input_invalid")
        labels = ", ".join(
            field_labels.get(str(field), str(field))
            for field in group.get("fields", [])
        )
        input_rows.append([
            _p(group.get("label") or group.get("id"), styles["small_bold"]),
            _p(labels, styles["small"]),
            _p(group.get("evidence") or "Требуется документ-основание.", styles["small"]),
        ])
    inputs_table = LongTable(
        input_rows, colWidths=[42 * mm, 64 * mm, 74 * mm], repeatRows=1,
    )
    inputs_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F5")),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C5D5D8")),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E2E4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([inputs_table, Spacer(1, 4 * mm)])

    gate = readiness.get("normative_gate") if isinstance(readiness.get("normative_gate"), dict) else {}
    basis = gate.get("required_basis") if isinstance(gate.get("required_basis"), list) else []
    if basis:
        story.append(_p("Контроль расчётной базы", styles["h2"]))
        for index, item in enumerate(basis, 1):
            story.append(_p(f"{index}. {item}", styles["body"]))
    references = gate.get("official_references") if isinstance(gate.get("official_references"), list) else []
    if references:
        story.append(_p("Официальные справочные источники", styles["h2"]))
        for reference in references:
            if not isinstance(reference, dict):
                continue
            story.append(_p(
                f"{reference.get('title', 'Источник')}: {reference.get('url', '')}",
                styles["small"],
            ))

    sections = readiness.get("draft_sections") if isinstance(readiness.get("draft_sections"), list) else []
    if sections:
        story.append(_p("Разделы будущей сметы", styles["h2"]))
        section_rows = [[_p("№", styles["small_bold"]), _p("Раздел", styles["small_bold"]), _p("Состояние", styles["small_bold"])]]
        for index, section in enumerate(sections, 1):
            section_rows.append([
                _p(index, styles["small"]),
                _p(section.get("label") if isinstance(section, dict) else section, styles["small"]),
                _p("Состав не подтверждён", styles["small"]),
            ])
        sections_table = Table(section_rows, colWidths=[10 * mm, 120 * mm, 50 * mm], repeatRows=1)
        sections_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F5")),
            ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#C5D5D8")),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D8E2E4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(sections_table)

    story.extend([
        Spacer(1, 5 * mm),
        _p("Контроль целостности", styles["h2"]),
        _p(f"Input facts SHA-256: {_display_hash(input_facts_sha)}", styles["hash"]),
        _p(f"Readiness SHA-256: {_display_hash(readiness_sha)}", styles["hash"]),
        _p(f"Task binding SHA-256: {_display_hash(task_binding_sha)}", styles["hash"]),
        Spacer(1, 2 * mm),
        _p(
            "После получения документов сметчик должен проверить их применимость, редакции и "
            "взаимную согласованность. Только затем допустим денежный расчёт.",
            styles["small"],
        ),
    ])
    footer = _page_footer(task_binding_sha, label="Проверка")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    if not path.is_file() or path.stat().st_size < 1_000:
        raise EstimateArtifactError("estimate_readiness_pdf_not_materialized")
    return path


class EstimateArtifactStore:
    def __init__(self, db_path: str | Path, artifact_root: str | Path):
        self.db_path = str(db_path)
        self.artifact_root = Path(artifact_root).expanduser().resolve()
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS public_estimates (
                    estimate_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    source_response_id TEXT NOT NULL,
                    current_version INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_public_estimates_session
                    ON public_estimates(session_id, updated_at);
                CREATE TABLE IF NOT EXISTS public_estimate_versions (
                    version_id TEXT PRIMARY KEY,
                    estimate_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    spec_json TEXT NOT NULL,
                    calculation_json TEXT NOT NULL,
                    spec_sha256 TEXT NOT NULL,
                    calculation_sha256 TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(estimate_id, version),
                    UNIQUE(session_id, response_id),
                    FOREIGN KEY(estimate_id) REFERENCES public_estimates(estimate_id)
                );
                CREATE TABLE IF NOT EXISTS public_estimate_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    estimate_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    estimate_version INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    reference_sha256 TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    FOREIGN KEY(estimate_id) REFERENCES public_estimates(estimate_id),
                    FOREIGN KEY(version_id) REFERENCES public_estimate_versions(version_id)
                );
                CREATE INDEX IF NOT EXISTS idx_public_estimate_artifacts_session
                    ON public_estimate_artifacts(session_id, created_at);
                CREATE TABLE IF NOT EXISTS public_estimate_readiness_artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    response_id TEXT NOT NULL,
                    request_source_sha256 TEXT NOT NULL,
                    readiness_sha256 TEXT NOT NULL,
                    task_binding_sha256 TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    reference_sha256 TEXT NOT NULL,
                    binding_sha256 TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    storage_path TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(session_id, response_id)
                );
                CREATE INDEX IF NOT EXISTS idx_public_estimate_readiness_artifacts_session
                    ON public_estimate_readiness_artifacts(session_id, created_at);
                """
            )

    def _cleanup(self, connection: sqlite3.Connection, now: float) -> None:
        expired_estimates = connection.execute(
            "SELECT DISTINCT storage_path FROM public_estimate_artifacts WHERE expires_at <= ?",
            (now,),
        ).fetchall()
        expired_readiness = connection.execute(
            "SELECT DISTINCT storage_path FROM public_estimate_readiness_artifacts WHERE expires_at <= ?",
            (now,),
        ).fetchall()
        connection.execute("DELETE FROM public_estimate_artifacts WHERE expires_at <= ?", (now,))
        connection.execute(
            "DELETE FROM public_estimate_readiness_artifacts WHERE expires_at <= ?", (now,),
        )
        connection.execute("DELETE FROM public_estimate_versions WHERE expires_at <= ?", (now,))
        connection.execute("DELETE FROM public_estimates WHERE expires_at <= ?", (now,))
        expired_paths = {
            str(row["storage_path"]) for row in [*expired_estimates, *expired_readiness]
        }
        for storage_path in expired_paths:
            remaining_estimate = connection.execute(
                "SELECT 1 FROM public_estimate_artifacts WHERE storage_path = ? LIMIT 1",
                (storage_path,),
            ).fetchone()
            remaining_readiness = connection.execute(
                "SELECT 1 FROM public_estimate_readiness_artifacts WHERE storage_path = ? LIMIT 1",
                (storage_path,),
            ).fetchone()
            if remaining_estimate is None and remaining_readiness is None:
                path = Path(storage_path).resolve()
                if path.is_relative_to(self.artifact_root):
                    path.unlink(missing_ok=True)

    @staticmethod
    def _artifact_public(
        row: sqlite3.Row | dict[str, Any],
        *,
        estimate_title: Any = None,
    ) -> dict[str, Any]:
        get = row.__getitem__
        version = int(get("estimate_version"))
        return {
            "id": get("artifact_id"),
            "schema_version": ARTIFACT_SCHEMA,
            "kind": "pdf",
            "name": _estimate_pdf_name(estimate_title, version),
            "locator": f"/v1/public/estimate-artifacts/{get('artifact_id')}/content",
            "media_type": get("media_type"),
            "reference_sha256": get("reference_sha256"),
            "content_sha256": get("content_sha256"),
            "size_bytes": int(get("size_bytes")),
            "deliverable_type": "pdf",
            "evidence_binding_sha256": get("binding_sha256"),
            "status": "materialized",
            "immutable": True,
            "estimate_id": get("estimate_id"),
            "estimate_version": version,
        }

    @staticmethod
    def _readiness_artifact_public(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        get = row.__getitem__
        return {
            "id": get("artifact_id"),
            "schema_version": READINESS_ARTIFACT_SCHEMA,
            "kind": "pdf",
            "name": "Смета — чек-лист исходных данных.pdf",
            "locator": f"/v1/public/estimate-artifacts/{get('artifact_id')}/content",
            "media_type": get("media_type"),
            "reference_sha256": get("reference_sha256"),
            "content_sha256": get("content_sha256"),
            "size_bytes": int(get("size_bytes")),
            "deliverable_type": "pdf",
            "evidence_binding_sha256": get("binding_sha256"),
            "status": "materialized",
            "immutable": True,
            "readiness_sha256": get("readiness_sha256"),
            "task_binding_sha256": get("task_binding_sha256"),
            "document_role": "estimate_input_checklist",
        }

    def _version_public(
        self,
        version_row: sqlite3.Row,
        artifact_row: sqlite3.Row | None,
    ) -> dict[str, Any]:
        spec = json.loads(version_row["spec_json"])
        return {
            "schema_version": ESTIMATE_SCHEMA,
            "id": version_row["estimate_id"],
            "version_id": version_row["version_id"],
            "version": int(version_row["version"]),
            "project_id": version_row["project_id"],
            "response_id": version_row["response_id"],
            "state": "saved",
            "spec": spec,
            "calculation": json.loads(version_row["calculation_json"]),
            "spec_sha256": version_row["spec_sha256"],
            "calculation_sha256": version_row["calculation_sha256"],
            "artifacts": [
                self._artifact_public(artifact_row, estimate_title=spec.get("title"))
            ] if artifact_row else [],
            "created_at": float(version_row["created_at"]),
        }

    def persist(
        self,
        *,
        session: dict[str, Any],
        response_id: str,
        spec: EstimateSpec,
        calculation: dict[str, Any],
        estimate_id: str | None,
        base_version: int | None,
        materialize_pdf: bool,
    ) -> dict[str, Any]:
        expected = deterministic_estimate(spec)
        if calculation != expected:
            raise EstimateArtifactError("estimate_calculation_mismatch")
        now = time.time()
        expires_at = float(session["expires_at"])
        spec_json = _canonical_json(spec.model_dump(mode="json"))
        calculation_json = _canonical_json(calculation)
        spec_sha = _sha(spec_json)
        calculation_sha = str(calculation["calculation_sha256"])
        if not _SHA256.fullmatch(calculation_sha):
            raise EstimateArtifactError("estimate_calculation_hash_invalid")

        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            existing_version = connection.execute(
                """SELECT * FROM public_estimate_versions
                   WHERE session_id = ? AND response_id = ?""",
                (session["id"], response_id),
            ).fetchone()
            if existing_version is not None:
                if existing_version["spec_sha256"] != spec_sha:
                    raise EstimateVersionConflict("response_id_reused_with_different_estimate")
                artifact = connection.execute(
                    "SELECT * FROM public_estimate_artifacts WHERE version_id = ?",
                    (existing_version["version_id"],),
                ).fetchone()
                return self._version_public(existing_version, artifact)

            if estimate_id:
                estimate = connection.execute(
                    """SELECT * FROM public_estimates
                       WHERE estimate_id = ? AND session_id = ? AND project_id = ?""",
                    (estimate_id, session["id"], session["project_id"]),
                ).fetchone()
                if estimate is None:
                    raise EstimateVersionConflict("estimate_not_found_in_session")
                current_version = int(estimate["current_version"])
                if base_version is None or base_version != current_version:
                    raise EstimateVersionConflict("estimate_version_conflict")
                version = current_version + 1
            else:
                estimate_id = _opaque_id("estimate")
                version = 1
                connection.execute(
                    """INSERT INTO public_estimates
                       (estimate_id, session_id, project_id, source_response_id,
                        current_version, created_at, updated_at, expires_at)
                       VALUES (?, ?, ?, ?, 0, ?, ?, ?)""",
                    (
                        estimate_id, session["id"], session["project_id"], response_id,
                        now, now, expires_at,
                    ),
                )
            version_id = _opaque_id("estimate_version")
            connection.execute(
                """INSERT INTO public_estimate_versions
                   (version_id, estimate_id, session_id, project_id, response_id,
                    version, spec_json, calculation_json, spec_sha256,
                    calculation_sha256, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    version_id, estimate_id, session["id"], session["project_id"],
                    response_id, version, spec_json, calculation_json, spec_sha,
                    calculation_sha, now, expires_at,
                ),
            )
            artifact_row: sqlite3.Row | None = None
            if materialize_pdf:
                temporary = self.artifact_root / f".{uuid.uuid4().hex}.pdf"
                try:
                    generate_estimate_pdf(
                        spec, calculation, temporary,
                        estimate_id=estimate_id, version=version,
                    )
                    content = temporary.read_bytes()
                    content_sha = _sha(content)
                    storage_path = self.artifact_root / f"{content_sha}.pdf"
                    if storage_path.exists():
                        temporary.unlink(missing_ok=True)
                    else:
                        os.replace(temporary, storage_path)
                        storage_path.chmod(0o444)
                    artifact_id = _opaque_id("artifact")
                    locator = f"/v1/public/estimate-artifacts/{artifact_id}/content"
                    binding_payload = {
                        "schema_version": ARTIFACT_SCHEMA,
                        "session_id": session["id"],
                        "project_id": session["project_id"],
                        "response_id": response_id,
                        "estimate_id": estimate_id,
                        "estimate_version": version,
                        "version_id": version_id,
                        "spec_sha256": spec_sha,
                        "calculation_sha256": calculation_sha,
                        "content_sha256": content_sha,
                        "size_bytes": len(content),
                    }
                    binding_sha = _sha(_canonical_json(binding_payload))
                    reference_sha = _sha(_canonical_json({
                        "artifact_id": artifact_id,
                        "locator": locator,
                        "content_sha256": content_sha,
                        "binding_sha256": binding_sha,
                    }))
                    connection.execute(
                        """INSERT INTO public_estimate_artifacts
                           (artifact_id, estimate_id, version_id, session_id, project_id,
                            response_id, estimate_version, media_type, content_sha256,
                            reference_sha256, binding_sha256, size_bytes, storage_path,
                            created_at, expires_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 'application/pdf', ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            artifact_id, estimate_id, version_id, session["id"],
                            session["project_id"], response_id, version, content_sha,
                            reference_sha, binding_sha, len(content), str(storage_path),
                            now, expires_at,
                        ),
                    )
                    artifact_row = connection.execute(
                        "SELECT * FROM public_estimate_artifacts WHERE artifact_id = ?",
                        (artifact_id,),
                    ).fetchone()
                finally:
                    temporary.unlink(missing_ok=True)
            connection.execute(
                """UPDATE public_estimates
                   SET current_version = ?, updated_at = ?, expires_at = ?
                   WHERE estimate_id = ?""",
                (version, now, expires_at, estimate_id),
            )
            version_row = connection.execute(
                "SELECT * FROM public_estimate_versions WHERE version_id = ?",
                (version_id,),
            ).fetchone()
            assert version_row is not None
            return self._version_public(version_row, artifact_row)

    def persist_readiness_artifact(
        self,
        *,
        session: dict[str, Any],
        response_id: str,
        readiness: dict[str, Any],
        proof: dict[str, Any],
    ) -> dict[str, Any]:
        readiness_sha = str(proof.get("readiness_sha256") or "").lower()
        task_binding_sha = str(proof.get("binding_sha256") or "").lower()
        input_facts_sha = str(proof.get("input_facts_sha256") or "").lower()
        input_facts = proof.get("input_facts") if isinstance(proof.get("input_facts"), dict) else {}
        request_source_sha = str(
            input_facts.get("request_brief_sha256")
            or input_facts.get("request_spec_sha256")
            or ""
        ).lower()
        if not all(_SHA256.fullmatch(value) for value in (
            readiness_sha, task_binding_sha, input_facts_sha, request_source_sha,
        )):
            raise EstimateArtifactError("estimate_readiness_binding_invalid")
        if readiness_sha != _sha(_canonical_json(readiness)):
            raise EstimateArtifactError("estimate_readiness_hash_mismatch")

        now = time.time()
        expires_at = float(session["expires_at"])
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            existing = connection.execute(
                """SELECT * FROM public_estimate_readiness_artifacts
                   WHERE session_id = ? AND response_id = ?""",
                (session["id"], response_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["readiness_sha256"] != readiness_sha
                    or existing["task_binding_sha256"] != task_binding_sha
                    or existing["request_source_sha256"] != request_source_sha
                ):
                    raise EstimateArtifactError("response_id_reused_with_different_readiness")
                return self._readiness_artifact_public(existing)

            temporary = self.artifact_root / f".{uuid.uuid4().hex}.pdf"
            try:
                generate_estimate_readiness_pdf(readiness, proof, temporary)
                content = temporary.read_bytes()
                content_sha = _sha(content)
                storage_path = self.artifact_root / f"{content_sha}.pdf"
                if storage_path.exists():
                    temporary.unlink(missing_ok=True)
                else:
                    os.replace(temporary, storage_path)
                    storage_path.chmod(0o444)
                artifact_id = _opaque_id("artifact")
                locator = f"/v1/public/estimate-artifacts/{artifact_id}/content"
                binding_payload = {
                    "schema_version": READINESS_ARTIFACT_SCHEMA,
                    "session_id": session["id"],
                    "project_id": session["project_id"],
                    "response_id": response_id,
                    "request_source_sha256": request_source_sha,
                    "input_facts_sha256": input_facts_sha,
                    "readiness_sha256": readiness_sha,
                    "task_binding_sha256": task_binding_sha,
                    "content_sha256": content_sha,
                    "size_bytes": len(content),
                }
                binding_sha = _sha(_canonical_json(binding_payload))
                reference_sha = _sha(_canonical_json({
                    "artifact_id": artifact_id,
                    "locator": locator,
                    "content_sha256": content_sha,
                    "binding_sha256": binding_sha,
                }))
                connection.execute(
                    """INSERT INTO public_estimate_readiness_artifacts
                       (artifact_id, session_id, project_id, response_id,
                        request_source_sha256, readiness_sha256, task_binding_sha256,
                        media_type, content_sha256, reference_sha256, binding_sha256,
                        size_bytes, storage_path, created_at, expires_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'application/pdf', ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        artifact_id, session["id"], session["project_id"], response_id,
                        request_source_sha, readiness_sha, task_binding_sha, content_sha,
                        reference_sha, binding_sha, len(content), str(storage_path), now,
                        expires_at,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM public_estimate_readiness_artifacts WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchone()
                assert row is not None
                return self._readiness_artifact_public(row)
            finally:
                temporary.unlink(missing_ok=True)

    def get_estimate(self, session_id: str, estimate_id: str) -> dict[str, Any] | None:
        now = time.time()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            estimate = connection.execute(
                """SELECT * FROM public_estimates
                   WHERE estimate_id = ? AND session_id = ? AND expires_at > ?""",
                (estimate_id, session_id, now),
            ).fetchone()
            if estimate is None:
                return None
            version = connection.execute(
                """SELECT * FROM public_estimate_versions
                   WHERE estimate_id = ? AND version = ?""",
                (estimate_id, estimate["current_version"]),
            ).fetchone()
            artifact = connection.execute(
                "SELECT * FROM public_estimate_artifacts WHERE version_id = ?",
                (version["version_id"],),
            ).fetchone()
        return self._version_public(version, artifact)

    def list_versions(self, session_id: str, estimate_id: str) -> list[dict[str, Any]] | None:
        now = time.time()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            owner = connection.execute(
                "SELECT 1 FROM public_estimates WHERE estimate_id = ? AND session_id = ?",
                (estimate_id, session_id),
            ).fetchone()
            if owner is None:
                return None
            versions = connection.execute(
                """SELECT * FROM public_estimate_versions
                   WHERE estimate_id = ? ORDER BY version DESC""",
                (estimate_id,),
            ).fetchall()
            result = []
            for version in versions:
                artifact = connection.execute(
                    "SELECT * FROM public_estimate_artifacts WHERE version_id = ?",
                    (version["version_id"],),
                ).fetchone()
                result.append(self._version_public(version, artifact))
        return result

    def artifact_content(self, session_id: str, artifact_id: str) -> tuple[dict[str, Any], bytes] | None:
        now = time.time()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT * FROM public_estimate_artifacts
                   WHERE artifact_id = ? AND session_id = ? AND expires_at > ?""",
                (artifact_id, session_id, now),
            ).fetchone()
            readiness_row = None
            estimate_title = None
            if row is not None:
                version_row = connection.execute(
                    "SELECT spec_json FROM public_estimate_versions WHERE version_id = ?",
                    (row["version_id"],),
                ).fetchone()
                if version_row is not None:
                    estimate_title = json.loads(version_row["spec_json"]).get("title")
            if row is None:
                readiness_row = connection.execute(
                    """SELECT * FROM public_estimate_readiness_artifacts
                       WHERE artifact_id = ? AND session_id = ? AND expires_at > ?""",
                    (artifact_id, session_id, now),
                ).fetchone()
        selected = row or readiness_row
        if selected is None:
            return None
        path = Path(selected["storage_path"]).resolve()
        if not path.is_relative_to(self.artifact_root) or not path.is_file():
            raise EstimateArtifactError("estimate_artifact_storage_boundary_violation")
        content = path.read_bytes()
        if len(content) != int(selected["size_bytes"]) or _sha(content) != selected["content_sha256"]:
            raise EstimateArtifactError("estimate_artifact_integrity_failed")
        artifact = (
            self._artifact_public(row, estimate_title=estimate_title)
            if row is not None
            else self._readiness_artifact_public(readiness_row)
        )
        return artifact, content


_STORE = EstimateArtifactStore(
    DB_PATH,
    os.environ.get(
        "KOLIBRI_ESTIMATE_ARTIFACT_ROOT",
        str(DATA_DIR / "artifacts" / "estimates"),
    ),
)


def configure_estimate_artifact_store(
    db_path: str | Path,
    artifact_root: str | Path,
) -> EstimateArtifactStore:
    global _STORE
    _STORE = EstimateArtifactStore(db_path, artifact_root)
    return _STORE


def get_estimate_artifact_store() -> EstimateArtifactStore:
    return _STORE


def materialize_public_estimate_task(
    *,
    session: dict[str, Any],
    response_id: str,
    task: dict[str, Any],
    request_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a verified estimate or readiness checklist and attach real PDF evidence.

    Provider proposals retain their content-bound provider/verifier gate.  A
    readiness result is accepted only after its request/readiness binding is
    independently recomputed by ``vertical_tasks``.  It never receives a
    monetary calculation and never upgrades ``provider_verified`` to true.
    """

    if task.get("intent") != "estimate":
        return task
    execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if result.get("type") == "estimate_readiness":
        from vertical_tasks import verified_deterministic_estimate_fallback

        if not verified_deterministic_estimate_fallback(task):
            return task
        requested = task.get("artifact_delivery", {}).get("requested", [])
        artifacts = list(task.get("artifacts") or [])
        if "pdf" in requested and not any(
            item.get("deliverable_type") == "pdf" for item in artifacts
            if isinstance(item, dict)
        ):
            artifact = _STORE.persist_readiness_artifact(
                session=session,
                response_id=response_id,
                readiness=result["readiness"],
                proof=result["generation"],
            )
            artifacts.append(artifact)
        delivered = sorted({
            str(item.get("deliverable_type"))
            for item in artifacts
            if isinstance(item, dict) and item.get("deliverable_type")
        })
        missing = [item for item in requested if item not in delivered]
        return {
            **task,
            # A complete PDF delivery does not make the estimate itself ready:
            # required project, quantity, pricing and tax inputs are still absent.
            "status": "incomplete",
            "artifacts": artifacts,
            "artifact_delivery": {
                "required": bool(requested),
                "status": (
                    "not_required" if not requested
                    else "materialized" if not missing
                    else "not_materialized"
                ),
                "requested": requested,
                "delivered": delivered,
                "missing": missing,
                "count": len(artifacts),
            },
        }
    provider_verified = (
        execution.get("provider_verified") is True
        and execution.get("status") == "completed"
    )
    engine_verified = False
    if not provider_verified:
        # Local import avoids making the estimate schema module depend on the
        # persistence layer while still sharing one proof verifier.
        from vertical_tasks import verified_deterministic_estimate_fallback

        engine_verified = verified_deterministic_estimate_fallback(task)
    if not (provider_verified or engine_verified):
        return task
    if result.get("type") != "deterministic_estimate":
        return task
    spec = EstimateSpec.model_validate(result.get("estimate"))
    calculation = result.get("calculation")
    if not isinstance(calculation, dict):
        raise EstimateArtifactError("estimate_calculation_missing")
    metadata = request_metadata if isinstance(request_metadata, dict) else {}
    estimate_id = metadata.get("estimate_id")
    if estimate_id is not None and not isinstance(estimate_id, str):
        raise EstimateVersionConflict("estimate_id_invalid")
    base_version = metadata.get("estimate_base_version")
    if base_version is not None and (not isinstance(base_version, int) or isinstance(base_version, bool)):
        raise EstimateVersionConflict("estimate_base_version_invalid")
    requested = task.get("artifact_delivery", {}).get("requested", [])
    materialize_pdf = "pdf" in requested
    persisted = _STORE.persist(
        session=session,
        response_id=response_id,
        spec=spec,
        calculation=calculation,
        estimate_id=estimate_id,
        base_version=base_version,
        materialize_pdf=materialize_pdf,
    )
    artifacts = list(task.get("artifacts") or [])
    artifacts.extend(persisted["artifacts"])
    delivered = sorted({str(item.get("deliverable_type")) for item in artifacts})
    missing = [item for item in requested if item not in delivered]
    return {
        **task,
        "status": "completed" if not missing else "incomplete",
        "result": {
            **result,
            "estimate": persisted["spec"],
            "calculation": persisted["calculation"],
        },
        "persistence": {
            "schema_version": ESTIMATE_SCHEMA,
            "estimate_id": persisted["id"],
            "version_id": persisted["version_id"],
            "version": persisted["version"],
            "state": "saved",
            "spec_sha256": persisted["spec_sha256"],
            "calculation_sha256": persisted["calculation_sha256"],
        },
        "artifacts": artifacts,
        "artifact_delivery": {
            "required": bool(requested),
            "status": (
                "not_required" if not requested
                else "materialized" if not missing
                else "not_materialized"
            ),
            "requested": requested,
            "delivered": delivered,
            "missing": missing,
            "count": len(artifacts),
        },
    }
