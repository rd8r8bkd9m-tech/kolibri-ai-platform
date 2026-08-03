"""Deterministic official_ru_v1 document renderers.

All renderers consume the immutable snapshot contract.  They never query the
database, read URLs, or derive totals from mutable project state.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from html import escape
import io
import json
from pathlib import Path
import zipfile
from typing import Any, Iterable, Mapping

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    LongTable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from .estimate_document_pack import DocumentPackError, RenderedDocumentFile


RENDERER_VERSION = "official_ru_v1"
_ROOT = Path(__file__).resolve().parents[1]
_FONT_DIR = _ROOT / "assets" / "fonts"
_PET_MARK = _ROOT.parent / "public" / "pets" / "masters" / "kolibri-v1.png"
_FONT_REGULAR = "KolibriNotoSans"
_FONT_BOLD = "KolibriNotoSansBold"
_INK = colors.HexColor("#10241D")
_TEAL = colors.HexColor("#128F88")
_MUTED = colors.HexColor("#66756D")
_LINE = colors.HexColor("#A8B4AE")
_LINE_LIGHT = colors.HexColor("#D7DEDA")
_FILL = colors.HexColor("#F2F5F3")
_FILL_DARK = colors.HexColor("#E5EBE8")
_WHITE = colors.white
_BLACK = colors.HexColor("#111111")
_MONEY_Q = 2


def _register_fonts() -> None:
    if _FONT_REGULAR not in pdfmetrics.getRegisteredFontNames():
        regular = _FONT_DIR / "NotoSans-Regular.ttf"
        bold = _FONT_DIR / "NotoSans-Bold.ttf"
        if not regular.is_file() or not bold.is_file():
            raise DocumentPackError(
                "document_font_missing",
                "Unicode-шрифт документа не установлен в release.",
                status_code=503,
            )
        pdfmetrics.registerFont(TTFont(_FONT_REGULAR, str(regular)))
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(bold)))


def _money(value: object) -> str:
    try:
        amount = float(str(value))
    except (TypeError, ValueError):
        amount = 0.0
    whole, cents = f"{amount:,.2f}".split(".")
    return f"{whole.replace(',', ' ')},{cents} руб."


def _quantity(value: object) -> str:
    raw = str(value)
    try:
        parsed = float(raw)
    except ValueError:
        return raw
    if parsed.is_integer():
        return f"{int(parsed):,}".replace(",", " ")
    return raw.replace(".", ",")


def _status_label(source: Mapping[str, Any]) -> str:
    source_type = str(source.get("sourceType") or "")
    if bool(source.get("stale")):
        return "STALE"
    if source_type == "ai_preliminary":
        return "AI PRELIM."
    if source_type in {"verified", "customer_approved"}:
        return "VERIFIED"
    return "SOURCE-BACKED"


def _p(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "body": ParagraphStyle("OfficialBody", parent=base["Normal"], fontName=_FONT_REGULAR, fontSize=8.1, leading=10.5, textColor=_BLACK),
        "small": ParagraphStyle("OfficialSmall", parent=base["Normal"], fontName=_FONT_REGULAR, fontSize=6.6, leading=8.5, textColor=_MUTED),
        "bold": ParagraphStyle("OfficialBold", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=8.1, leading=10.5, textColor=_INK),
        "title": ParagraphStyle("OfficialTitle", parent=base["Title"], fontName=_FONT_BOLD, fontSize=14, leading=17, textColor=_INK, alignment=TA_CENTER, spaceAfter=3),
        "subtitle": ParagraphStyle("OfficialSubtitle", parent=base["Normal"], fontName=_FONT_REGULAR, fontSize=8, leading=10.5, textColor=_BLACK, alignment=TA_CENTER),
        "section": ParagraphStyle("OfficialSection", parent=base["Heading2"], fontName=_FONT_BOLD, fontSize=9.2, leading=12, textColor=_INK, spaceBefore=2, spaceAfter=4, keepWithNext=True),
        "cell": ParagraphStyle("OfficialCell", parent=base["Normal"], fontName=_FONT_REGULAR, fontSize=6.5, leading=8.2, textColor=_BLACK),
        "cell_bold": ParagraphStyle("OfficialCellBold", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=6.5, leading=8.2, textColor=_INK),
        "cell_right": ParagraphStyle("OfficialCellRight", parent=base["Normal"], fontName=_FONT_REGULAR, fontSize=6.5, leading=8.2, textColor=_BLACK, alignment=TA_RIGHT),
        "cell_right_bold": ParagraphStyle("OfficialCellRightBold", parent=base["Normal"], fontName=_FONT_BOLD, fontSize=6.5, leading=8.2, textColor=_INK, alignment=TA_RIGHT),
    }


def _frame(snapshot: Mapping[str, Any]):
    document = snapshot["document"]
    number = str(document["number"])
    version = str(snapshot["estimateVersion"])

    def draw(page_canvas: canvas.Canvas, _doc: SimpleDocTemplate) -> None:
        width, height = A4
        page_canvas.saveState()
        if not _PET_MARK.is_file():
            raise DocumentPackError("document_mascot_missing", "Канонический mascot не найден в release.", status_code=503)
        page_canvas.drawImage(str(_PET_MARK), 18 * mm, height - 18 * mm, width=12 * mm, height=12 * mm, preserveAspectRatio=True, mask="auto")
        page_canvas.setStrokeColor(_TEAL)
        page_canvas.setLineWidth(0.7)
        page_canvas.line(18 * mm, height - 18 * mm, width - 18 * mm, height - 18 * mm)
        page_canvas.setStrokeColor(_LINE_LIGHT)
        page_canvas.setLineWidth(0.4)
        page_canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
        page_canvas.setFont(_FONT_REGULAR, 6.1)
        page_canvas.setFillColor(_MUTED)
        page_canvas.drawString(18 * mm, 9.5 * mm, f"{number} / версия {version}")
        page_canvas.drawRightString(width - 18 * mm, 9.5 * mm, f"Лист {page_canvas.getPageNumber()}")
        page_canvas.restoreState()

    return draw


def _table(data: list[list[Any]], widths: list[float], *, repeat_rows: int = 1, header_fill: colors.Color = _FILL) -> LongTable:
    table = LongTable(data, colWidths=widths, repeatRows=repeat_rows, splitByRow=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, repeat_rows - 1), _FONT_BOLD),
        ("BACKGROUND", (0, 0), (-1, repeat_rows - 1), header_fill),
        ("TEXTCOLOR", (0, 0), (-1, repeat_rows - 1), _INK),
        ("GRID", (0, 0), (-1, -1), 0.3, _LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _header(snapshot: Mapping[str, Any], styles: Mapping[str, ParagraphStyle], title: str, subtitle: str | None = None) -> list[Any]:
    document = snapshot["document"]
    project = snapshot["project"]
    object_info = snapshot["object"]
    status = str(document["status"]).upper()
    if document.get("mode") == "preliminary":
        status = "PRELIMINARY"
    block: list[Any] = [
        Spacer(1, 5 * mm),
        _p(title, styles["title"]),
        _p(subtitle or f"№ {document['number']} · версия сметы {snapshot['estimateVersion']}", styles["subtitle"]),
        Spacer(1, 3 * mm),
    ]
    meta = [
        [_p("Исполнитель", styles["bold"]), _p((snapshot.get("contractor") or {}).get("displayName", "Не назначен"), styles["body"]), _p("Заказчик", styles["bold"]), _p((snapshot.get("customer") or {}).get("displayName", "Не назначен"), styles["body"])],
        [_p("Объект", styles["bold"]), _p(object_info.get("name") or project["title"], styles["body"]), _p("Регион", styles["bold"]), _p(object_info.get("resolvedLocation") or "Требуется уточнить", styles["body"])],
        [_p("Дата", styles["bold"]), _p(document["date"], styles["body"]), _p("Статус", styles["bold"]), _p(status, styles["body"])],
    ]
    block.append(_table(meta, [23 * mm, 64 * mm, 23 * mm, 64 * mm], repeat_rows=0, header_fill=_FILL))
    block.append(Spacer(1, 5 * mm))
    return block


def _commercial_page(snapshot: Mapping[str, Any], styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    block = _header(snapshot, styles, "КОММЕРЧЕСКАЯ СМЕТА", f"Срок действия: до {snapshot['document']['validUntil']}")
    summary = [[_p("№", styles["bold"]), _p("Раздел", styles["bold"]), _p("Работы", styles["bold"]), _p("Материалы", styles["bold"]), _p("Итого", styles["bold"])]]
    by_section: OrderedDict[str, dict[str, float]] = OrderedDict()
    for line in snapshot["lines"]:
        section = str(line["section"])
        item = by_section.setdefault(section, {"work": 0.0, "material": 0.0, "total": 0.0})
        total = float(str(line["lineTotal"]))
        item["total"] += total
        if str(line["kind"]) in {"work", "service"}:
            item["work"] += total
        else:
            item["material"] += total
    for index, (section, values) in enumerate(by_section.items(), start=1):
        summary.append([_p(index, styles["cell"]), _p(section, styles["cell"]), _p(_money(values["work"]), styles["cell_right"]), _p(_money(values["material"]), styles["cell_right"]), _p(_money(values["total"]), styles["cell_right_bold"])])
    summary.append(["", _p("Прямые затраты", styles["cell_bold"]), "", "", _p(_money(snapshot["commercialTerms"]["directTotal"]), styles["cell_right_bold"])])
    summary.append(["", _p(f"Резерв {snapshot['commercialTerms']['reservePercent']}%", styles["cell_bold"]), "", "", _p(_money(snapshot["commercialTerms"]["reserve"]), styles["cell_right_bold"])])
    summary.append(["", _p("Итого к оплате", styles["cell_bold"]), "", "", _p(_money(snapshot["commercialTerms"]["total"]), styles["cell_right_bold"])])
    table = _table(summary, [10 * mm, 55 * mm, 30 * mm, 30 * mm, 49 * mm])
    table.setStyle(TableStyle([
        ("LINEABOVE", (0, -3), (-1, -3), 0.7, _TEAL),
        ("BACKGROUND", (0, -1), (-1, -1), _FILL_DARK),
        ("LINEABOVE", (0, -1), (-1, -1), 1, _INK),
    ]))
    block.extend([_p("Сводный расчёт стоимости", styles["section"]), table, Spacer(1, 5 * mm)])
    totals = [
        [_p("Сметная стоимость", styles["bold"]), _p(_money(snapshot["commercialTerms"]["total"]), styles["cell_right_bold"])],
        [_p("Сумма прописью", styles["bold"]), _p(str(snapshot["commercialTerms"]["totalWords"]), styles["body"])],
        [_p("Налоговый режим", styles["bold"]), _p(snapshot["commercialTerms"]["taxMode"], styles["body"])],
    ]
    block.append(_table(totals, [45 * mm, 129 * mm], repeat_rows=0))
    block.extend([Spacer(1, 8 * mm), _p("Условия и границы расчёта", styles["section"])])
    conditions = snapshot.get("calculationConditions") or ["Исходные данные и цены требуют проверки перед заключением договора."]
    block.extend(_conditions_list(conditions, styles))
    return block


def _conditions_list(values: Iterable[object], styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    result: list[Any] = []
    for index, value in enumerate(values, start=1):
        result.append(_p(f"{index}. {value}", styles["body"]))
        result.append(Spacer(1, 1.2 * mm))
    return result


def _line_table(snapshot: Mapping[str, Any], styles: Mapping[str, ParagraphStyle], *, title: str) -> list[Any]:
    block: list[Any] = [_p(title, styles["section"])]
    header = [_p(value, styles["bold"]) for value in ["№", "Обоснование", "Наименование работ и затрат", "Ед.", "Кол-во", "Цена за ед., руб.", "Стоимость, руб."]]
    data: list[list[Any]] = [header]
    previous_section = None
    for line in snapshot["lines"]:
        section = str(line["section"])
        if section != previous_section:
            data.append([_p(section, styles["cell_bold"]), "", "", "", "", "", ""])
            previous_section = section
        data.append([
            _p(line["position"], styles["cell"]),
            _p(line.get("catalogEntryId") or line.get("priceObservationId") or "Расчётная строка", styles["cell"]),
            _p(line["description"], styles["cell"]),
            _p(line["unit"], styles["cell"]),
            _p(_quantity(line["quantity"]), styles["cell_right"]),
            _p(_money(line["unitPrice"]), styles["cell_right"]),
            _p(_money(line["lineTotal"]), styles["cell_right"]),
        ])
    data.append(["", "", _p("Итого", styles["cell_bold"]), "", "", "", _p(_money(snapshot["commercialTerms"]["directTotal"]), styles["cell_right_bold"])])
    table = _table(data, [8 * mm, 22 * mm, 54 * mm, 12 * mm, 16 * mm, 30 * mm, 32 * mm])
    for row_index, row in enumerate(data):
        if row_index and row[1] == "" and row[2] == "" and row[0] != "":
            table.setStyle(TableStyle([("SPAN", (0, row_index), (-1, row_index)), ("BACKGROUND", (0, row_index), (-1, row_index), _FILL_DARK), ("LINEABOVE", (0, row_index), (-1, row_index), 0.5, _TEAL)]))
    table.setStyle(TableStyle([("LINEABOVE", (0, -1), (-1, -1), 0.8, _TEAL), ("BACKGROUND", (0, -1), (-1, -1), _FILL_DARK)]))
    block.append(table)
    return block


def _resource_page(snapshot: Mapping[str, Any], styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    resources: OrderedDict[tuple[str, str], dict[str, Any]] = OrderedDict()
    for line in snapshot["lines"]:
        key = (str(line["description"]), str(line["unit"]))
        item = resources.setdefault(key, {"quantity": 0.0, "total": 0.0, "source": line["source"]})
        item["quantity"] += float(str(line["quantity"]))
        item["total"] += float(str(line["lineTotal"]))
    data: list[list[Any]] = [[_p(value, styles["bold"]) for value in ["№", "Код", "Наименование ресурса", "Ед.", "Кол-во", "Цена, руб.", "Стоимость, руб."]]]
    for index, ((description, unit), item) in enumerate(resources.items(), start=1):
        data.append([_p(index, styles["cell"]), _p("RES-" + str(index).zfill(3), styles["cell"]), _p(description, styles["cell"]), _p(unit, styles["cell"]), _p(_quantity(item["quantity"]), styles["cell_right"]), _p(_money(item["total"] / item["quantity"] if item["quantity"] else 0), styles["cell_right"]), _p(_money(item["total"]), styles["cell_right"])])
    data.append(["", "", _p("Итого по ведомости ресурсов", styles["cell_bold"]), "", "", "", _p(_money(snapshot["commercialTerms"]["directTotal"]), styles["cell_right_bold"])])
    return _header(snapshot, styles, "РЕСУРСНАЯ ВЕДОМОСТЬ", "Материалы, оборудование и механизмы с наборами исходных цен") + [_table(data, [8 * mm, 20 * mm, 60 * mm, 12 * mm, 16 * mm, 26 * mm, 32 * mm])]


def _analysis_page(snapshot: Mapping[str, Any], styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    data: list[list[Any]] = [[_p(value, styles["bold"]) for value in ["№", "Ресурс", "Источник", "Регион", "Дата цены", "Цена, руб.", "Статус"]]]
    for line in snapshot["lines"]:
        source = line["source"]
        data.append([_p(line["position"], styles["cell"]), _p(line["description"], styles["cell"]), _p(source.get("label"), styles["cell"]), _p(source.get("region") or snapshot["object"].get("region") or "Не указан", styles["cell"]), _p(source.get("observedAt") or "Не указана", styles["cell"]), _p(_money(line["unitPrice"]), styles["cell_right"]), _p(_status_label(source), styles["cell"])] )
    block = _header(snapshot, styles, "КОНЪЮНКТУРНЫЙ АНАЛИЗ", "Сведения обо всех источниках применённых цен")
    block.extend([_table(data, [8 * mm, 39 * mm, 34 * mm, 28 * mm, 22 * mm, 25 * mm, 18 * mm]), Spacer(1, 5 * mm), _p("Статус документа", styles["bold"]), _p("PRELIMINARY — предварительные цены требуют подтверждения." if snapshot["document"]["mode"] == "preliminary" else "SOURCE-BACKED / VERIFIED — цены прошли проверку выпуска.", styles["body"])])
    return block


def _appendix_page(snapshot: Mapping[str, Any], styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    block = _header(snapshot, styles, "ПРИЛОЖЕНИЕ № 1", "График платежей и условия/границы расчёта")
    schedule = [[_p(value, styles["bold"]) for value in ["№", "Этап", "Доля, %", "Основание платежа"]]]
    for index, item in enumerate(snapshot["commercialTerms"]["paymentSchedule"], start=1):
        schedule.append([_p(index, styles["cell"]), _p(item["label"], styles["cell"]), _p(item["percent"], styles["cell_right"]), _p("По условиям договора", styles["cell"])])
    block.extend([_p("1. График этапов и платежей", styles["section"]), _table(schedule, [10 * mm, 73 * mm, 24 * mm, 67 * mm]), Spacer(1, 5 * mm), _p("2. Условия и границы расчёта", styles["section"]), _table([[_p("Принято в расчёте", styles["bold"]), _p("Не включено в расчёт", styles["bold"])], [_p("\n".join(str(v) for v in snapshot.get("calculationConditions") or ["Не указано"]), styles["body"]), _p("\n".join(str(v) for v in snapshot.get("scopeExclusions") or ["Работы и поставки, не перечисленные в строках сметы."]), styles["body"])]], [87 * mm, 87 * mm], repeat_rows=1), Spacer(1, 5 * mm), _p("3. Порядок уточнения", styles["section"]), _p("Документ выпускается на основании зафиксированной версии сметы. Изменение исходных данных оформляется новой версией.", styles["body"])])
    return block


def _invoice_page(snapshot: Mapping[str, Any], styles: Mapping[str, ParagraphStyle]) -> list[Any]:
    contractor = snapshot.get("contractor") or {}
    requisites = contractor.get("requisites") if isinstance(contractor, Mapping) else {}
    customer = snapshot.get("customer") or {}
    block = _header(snapshot, styles, "СЧЁТ НА ОПЛАТУ", f"№ {snapshot['document']['number']} от {snapshot['document']['date']}")
    details = [
        [_p("Банк получателя", styles["bold"]), _p(requisites.get("bankName", ""), styles["body"]), _p("БИК", styles["bold"]), _p(requisites.get("bankIdentificationCode", ""), styles["body"])],
        [_p("Получатель", styles["bold"]), _p(requisites.get("legalName", ""), styles["body"]), _p("Сч. №", styles["bold"]), _p(requisites.get("settlementAccount", ""), styles["body"])],
        [_p("ИНН / КПП", styles["bold"]), _p(f"{requisites.get('taxId', '')} / {requisites.get('registrationCode') or '—'}", styles["body"]), _p("Корр. сч.", styles["bold"]), _p(requisites.get("correspondentAccount", ""), styles["body"])],
    ]
    block.extend([_table(details, [29 * mm, 60 * mm, 25 * mm, 60 * mm], repeat_rows=0), Spacer(1, 7 * mm), _p(f"Заказчик: {customer.get('displayName', '')}", styles["body"]), _p(f"Основание платежа: {requisites.get('basis', '')}", styles["body"]), Spacer(1, 6 * mm)])
    lines = [[_p(value, styles["bold"]) for value in ["№", "Наименование", "Кол-во", "Ед.", "Цена, руб.", "Сумма, руб."]], [_p(1, styles["cell"]), _p("Аванс по официальному комплекту сметных документов", styles["cell"]), _p("1", styles["cell_right"]), _p("компл.", styles["cell"]), _p(snapshot["commercialTerms"]["total"], styles["cell_right"]), _p(snapshot["commercialTerms"]["total"], styles["cell_right"])]]
    block.extend([_table(lines, [8 * mm, 73 * mm, 17 * mm, 19 * mm, 28 * mm, 29 * mm]), Spacer(1, 5 * mm), _p(f"Итого: {_money(snapshot['commercialTerms']['total'])}", styles["cell_right_bold"]), _p(f"Всего к оплате: {_money(snapshot['commercialTerms']['total'])}", styles["cell_right_bold"]), _p(str(snapshot["commercialTerms"]["totalWords"]), styles["body"])])
    return block


def render_pdf(snapshot: Mapping[str, Any], *, requested_kinds: Iterable[str]) -> bytes:
    _register_fonts()
    styles = _styles()
    kinds = tuple(requested_kinds)
    story: list[Any] = []

    def add_page(page_story: list[Any]) -> None:
        if story:
            story.append(PageBreak())
        story.extend(page_story)

    if "pack" in kinds or "commercial_offer" in kinds:
        add_page(_commercial_page(snapshot, styles))
    if "pack" in kinds or "local_estimate" in kinds:
        add_page(
            _header(snapshot, styles, "ЛОКАЛЬНЫЙ СМЕТНЫЙ РАСЧЁТ", "По составу и стоимости работ/затрат")
            + _line_table(snapshot, styles, title="Метод расчёта: ресурсный")
        )
    if "pack" in kinds or "resource_statement" in kinds:
        add_page(_resource_page(snapshot, styles))
    if "pack" in kinds or "conjunctural_analysis" in kinds:
        add_page(_analysis_page(snapshot, styles))
    if "pack" in kinds or "appendix" in kinds:
        add_page(_appendix_page(snapshot, styles))
    if "invoice" in kinds:
        add_page(_invoice_page(snapshot, styles))
    if not story:
        raise DocumentPackError("document_kind_invalid", "Нет содержимого для PDF.")
    output = io.BytesIO()
    title = str(snapshot["project"]["title"])
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=22 * mm, bottomMargin=18 * mm, title=title, author="Kolibri", subject="Официальный комплект сметных документов")
    def invariant_canvas(*args: Any, **kwargs: Any) -> canvas.Canvas:
        kwargs.setdefault("invariant", 1)
        return canvas.Canvas(*args, **kwargs)

    doc.build(story, onFirstPage=_frame(snapshot), onLaterPages=_frame(snapshot), canvasmaker=invariant_canvas)
    return output.getvalue()


def _set_cell(cell: Any, value: object, *, bold: bool = False, right: bool = False) -> None:
    cell.text = str(value)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    paragraph = cell.paragraphs[0]
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT if right else WD_ALIGN_PARAGRAPH.LEFT
    paragraph.paragraph_format.space_after = Pt(0)
    for run in paragraph.runs:
        run.font.name = "Noto Sans"
        run.font.size = Pt(8)
        run.bold = bold
        run.font.color.rgb = RGBColor(16, 36, 29)


def _repeat_header(row: Any) -> None:
    props = row._tr.get_or_add_trPr()
    marker = OxmlElement("w:tblHeader")
    marker.set(qn("w:val"), "true")
    props.append(marker)


def _set_docx_table_widths(table: Any, widths_cm: list[float]) -> None:
    """Keep the OOXML grid and cell widths inside the portrait print area."""

    twips = [str(round(width * 1440 / 2.54)) for width in widths_cm]
    grid = table._tbl.tblGrid
    for index, width in enumerate(twips):
        if index < len(grid.gridCol_lst):
            grid.gridCol_lst[index].set(qn("w:w"), width)
    table_properties = table._tbl.tblPr
    table_width = table_properties.find(qn("w:tblW"))
    if table_width is None:
        table_width = OxmlElement("w:tblW")
        table_properties.append(table_width)
    table_width.set(qn("w:type"), "dxa")
    table_width.set(qn("w:w"), str(sum(int(width) for width in twips)))


def render_docx(snapshot: Mapping[str, Any], *, requested_kinds: Iterable[str]) -> bytes:
    document = Document()
    section = document.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(1.8)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.header_distance = Cm(0.8)
    section.footer_distance = Cm(0.8)
    normal = document.styles["Normal"]
    normal.font.name = "Noto Sans"
    normal.font.size = Pt(8)
    normal.font.color.rgb = RGBColor(17, 17, 17)
    document.core_properties.author = "Kolibri"
    document.core_properties.title = str(snapshot["project"]["title"])
    if _PET_MARK.is_file():
        header = section.header.paragraphs[0]
        header.add_run().add_picture(str(_PET_MARK), width=Cm(1.2))
        header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    footer = section.footer.paragraphs[0]
    footer.text = f"{snapshot['document']['number']} / версия {snapshot['estimateVersion']}"
    footer.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for run in footer.runs:
        run.font.name = "Noto Sans"
        run.font.size = Pt(7)
        run.font.color.rgb = RGBColor(102, 117, 109)

    def heading(text: str) -> None:
        p = document.add_paragraph()
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(text)
        run.bold = True
        run.font.name = "Noto Sans"
        run.font.size = Pt(13)
        run.font.color.rgb = RGBColor(16, 36, 29)

    def table(rows: list[list[object]], widths: list[float]) -> None:
        tbl = document.add_table(rows=0, cols=len(widths))
        tbl.style = "Table Grid"
        tbl.autofit = False
        tbl.alignment = WD_TABLE_ALIGNMENT.LEFT
        for row_index, values in enumerate(rows):
            cells = tbl.add_row().cells
            for index, value in enumerate(values):
                cells[index].width = Cm(widths[index])
                _set_cell(cells[index], value, bold=row_index == 0, right=index >= len(values) - 2)
            if row_index == 0:
                _repeat_header(tbl.rows[-1])
        _set_docx_table_widths(tbl, widths)

    kinds = tuple(requested_kinds)
    if "pack" in kinds or "commercial_offer" in kinds:
        heading("КОММЕРЧЕСКАЯ СМЕТА")
        document.add_paragraph(f"№ {snapshot['document']['number']} · срок действия до {snapshot['document']['validUntil']}")
        table([["Раздел", "Сумма, руб."], *[[item["name"], _money(item["total"])] for item in snapshot["sections"]], ["Итого к оплате", _money(snapshot["commercialTerms"]["total"])]], [11.5, 5.9])
    if "pack" in kinds or "local_estimate" in kinds:
        document.add_page_break()
        heading("ЛОКАЛЬНЫЙ СМЕТНЫЙ РАСЧЁТ")
        table([["№", "Раздел", "Наименование", "Ед.", "Кол-во", "Цена", "Сумма"], *[[line["position"], line["section"], line["description"], line["unit"], _quantity(line["quantity"]), _money(line["unitPrice"]), _money(line["lineTotal"])] for line in snapshot["lines"]]], [0.6, 1.8, 6.9, 1.2, 1.4, 2.6, 2.9])
    if "pack" in kinds or "resource_statement" in kinds:
        document.add_page_break()
        heading("РЕСУРСНАЯ ВЕДОМОСТЬ")
        table([["№", "Ресурс", "Ед.", "Кол-во", "Стоимость"], *[[line["position"], line["description"], line["unit"], _quantity(line["quantity"]), _money(line["lineTotal"])] for line in snapshot["lines"]]], [0.6, 9.0, 1.2, 2.0, 4.6])
    if "pack" in kinds or "conjunctural_analysis" in kinds:
        document.add_page_break()
        heading("КОНЪЮНКТУРНЫЙ АНАЛИЗ")
        table([["№", "Ресурс", "Источник", "Дата цены", "Статус"], *[[line["position"], line["description"], line["source"].get("label"), line["source"].get("observedAt"), _status_label(line["source"])] for line in snapshot["lines"]]], [0.6, 6.8, 4.0, 2.5, 3.5])
    if "pack" in kinds or "appendix" in kinds:
        document.add_page_break()
        heading("ПРИЛОЖЕНИЕ № 1")
        document.add_paragraph("Условия и границы расчёта")
        for value in snapshot.get("calculationConditions") or ["Не указано"]:
            document.add_paragraph(str(value), style="List Bullet")
        document.add_paragraph("Не включено в расчёт")
        for value in snapshot.get("scopeExclusions") or ["Работы и поставки, не перечисленные в строках сметы."]:
            document.add_paragraph(str(value), style="List Bullet")
        document.add_paragraph("График платежей")
        table([["Этап", "Доля, %"], *[[item["label"], item["percent"]] for item in snapshot["commercialTerms"]["paymentSchedule"]]], [13.2, 4.2])
    if "invoice" in kinds:
        document.add_page_break()
        heading("СЧЁТ НА ОПЛАТУ")
        requisites = (snapshot.get("contractor") or {}).get("requisites") or {}
        document.add_paragraph(f"Получатель: {requisites.get('legalName', '')}")
        document.add_paragraph(f"Основание платежа: {requisites.get('basis', '')}")
        document.add_paragraph(f"Всего к оплате: {_money(snapshot['commercialTerms']['total'])}")
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def render_xlsx(snapshot: Mapping[str, Any], *, requested_kinds: Iterable[str]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    thin = Side(style="thin", color="A8B4AE")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    fill = PatternFill("solid", fgColor="E5EBE8")

    def sheet(name: str, headers: list[str], rows: list[list[object]]) -> None:
        ws = workbook.create_sheet(name)
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(name="Noto Sans", bold=True, color="10241D")
            cell.fill = fill
            cell.border = border
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for values in rows:
            ws.append(values)
        for row in ws.iter_rows():
            for cell in row:
                cell.border = border
                cell.font = Font(name="Noto Sans", size=9, color="111111", bold=cell.row == 1)
                cell.alignment = Alignment(wrap_text=True, vertical="top", horizontal="right" if cell.column >= len(headers) - 1 else "left")
        ws.freeze_panes = "A2"
        for index, width in enumerate([8, 24, 58, 14, 14, 18, 18][: len(headers)], start=1):
            ws.column_dimensions[get_column_letter(index)].width = width

    kinds = tuple(requested_kinds)
    if "pack" in kinds or "commercial_offer" in kinds:
        sheet("Коммерческая смета", ["Раздел", "Сумма, руб."], [[item["name"], float(item["total"])] for item in snapshot["sections"]] + [["Итого к оплате", float(snapshot["commercialTerms"]["total"])]] )
    if "pack" in kinds or "local_estimate" in kinds:
        sheet("Локальный расчёт", ["№", "Раздел", "Наименование", "Ед.", "Количество", "Цена, руб.", "Сумма, руб."], [[line["position"], line["section"], line["description"], line["unit"], float(line["quantity"]), float(line["unitPrice"]), f"=E{index + 1}*F{index + 1}"] for index, line in enumerate(snapshot["lines"], start=1)])
    if "pack" in kinds or "resource_statement" in kinds:
        sheet("Ресурсная ведомость", ["№", "Ресурс", "Ед.", "Количество", "Стоимость, руб."], [[line["position"], line["description"], line["unit"], float(line["quantity"]), float(line["lineTotal"])] for line in snapshot["lines"]])
    if "pack" in kinds or "conjunctural_analysis" in kinds:
        sheet("Конъюнктурный анализ", ["№", "Ресурс", "Источник", "Регион", "Дата цены", "Статус"], [[line["position"], line["description"], line["source"].get("label"), line["source"].get("region") or "", line["source"].get("observedAt"), _status_label(line["source"])] for line in snapshot["lines"]])
    if "pack" in kinds or "appendix" in kinds:
        sheet("Условия", ["Раздел", "Значение"], [["Принято в расчёте", "\n".join(snapshot.get("calculationConditions") or ["Не указано"])], ["Не включено в расчёт", "\n".join(snapshot.get("scopeExclusions") or ["Работы и поставки, не перечисленные в строках сметы."])], ["График платежей", json.dumps(snapshot["commercialTerms"]["paymentSchedule"], ensure_ascii=False)]])
    if "invoice" in kinds:
        requisites = (snapshot.get("contractor") or {}).get("requisites") or {}
        sheet("Счёт", ["Поле", "Значение"], [["Получатель", requisites.get("legalName", "")], ["Банк", requisites.get("bankName", "")], ["БИК", requisites.get("bankIdentificationCode", "")], ["Расчётный счёт", requisites.get("settlementAccount", "")], ["Сумма", float(snapshot["commercialTerms"]["total"])]] )
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def render_zip(snapshot: Mapping[str, Any], files: Iterable[RenderedDocumentFile]) -> bytes:
    stable = datetime.fromisoformat(str(snapshot["document"]["date"]))
    timestamp = (max(stable.year, 1980), stable.month, stable.day, 0, 0, 0)
    content = io.BytesIO()
    file_list = list(files)
    manifest = {
        "schemaId": "kolibri.estimate_document_pack_manifest",
        "schemaVersion": "1.0",
        "rendererVersion": RENDERER_VERSION,
        "documentNumber": snapshot["document"]["number"],
        "estimateVersion": snapshot["estimateVersion"],
        "sourceHash": snapshot["sourceHash"],
        "files": [],
    }
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in file_list:
            digest = "sha256:" + __import__("hashlib").sha256(file.content).hexdigest()
            manifest["files"].append({"kind": file.kind, "filename": file.filename, "mediaType": file.media_type, "sizeBytes": len(file.content), "artifactHash": digest})
            info = zipfile.ZipInfo(file.filename, date_time=timestamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, file.content, compresslevel=6)
        info = zipfile.ZipInfo("manifest.json", date_time=timestamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (0o100644 & 0xFFFF) << 16
        archive.writestr(info, json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"), compresslevel=6)
    return content.getvalue()


def render_document_files(snapshot: Mapping[str, Any], *, requested_kinds: Iterable[str]) -> tuple[RenderedDocumentFile, ...]:
    kinds = tuple(requested_kinds)
    pdf = render_pdf(snapshot, requested_kinds=kinds)
    xlsx = render_xlsx(snapshot, requested_kinds=kinds)
    docx = render_docx(snapshot, requested_kinds=kinds)
    number = str(snapshot["document"]["number"])
    files = [
        RenderedDocumentFile("pdf", f"{number}-official-pack.pdf", "application/pdf", pdf),
        RenderedDocumentFile("xlsx", f"{number}-official-pack.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", xlsx),
        RenderedDocumentFile("docx", f"{number}-official-pack.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx),
    ]
    zip_bytes = render_zip(snapshot, files)
    files.append(RenderedDocumentFile("zip", f"{number}-official-pack.zip", "application/zip", zip_bytes))
    return tuple(files)


__all__ = ["RENDERER_VERSION", "render_document_files", "render_docx", "render_pdf", "render_xlsx", "render_zip"]
