"""Professional PDF generation for Kolibri estimates and documents.
Uses WeasyPrint for HTML+CSS → PDF with Cyrillic support."""
from html.parser import HTMLParser
from io import BytesIO
import os
from pathlib import Path
from decimal import Decimal
from typing import Any, Callable, Dict, Mapping, Optional
from urllib.parse import urlsplit
from xml.sax.saxutils import escape
from jinja2 import Environment, BaseLoader
from app.document_html import sanitize_document_html


_TAX_REGIME_LABELS = {
    "unspecified": "Не выбран",
    "npd": "Самозанятый · НПД · без НДС",
    "usn_exempt": "УСН · освобождение от НДС",
    "usn_vat5": "УСН · НДС 5%",
    "usn_vat7": "УСН · НДС 7%",
    "osno_vat22": "ОСНО · НДС 22%",
}

# Prefer WeasyPrint; use ReportLab when native WeasyPrint libraries are unavailable.
# Both paths return validated PDF bytes and never HTML under a PDF MIME type.
try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    HTML = None
    WEASYPRINT_AVAILABLE = False

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


class PDFGenerationUnavailable(RuntimeError):
    """Raised when the configured runtime cannot produce a real PDF."""


def _validate_pdf(pdf: bytes) -> bytes:
    if len(pdf) < 100 or not pdf.startswith(b"%PDF-"):
        raise PDFGenerationUnavailable("PDF renderer returned an invalid document")
    return pdf


def _render_pdf(html: str) -> bytes:
    if not WEASYPRINT_AVAILABLE or HTML is None:
        raise PDFGenerationUnavailable("WeasyPrint is required for PDF generation")
    return _validate_pdf(HTML(string=html).write_pdf())


def _render_with_portable_fallback(
    html: str,
    fallback: Callable[[], bytes],
) -> bytes:
    """Render with WeasyPrint, falling back when its native runtime fails.

    Importing WeasyPrint only proves that its Python package is present.  The
    actual render can still fail later when a worker has an incomplete or
    incompatible native Pango/Cairo/font stack.  ReportLab is our independent
    renderer, so a runtime failure in the preferred renderer must not turn an
    otherwise valid PDF request into a 502.
    """

    if WEASYPRINT_AVAILABLE:
        try:
            return _render_pdf(html)
        except Exception:
            try:
                return fallback()
            except Exception as fallback_error:
                raise PDFGenerationUnavailable(
                    "Both configured PDF renderers failed"
                ) from fallback_error
    return fallback()


def _reportlab_fonts() -> tuple[str, str]:
    if not REPORTLAB_AVAILABLE:
        raise PDFGenerationUnavailable("ReportLab is required for portable PDF generation")
    configured = os.getenv("KOLIBRI_PDF_FONT")
    regular_candidates = [
        configured,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    bold_candidates = [
        os.getenv("KOLIBRI_PDF_BOLD_FONT"),
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    regular = next((path for path in regular_candidates if path and Path(path).is_file()), None)
    bold = next((path for path in bold_candidates if path and Path(path).is_file()), regular)
    if regular is None or bold is None:
        raise PDFGenerationUnavailable("A Unicode PDF font is required for Cyrillic output")
    if "KolibriSans" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("KolibriSans", regular))
    if "KolibriSans-Bold" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("KolibriSans-Bold", bold))
    return "KolibriSans", "KolibriSans-Bold"


def _paragraph(value: object, style):
    return Paragraph(escape("" if value is None else str(value)).replace("\n", "<br/>"), style)


