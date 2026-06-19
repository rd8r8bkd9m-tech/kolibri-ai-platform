import os
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

from config import DATA_DIR


DOCS_DIR = DATA_DIR / "documents"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def _register_fonts():
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNS.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("KolibriFont", fp))
                return "KolibriFont"
            except Exception:
                continue
    return "Helvetica"


def _register_bold_fonts():
    font_paths = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont("KolibriFontBold", fp))
                return "KolibriFontBold"
            except Exception:
                continue
    return "Helvetica-Bold"


FONT_NAME = _register_fonts()
FONT_BOLD = _register_bold_fonts()


def generate_estimate_pdf(estimate: dict, output_path: Optional[str] = None) -> str:
    if not output_path:
        filename = f"estimate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = str(DOCS_DIR / filename)

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("Title", parent=styles["Title"], fontName=FONT_NAME, fontSize=16, spaceAfter=12)
    normal_style = ParagraphStyle("Normal", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontName=FONT_NAME, fontSize=8, textColor=colors.grey)

    elements = []

    title = estimate.get("title", "Смета")
    elements.append(Paragraph(title, title_style))

    client = estimate.get("client", {})
    if client.get("name"):
        elements.append(Paragraph(f"Клиент: {client['name']}", normal_style))
    if client.get("phone"):
        elements.append(Paragraph(f"Телефон: {client['phone']}", normal_style))
    if client.get("address"):
        elements.append(Paragraph(f"Адрес: {client['address']}", normal_style))

    obj = estimate.get("object", {})
    if obj.get("type"):
        elements.append(Paragraph(f"Объект: {obj['type']}, площадь: {obj.get('area', 0)} м²", normal_style))

    elements.append(Spacer(1, 12*mm))

    items = estimate.get("items", [])
    if items:
        header = ["№", "Наименование", "Ед.", "Кол-во", "Цена", "Сумма"]
        data = [header]
        for i, item in enumerate(items, 1):
            data.append([
                str(i),
                item.get("name", ""),
                item.get("unit", ""),
                str(item.get("quantity", 0)),
                f"{item.get('unit_price', 0):,.2f}",
                f"{item.get('total', 0):,.2f}",
            ])

        totals = estimate.get("totals", {})
        data.append(["", "", "", "", "Работы:", f"{totals.get('works', 0):,.2f}"])
        data.append(["", "", "", "", "Материалы:", f"{totals.get('materials', 0):,.2f}"])
        if totals.get("delivery", 0) > 0:
            data.append(["", "", "", "", "Доставка:", f"{totals['delivery']:,.2f}"])
        if totals.get("discount", 0) > 0:
            data.append(["", "", "", "", "Скидка:", f"-{totals['discount']:,.2f}"])
        data.append(["", "", "", "", "ИТОГО:", f"{totals.get('grand_total', 0):,.2f}"])

        col_widths = [25, 180, 40, 50, 60, 70]
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a5568")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, len(items)), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, len(items)), [colors.white, colors.HexColor("#f7fafc")]),
            ("FONTSIZE", (-2, len(items)+1), (-1, -1), 10),
            ("FONTNAME", (-2, -1), (-1, -1), FONT_NAME),
            ("LINEABOVE", (-2, -1), (-1, -1), 1.5, colors.HexColor("#2d3748")),
        ]))
        elements.append(table)

    assumptions = estimate.get("assumptions", [])
    if assumptions:
        elements.append(Spacer(1, 8*mm))
        elements.append(Paragraph("Допущения:", small_style))
        for a in assumptions:
            elements.append(Paragraph(f"• {a}", small_style))

    warnings = estimate.get("warnings", [])
    if warnings:
        elements.append(Spacer(1, 4*mm))
        elements.append(Paragraph("Предупреждения:", small_style))
        for w in warnings:
            elements.append(Paragraph(f"⚠ {w}", small_style))

    elements.append(Spacer(1, 12*mm))
    elements.append(Paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y')}", normal_style))
    elements.append(Paragraph(f"Версия: v{estimate.get('version', 1)}", normal_style))

    doc.build(elements)
    return output_path


def generate_commercial_offer_pdf(estimate: dict, company: dict = None, output_path: Optional[str] = None) -> str:
    if not output_path:
        filename = f"kp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = str(DOCS_DIR / filename)

    if company is None:
        company = {"name": "Kolibri Construction", "inn": "", "phone": "", "email": ""}

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("Title", parent=styles["Title"], fontName=FONT_NAME, fontSize=18, spaceAfter=16)
    subtitle_style = ParagraphStyle("Subtitle", parent=styles["Heading2"], fontName=FONT_NAME, fontSize=14, spaceAfter=8)
    normal_style = ParagraphStyle("Normal", parent=styles["Normal"], fontName=FONT_NAME, fontSize=11)

    elements = []

    elements.append(Paragraph("КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ", title_style))
    elements.append(Spacer(1, 8*mm))

    elements.append(Paragraph(f"От: {company['name']}", normal_style))
    if company.get("inn"):
        elements.append(Paragraph(f"ИНН: {company['inn']}", normal_style))
    elements.append(Spacer(1, 4*mm))

    client = estimate.get("client", {})
    if client.get("name"):
        elements.append(Paragraph(f"Для: {client['name']}", normal_style))
    elements.append(Spacer(1, 8*mm))

    elements.append(Paragraph(f"Предмет: {estimate.get('title', 'Строительные работы')}", subtitle_style))
    elements.append(Spacer(1, 4*mm))

    items = estimate.get("items", [])
    if items:
        header = ["№", "Наименование работ", "Ед.изм.", "Кол-во", "Цена", "Сумма"]
        data = [header]
        for i, item in enumerate(items, 1):
            data.append([
                str(i),
                Paragraph(item.get("name", ""), normal_style),
                item.get("unit", ""),
                str(item.get("quantity", 0)),
                f"{item.get('unit_price', 0):,.2f} руб.",
                f"{item.get('total', 0):,.2f} руб.",
            ])

        totals = estimate.get("totals", {})
        data.append(["", "", "", "", Paragraph("<b>ИТОГО:</b>", normal_style), Paragraph(f"<b>{totals.get('grand_total', 0):,.2f} руб.</b>", normal_style)])

        col_widths = [25, 170, 45, 45, 70, 80]
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -2), 0.5, colors.grey),
            ("LINEABOVE", (-2, -1), (-1, -1), 2, colors.HexColor("#2b6cb0")),
        ]))
        elements.append(table)

    elements.append(Spacer(1, 12*mm))
    elements.append(Paragraph("Срок выполнения: по согласованию", normal_style))
    elements.append(Paragraph("Гарантия: 12 месяцев", normal_style))
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y')}", normal_style))

    doc.build(elements)
    return output_path


