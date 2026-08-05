from __future__ import annotations

from decimal import Decimal
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from document_engine import BusinessDocument
from estimate_engine import Estimate, recalculate_estimate

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]


def register_cyrillic_font() -> str:
    for candidate in _FONT_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            font_name = "KolibriCyrillic"
            try:
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
            except Exception:
                pass
            return font_name
    return "Helvetica"


def _styles() -> dict[str, ParagraphStyle]:
    font_name = register_cyrillic_font()
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("KolibriTitle", parent=base["Title"], fontName=font_name, fontSize=17, leading=22, spaceAfter=8),
        "h2": ParagraphStyle("KolibriH2", parent=base["Heading2"], fontName=font_name, fontSize=12, leading=16, spaceBefore=10, spaceAfter=5),
        "body": ParagraphStyle("KolibriBody", parent=base["BodyText"], fontName=font_name, fontSize=9, leading=12),
        "small": ParagraphStyle("KolibriSmall", parent=base["BodyText"], fontName=font_name, fontSize=8, leading=10),
    }


def _p(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _money(value: Decimal | str) -> str:
    return f"{Decimal(str(value)):.2f}"


def generate_estimate_pdf(estimate: Estimate, output_path: str | Path) -> Path:
    estimate = recalculate_estimate(estimate)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    story = [_p(estimate.title, styles["title"]), _p(f"Клиент: {estimate.client_name}", styles["body"]), _p(f"Объект: {estimate.object_address}", styles["body"]), Spacer(1, 6)]
    for section in estimate.sections:
        story.append(_p(section.title, styles["h2"]))
        rows = [[_p("Наименование", styles["small"]), _p("Кол-во", styles["small"]), _p("Работы", styles["small"]), _p("Материалы", styles["small"]), _p("Итого", styles["small"])]]
        for item in section.items:
            rows.append([_p(item.name, styles["small"]), _p(f"{item.quantity} {item.unit}", styles["small"]), _p(_money(item.labor_total()), styles["small"]), _p(_money(item.material_total()), styles["small"]), _p(_money(item.line_total()), styles["small"])])
        table = Table(rows, colWidths=[72 * mm, 24 * mm, 24 * mm, 26 * mm, 26 * mm])
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF4F8")), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BAC7D1")), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
        story.append(table)
    totals = estimate.totals
    story.extend([Spacer(1, 10), _p(f"Работы: {_money(totals.labor)} {estimate.currency}", styles["body"]), _p(f"Материалы: {_money(totals.materials)} {estimate.currency}", styles["body"]), _p(f"Итого: {_money(totals.grand_total)} {estimate.currency}", styles["h2"]), _p(f"Audit fingerprint: {estimate.calculation_audit[-1]['fingerprint']}", styles["small"])])
    doc.build(story)
    return path


def generate_business_document_pdf(document: BusinessDocument, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    story = [
        _p(document.title, styles["title"]),
        _p(f"Заказчик: {document.client_name}", styles["body"]),
        _p(f"Подрядчик / отправитель: {document.contractor_name}", styles["body"]),
        _p(f"Основание расчёта: смета {document.estimate_id}", styles["body"]),
        Spacer(1, 8),
    ]
    for section in document.body_sections:
        story.append(_p(section.get("title", "Раздел"), styles["h2"]))
        story.append(_p(section.get("text", ""), styles["body"]))
        section_rows = section.get("rows")
        if isinstance(section_rows, list) and section_rows:
            rows = [[
                _p("Раздел", styles["small"]),
                _p("Позиция", styles["small"]),
                _p("Ед.", styles["small"]),
                _p("Объём", styles["small"]),
                _p("Сумма", styles["small"]),
            ]]
            for row in section_rows:
                rows.append([
                    _p(row.get("section", ""), styles["small"]),
                    _p(row.get("item", ""), styles["small"]),
                    _p(row.get("unit", ""), styles["small"]),
                    _p(row.get("quantity", ""), styles["small"]),
                    _p(row.get("total", ""), styles["small"]),
                ])
            table = Table(rows, colWidths=[27 * mm, 72 * mm, 15 * mm, 20 * mm, 25 * mm], repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F3F5")),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#C9CDD2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.extend([Spacer(1, 5), table])
    if document.attachments:
        story.append(_p("Приложения", styles["h2"]))
        for attachment in document.attachments:
            story.append(_p(f"• {attachment}", styles["body"]))
    if document.missing_fields:
        story.append(_p("Перед подписанием требуется заполнить и проверить", styles["h2"]))
        for field in document.missing_fields:
            story.append(_p(f"• {field}", styles["body"]))
    story.extend([
        Spacer(1, 12),
        _p(f"Сумма документа: {document.total} {document.currency}", styles["h2"]),
        _p(f"Оформление: {document.document_standard}. Требуется проверка уполномоченным лицом перед подписанием.", styles["small"]),
    ])
    doc.build(story)
    return path