def _reportlab_estimate_pdf(estimate_data: Dict[str, Any]) -> bytes:
    regular_font, bold_font = _reportlab_fonts()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=20 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=str(estimate_data.get("title") or "Смета"),
        author="Колибри",
    )
    sample_styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "KolibriBody",
        parent=sample_styles["BodyText"],
        fontName=regular_font,
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#0A0A0B"),
    )
    small = ParagraphStyle("KolibriSmall", parent=body, fontSize=7, leading=8)
    heading = ParagraphStyle(
        "KolibriHeading",
        parent=body,
        fontName=bold_font,
        fontSize=16,
        leading=19,
        alignment=TA_CENTER,
        spaceAfter=4 * mm,
    )
    subtitle = ParagraphStyle(
        "KolibriSubtitle",
        parent=body,
        fontSize=10,
        leading=13,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=4 * mm,
    )
    money = ParagraphStyle(
        "KolibriMoney",
        parent=body,
        fontName=bold_font,
        alignment=TA_RIGHT,
    )
    currency = estimate_data.get("currency", "RUB")
    story = [
        _paragraph(f"Смета № {str(estimate_data.get('id', ''))[:8]}", heading),
        _paragraph(estimate_data.get("title", ""), subtitle),
    ]
    meta_rows = [
        ["Клиент", estimate_data.get("client", "")],
        ["Объект", estimate_data.get("object_name", "")],
        ["Регион", estimate_data.get("region", "")],
        [
            "Налоговый режим",
            _TAX_REGIME_LABELS.get(
                str(estimate_data.get("tax_regime") or "unspecified"),
                "Не выбран",
            ),
        ],
        ["Дата", str(estimate_data.get("created_at", ""))[:10]],
        ["Версия", estimate_data.get("version", 1)],
    ]
    meta = Table(
        [[_paragraph(label, body), _paragraph(value, body)] for label, value in meta_rows],
        colWidths=[32 * mm, 133 * mm],
        hAlign="LEFT",
    )
    meta.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), bold_font),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.extend([meta, Spacer(1, 4 * mm)])

    column_widths = [8 * mm, 18 * mm, 68 * mm, 12 * mm, 18 * mm, 24 * mm, 27 * mm]
    for section in estimate_data.get("sections", []):
        rows = [
            [
                _paragraph(section.get("title", ""), body),
                "",
                "",
                "",
                "",
                "",
                _paragraph(
                    _format_currency(Decimal(section.get("subtotal", "0")), currency),
                    money,
                ),
            ],
            [
                _paragraph("№", small),
                _paragraph("Код", small),
                _paragraph("Наименование", small),
                _paragraph("Ед.", small),
                _paragraph("Кол-во", small),
                _paragraph("Цена", small),
                _paragraph("Сумма", small),
            ],
        ]
        for index, position in enumerate(section.get("positions", []), start=1):
            rows.append(
                [
                    _paragraph(index, small),
                    _paragraph(position.get("code", ""), small),
                    _paragraph(position.get("name", ""), small),
                    _paragraph(position.get("unit", ""), small),
                    _paragraph(_format_ru(Decimal(position.get("quantity", "0"))), small),
                    _paragraph(
                        _format_currency(Decimal(position.get("price", "0")), currency),
                        small,
                    ),
                    _paragraph(
                        _format_currency(Decimal(position.get("sum", "0")), currency),
                        money,
                    ),
                ]
            )
        table = Table(rows, colWidths=column_widths, repeatRows=2, hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("SPAN", (0, 0), (5, 0)),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F8F7")),
                    ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F0F0F0")),
                    ("FONTNAME", (0, 0), (-1, 1), bold_font),
                    ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 1), (-1, -1), 0.35, colors.HexColor("#D6D6D6")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9A9A9A")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend([table, Spacer(1, 4 * mm)])

    total_rows = [
        ["Подытог", _format_currency(Decimal(estimate_data.get("subtotal", "0")), currency)],
        [
            f"Накладные расходы ({estimate_data.get('overhead_rate', '0')}%)",
            _format_currency(Decimal(estimate_data.get("overhead_amount", "0")), currency),
        ],
        [
            f"Сметная прибыль ({estimate_data.get('profit_rate', '0')}%)",
            _format_currency(Decimal(estimate_data.get("profit_amount", "0")), currency),
        ],
        [
            f"Резерв ({estimate_data.get('contingency_rate', '0')}%)",
            _format_currency(Decimal(estimate_data.get("contingency_amount", "0")), currency),
        ],
        [
            f"Генподрядные услуги ({estimate_data.get('general_contractor_rate', '0')}%)",
            _format_currency(Decimal(estimate_data.get("general_contractor_amount", "0")), currency),
        ],
        [
            f"Скидка ({estimate_data.get('discount_rate', '0')}%)",
            f"− {_format_currency(Decimal(estimate_data.get('discount_amount', '0')), currency)}",
        ],
        [
            f"НДС ({estimate_data.get('vat_rate', '22')}%)",
            _format_currency(Decimal(estimate_data.get("vat_amount", "0")), currency),
        ],
        ["ИТОГО", _format_currency(Decimal(estimate_data.get("total", "0")), currency)],
    ]
    totals = Table(
        [[_paragraph(label, body), _paragraph(value, money)] for label, value in total_rows],
        colWidths=[75 * mm, 45 * mm],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, -1), (-1, -1), 1.25, colors.HexColor("#0A0A0B")),
                ("FONTNAME", (0, -1), (-1, -1), bold_font),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(totals)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(regular_font, 7)
        canvas.setFillColor(colors.HexColor("#777777"))
        canvas.drawCentredString(A4[0] / 2, 9 * mm, f"Колибри | Страница {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return _validate_pdf(buffer.getvalue())


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _reportlab_document_pdf(title: str, html_content: str) -> bytes:
    regular_font, bold_font = _reportlab_fonts()
    extractor = _HTMLTextExtractor()
    extractor.feed(html_content)
    lines = [line.strip() for line in "".join(extractor.parts).splitlines() if line.strip()]
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="Колибри",
    )
    body = ParagraphStyle("DocumentBody", fontName=regular_font, fontSize=10, leading=15)
    heading = ParagraphStyle(
        "DocumentHeading",
        parent=body,
        fontName=bold_font,
        fontSize=17,
        leading=21,
        alignment=TA_CENTER,
        spaceAfter=8 * mm,
    )
    story = [_paragraph(title, heading)]
    for line in lines or [""]:
        story.extend([_paragraph(line, body), Spacer(1, 2 * mm)])
    document.build(story)
    return _validate_pdf(buffer.getvalue())