def generate_estimate_docx(estimate: dict, output_path: Optional[str] = None) -> str:
    if not output_path:
        filename = f"estimate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        output_path = str(DOCS_DIR / filename)

    doc = Document()

    title = doc.add_heading(estimate.get("title", "Смета"), 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    client = estimate.get("client", {})
    if client.get("name"):
        doc.add_paragraph(f"Клиент: {client['name']}")
    if client.get("phone"):
        doc.add_paragraph(f"Телефон: {client['phone']}")
    if client.get("address"):
        doc.add_paragraph(f"Адрес: {client['address']}")

    obj = estimate.get("object", {})
    if obj.get("type"):
        doc.add_paragraph(f"Объект: {obj['type']}, площадь: {obj.get('area', 0)} м²")

    doc.add_paragraph()

    items = estimate.get("items", [])
    if items:
        table = doc.add_table(rows=1, cols=6)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = "Table Grid"

        headers = ["№", "Наименование", "Ед.", "Кол-во", "Цена", "Сумма"]
        for i, header in enumerate(headers):
            cell = table.rows[0].cells[i]
            cell.text = header
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.bold = True
                    run.font.size = Pt(10)

        for idx, item in enumerate(items, 1):
            row = table.add_row()
            row.cells[0].text = str(idx)
            row.cells[1].text = item.get("name", "")
            row.cells[2].text = item.get("unit", "")
            row.cells[3].text = str(item.get("quantity", 0))
            row.cells[4].text = f"{item.get('unit_price', 0):,.2f}"
            row.cells[5].text = f"{item.get('total', 0):,.2f}"

        totals = estimate.get("totals", {})
        doc.add_paragraph()
        doc.add_paragraph(f"Работы: {totals.get('works', 0):,.2f} руб.")
        doc.add_paragraph(f"Материалы: {totals.get('materials', 0):,.2f} руб.")
        if totals.get("delivery", 0) > 0:
            doc.add_paragraph(f"Доставка: {totals['delivery']:,.2f} руб.")
        if totals.get("discount", 0) > 0:
            doc.add_paragraph(f"Скидка: -{totals['discount']:,.2f} руб.")

        p = doc.add_paragraph()
        run = p.add_run(f"ИТОГО: {totals.get('grand_total', 0):,.2f} руб.")
        run.font.bold = True
        run.font.size = Pt(14)

    doc.add_paragraph()
    doc.add_paragraph(f"Дата: {datetime.now().strftime('%d.%m.%Y')}")
    doc.add_paragraph(f"Версия: v{estimate.get('version', 1)}")

    doc.save(output_path)
    return output_path


def list_documents() -> list:
    docs = []
    for f in DOCS_DIR.iterdir():
        if f.suffix in (".pdf", ".docx"):
            docs.append({
                "filename": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "created": datetime.fromtimestamp(f.stat().st_ctime).isoformat(),
            })
    return sorted(docs, key=lambda x: x["created"], reverse=True)


def generate_act_pdf(estimate: dict, company: dict = None, output_path: Optional[str] = None) -> str:
    """Акт выполненных работ (PDF)."""
    if not output_path:
        filename = f"act_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = str(DOCS_DIR / filename)

    if company is None:
        company = {"name": "Kolibri Construction", "inn": "", "phone": ""}

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontName=FONT_NAME, fontSize=16, spaceAfter=12)
    normal_style = ParagraphStyle("Normal", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10)
    bold_style = ParagraphStyle("Bold", parent=styles["Normal"], fontName=FONT_BOLD, fontSize=10)

    elements = []
    elements.append(Paragraph("АКТ ВЫПОЛНЕННЫХ РАБОТ", title_style))
    elements.append(Spacer(1, 6*mm))

    now = datetime.now()
    elements.append(Paragraph(f"г. Лениногорск &nbsp;&nbsp;&nbsp; {now.strftime('%d.%m.%Y')}", normal_style))
    elements.append(Spacer(1, 4*mm))

    client = estimate.get("client", {})
    contractor = company.get("name", "Исполнитель")
    customer = client.get("name", "Заказчик")

    elements.append(Paragraph(
        f"Мы, нижеподписавшиеся, со стороны Исполнителя <b>{contractor}</b>, "
        f"с одной стороны, и со стороны Заказчика <b>{customer}</b>, с другой стороны, "
        f"составили настоящий акт о том, что следующие работы выполнены и приняты:",
        normal_style
    ))
    elements.append(Spacer(1, 6*mm))

    items = estimate.get("items", [])
    if items:
        header = ["№", "Наименование работ", "Ед.", "Кол-во", "Цена", "Сумма"]
        data = [header]
        for i, item in enumerate(items, 1):
            data.append([
                str(i),
                item.get("name", ""),
                item.get("unit", ""),
                str(item.get("quantity", 0)),
                f"{item.get('unit_price', 0):,.2f}",
                f"{item.get('total', 0):,.2f}",
            ])

        totals = estimate.get("totals", {})
        grand = totals.get("grand_total", sum(it.get("total", 0) for it in items))
        data.append(["", "", "", "", "ИТОГО:", f"{grand:,.2f} руб."])

        col_widths = [25, 180, 40, 50, 60, 70]
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a5568")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, len(items)), 0.5, colors.grey),
            ("LINEABOVE", (-2, -1), (-1, -1), 1.5, colors.HexColor("#2d3748")),
        ]))
        elements.append(table)

    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(f"Общая стоимость выполненных работ: <b>{grand:,.2f} руб.</b>", bold_style))
    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph("Работы выполнены в полном объёме и в установленные сроки. Стороны претензий друг к другу не имеют.", normal_style))
    elements.append(Spacer(1, 12*mm))

    elements.append(Paragraph("Подписи сторон:", bold_style))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(f"Исполнитель: _____________ / {contractor} /", normal_style))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(f"Заказчик: _____________ / {customer} /", normal_style))

    doc.build(elements)
    return output_path


def generate_invoice_pdf(estimate: dict, company: dict = None, output_path: Optional[str] = None) -> str:
    """Счёт на оплату (PDF)."""
    if not output_path:
        filename = f"invoice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = str(DOCS_DIR / filename)

    if company is None:
        company = {"name": "Kolibri Construction", "inn": "", "bank": "", "account": ""}

    doc = SimpleDocTemplate(output_path, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontName=FONT_NAME, fontSize=16, spaceAfter=12)
    normal_style = ParagraphStyle("Normal", parent=styles["Normal"], fontName=FONT_NAME, fontSize=10)
    bold_style = ParagraphStyle("Bold", parent=styles["Normal"], fontName=FONT_BOLD, fontSize=10)

    elements = []
    elements.append(Paragraph("СЧЁТ НА ОПЛАТУ", title_style))
    elements.append(Spacer(1, 6*mm))

    now = datetime.now()
    elements.append(Paragraph(f"Счёт № {now.strftime('%Y%m%d')}-1 от {now.strftime('%d.%m.%Y')}", bold_style))
    elements.append(Spacer(1, 4*mm))

    elements.append(Paragraph(f"Поставщик: <b>{company.get('name', '')}</b>", normal_style))
    if company.get("inn"):
        elements.append(Paragraph(f"ИНН: {company['inn']}", normal_style))
    elements.append(Spacer(1, 2*mm))

    client = estimate.get("client", {})
    elements.append(Paragraph(f"Покупатель: <b>{client.get('name', '')}</b>", normal_style))
    elements.append(Spacer(1, 6*mm))

    items = estimate.get("items", [])
    if items:
        header = ["№", "Наименование", "Кол-во", "Ед.", "Цена", "Сумма"]
        data = [header]
        for i, item in enumerate(items, 1):
            data.append([
                str(i),
                item.get("name", ""),
                str(item.get("quantity", 0)),
                item.get("unit", ""),
                f"{item.get('unit_price', 0):,.2f}",
                f"{item.get('total', 0):,.2f}",
            ])

        totals = estimate.get("totals", {})
        grand = totals.get("grand_total", 0)
        data.append(["", "", "", "", "ИТОГО:", f"{grand:,.2f} руб."])

        col_widths = [25, 170, 50, 40, 65, 75]
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b6cb0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, len(items)), 0.5, colors.grey),
            ("LINEABOVE", (-2, -1), (-1, -1), 2, colors.HexColor("#2b6cb0")),
        ]))
        elements.append(table)

    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(f"Итого к оплате: <b>{grand:,.2f} руб.</b>", bold_style))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph("Срок оплаты: в течение 3 банковских дней с момента получения счёта.", normal_style))

    doc.build(elements)
    return output_path