def _format_ru(value: Decimal) -> str:
    """Russian number format: 1 234,56"""
    s = f"{value:.2f}"
    int_part, dec_part = s.split(".")
    ip = int(int_part)
    sign = ""
    if ip < 0:
        sign = "-"
        ip = -ip
    groups = []
    while ip >= 1000:
        groups.append(f"{ip % 1000:03d}")
        ip //= 1000
    groups.append(str(ip))
    groups.reverse()
    return f"{sign}{' '.join(groups)},{dec_part}"


def _format_currency(amount: Decimal, currency: str = "RUB") -> str:
    formatted = _format_ru(amount)
    symbols = {"RUB": "руб.", "USD": "$", "EUR": "EUR"}
    return f"{formatted} {symbols.get(currency, currency)}"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

ESTIMATE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<style>
@page {
  size: A4 portrait;
  margin: 15mm 15mm 20mm 20mm;
  @bottom-center {
    content: "Документ сформирован системой Колибри · Страница " counter(page) " из " counter(pages);
    font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
    font-size: 8pt;
    color: #666;
  }
}
* { box-sizing: border-box; }
body { margin: 0; font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 10pt; color: #0A0A0B; }
.header { text-align: center; margin-bottom: 8mm; }
.header h1 { font-size: 16pt; margin: 0 0 4mm 0; }
.header .subtitle { font-size: 10pt; color: #555; margin: 1mm 0; }
.info { margin-bottom: 6mm; font-size: 9pt; }
.info-row { display: flex; justify-content: space-between; margin: 1mm 0; }
table { width: 100%; table-layout: fixed; border-collapse: collapse; margin: 4mm 0; font-size: 9pt; }
th { background: #f0f0f0; padding: 2mm 1mm; text-align: left; border-bottom: 1px solid #333; }
th, td { overflow-wrap: anywhere; word-break: break-word; }
td { padding: 1.5mm 1mm; border-bottom: 1px solid #ddd; vertical-align: top; }
td.num, th.num { text-align: right; }
td.sum, th.sum { text-align: right; font-weight: bold; }
td.quantity-value { white-space: nowrap; font-size: 7pt; font-variant-numeric: tabular-nums; }
td.money-value { white-space: nowrap; font-size: 7pt; font-variant-numeric: tabular-nums; }
td.source-cell { overflow-wrap: anywhere; word-break: break-word; font-size: 7pt; line-height: 1.25; }
td.source-cell a { color: #245f75; text-decoration: none; }
.section-header { background: #f8f8f8; font-weight: bold; }
.totals { margin-top: 6mm; width: 60%; margin-left: auto; font-size: 10pt; }
.totals-row { display: flex; justify-content: space-between; padding: 1.5mm 0; border-bottom: 1px solid #eee; }
.totals-row.grand { font-weight: bold; font-size: 12pt; border-top: 2px solid #333; margin-top: 2mm; }
.page-break { page-break-after: always; }
tr { page-break-inside: avoid; }
thead { display: table-header-group; }
</style>
</head>
<body>
<div class="header">
  <h1>Смета № {{ estimate_id[:8] }}</h1>
  <div class="subtitle">{{ title }}</div>
  {% if context_line %}<div class="subtitle">{{ context_line }}</div>{% endif %}
</div>

<div class="info">
  <div class="info-row"><span>Дата:</span><span>{{ date }}</span></div>
  <div class="info-row"><span>Валюта:</span><span>{{ currency }}</span></div>
  <div class="info-row"><span>Налоговый режим:</span><span>{{ tax_regime_label }}</span></div>
  <div class="info-row"><span>НДС:</span><span>{{ vat_rate }}%</span></div>
  <div class="info-row"><span>Накладные расходы:</span><span>{{ overhead_rate }}%</span></div>
</div>

{% for section in sections %}
<table>
  <colgroup>
    <col style="width:4%">
    <col style="width:9%">
    <col style="width:25%">
    <col style="width:6%">
    <col style="width:12%">
    <col style="width:13%">
    <col style="width:13%">
    <col style="width:18%">
  </colgroup>
  <thead>
    <tr class="section-header">
      <th colspan="7">{{ section.title }} ({{ section.position_count }} поз.)</th>
      <th class="sum">{{ section.subtotal }}</th>
    </tr>
    <tr>
      <th>№</th>
      <th>Код</th>
      <th>Наименование</th>
      <th>Ед.</th>
      <th class="num">Кол-во</th>
      <th class="num">Цена,<br>{{ currency_unit }}</th>
      <th class="num">Сумма,<br>{{ currency_unit }}</th>
      <th>Источник</th>
    </tr>
  </thead>
  <tbody>
    {% for pos in section.positions %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ pos.code }}</td>
      <td>{{ pos.name }}</td>
      <td>{{ pos.unit }}</td>
      <td class="num quantity-value">{{ pos.quantity }}</td>
      <td class="num money-value">{{ pos.price }}</td>
      <td class="sum money-value">{{ pos.sum }}</td>
      <td class="source-cell">
        {% if pos.source_url %}<a href="{{ pos.source_url }}">{{ pos.source_label }}</a>{% else %}{{ pos.source_label }}{% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endfor %}

<div class="totals">
  <div class="totals-row"><span>Подытог:</span><span>{{ subtotal }}</span></div>
  <div class="totals-row"><span>Накладные расходы ({{ overhead_rate }}%):</span><span>{{ overhead_amount }}</span></div>
  <div class="totals-row"><span>Сметная прибыль ({{ profit_rate }}%):</span><span>{{ profit_amount }}</span></div>
  <div class="totals-row"><span>Резерв ({{ contingency_rate }}%):</span><span>{{ contingency_amount }}</span></div>
  <div class="totals-row"><span>Генподрядные услуги ({{ general_contractor_rate }}%):</span><span>{{ general_contractor_amount }}</span></div>
  <div class="totals-row"><span>Скидка ({{ discount_rate }}%):</span><span>− {{ discount_amount }}</span></div>
  <div class="totals-row"><span>НДС ({{ vat_rate }}%):</span><span>{{ vat_amount }}</span></div>
  <div class="totals-row grand"><span>ИТОГО:</span><span>{{ total }}</span></div>
</div>

</body>
</html>"""


def _build_estimate_html(estimate_data: Dict[str, Any]) -> str:
    """Build the exact HTML passed to the estimate PDF renderer."""
    env = Environment(loader=BaseLoader(), autoescape=True)
    template = env.from_string(ESTIMATE_TEMPLATE)

    # Format all monetary values
    from decimal import Decimal
    currency = estimate_data.get("currency", "RUB")
    currency_unit = {"RUB": "руб.", "USD": "USD", "EUR": "EUR"}.get(
        currency,
        currency,
    )
    sections = []
    for sec in estimate_data.get("sections", []):
        positions = []
        for pos in sec.get("positions", []):
            evidence = pos.get("price_evidence")
            first_evidence = (
                evidence[0]
                if isinstance(evidence, list) and evidence and isinstance(evidence[0], Mapping)
                else {}
            )
            source_candidate = str(first_evidence.get("url") or pos.get("source") or "").strip()
            parsed_source = urlsplit(source_candidate)
            source_url = (
                source_candidate
                if parsed_source.scheme in {"http", "https"} and parsed_source.hostname
                else ""
            )
            source_label = str(first_evidence.get("source_title") or pos.get("source") or "").strip()
            source_date = str(first_evidence.get("price_date") or "").strip()
            if source_label and source_date:
                source_label = f"{source_label} · {source_date}"
            positions.append({
                "code": pos.get("code", ""),
                "name": pos.get("name", ""),
                "unit": pos.get("unit", ""),
                "quantity": _format_ru(Decimal(pos.get("quantity", "0"))),
                "price": _format_ru(Decimal(pos.get("price", "0"))),
                "sum": _format_ru(Decimal(pos.get("sum", "0"))),
                "source_label": source_label,
                "source_url": source_url,
            })
        sections.append({
            "title": sec.get("title", ""),
            "subtotal": _format_currency(Decimal(sec.get("subtotal", "0")), currency),
            "position_count": len(positions),
            "positions": positions,
        })

    title = str(estimate_data.get("title") or "")
    context_parts = []
    for value in (
        estimate_data.get("client", ""),
        estimate_data.get("object_name", ""),
        estimate_data.get("region", ""),
    ):
        text = " ".join(str(value or "").split()).strip()
        if text and text.casefold() not in title.casefold():
            context_parts.append(text)

    ctx = {
        "estimate_id": estimate_data.get("id", ""),
        "title": title,
        "context_line": " · ".join(context_parts),
        "date": str(estimate_data.get("created_at") or "")[:10],
        "currency": currency,
        "currency_unit": currency_unit,
        "vat_rate": estimate_data.get("vat_rate", "22"),
        "tax_regime_label": _TAX_REGIME_LABELS.get(
            str(estimate_data.get("tax_regime") or "unspecified"),
            "Не выбран",
        ),
        "overhead_rate": estimate_data.get("overhead_rate", "0"),
        "profit_rate": estimate_data.get("profit_rate", "0"),
        "contingency_rate": estimate_data.get("contingency_rate", "0"),
        "general_contractor_rate": estimate_data.get("general_contractor_rate", "0"),
        "discount_rate": estimate_data.get("discount_rate", "0"),
        "subtotal": _format_currency(Decimal(estimate_data.get("subtotal", "0")), currency),
        "overhead_amount": _format_currency(Decimal(estimate_data.get("overhead_amount", "0")), currency),
        "profit_amount": _format_currency(Decimal(estimate_data.get("profit_amount", "0")), currency),
        "contingency_amount": _format_currency(Decimal(estimate_data.get("contingency_amount", "0")), currency),
        "general_contractor_amount": _format_currency(Decimal(estimate_data.get("general_contractor_amount", "0")), currency),
        "discount_amount": _format_currency(Decimal(estimate_data.get("discount_amount", "0")), currency),
        "vat_amount": _format_currency(Decimal(estimate_data.get("vat_amount", "0")), currency),
        "total": _format_currency(Decimal(estimate_data.get("total", "0")), currency),
        "sections": sections,
    }

    return template.render(**ctx)


def generate_estimate_pdf(estimate_data: Dict[str, Any]) -> bytes:
    """Generate professional PDF from estimate data. Returns PDF bytes."""
    html_str = _build_estimate_html(estimate_data)
    return _render_with_portable_fallback(
        html_str,
        lambda: _reportlab_estimate_pdf(estimate_data),
    )


def generate_document_pdf(document_data: Dict[str, Any]) -> bytes:
    """Generate PDF from document HTML content."""
    html_content = sanitize_document_html(document_data.get("content", ""))
    title = escape(str(document_data.get("title", "Документ")))

    template = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<style>
@page {{ size: A4; margin: 15mm 15mm 20mm 20mm; }}
body {{ font-family: "DejaVu Sans", Arial, sans-serif; font-size: 11pt; color: #0A0A0B; line-height: 1.6; }}
.header {{ text-align: center; margin-bottom: 10mm; border-bottom: 2px solid #333; padding-bottom: 5mm; }}
.header h1 {{ font-size: 18pt; margin: 0; }}
.content {{ margin-top: 5mm; }}
.footer {{ margin-top: 15mm; font-size: 9pt; color: #666; text-align: center; border-top: 1px solid #ccc; padding-top: 3mm; }}
</style>
</head>
<body>
<div class="header"><h1>{title}</h1></div>
<div class="content">{html_content}</div>
<div class="footer">Документ сформирован системой Колибри</div>
</body>
</html>"""

    return _render_with_portable_fallback(
        template,
        lambda: _reportlab_document_pdf(str(title), str(html_content)),
    )
