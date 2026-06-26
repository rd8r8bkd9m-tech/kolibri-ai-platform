"""Professional PDF generation for Kolibri estimates and documents.
Uses WeasyPrint for HTML+CSS → PDF with Cyrillic support."""
import os
from decimal import Decimal
from typing import Dict, Any, Optional
from jinja2 import Environment, BaseLoader

# Try WeasyPrint, fallback to HTML-only
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


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
    symbols = {"RUB": "₽", "USD": "$", "EUR": "€"}
    return f"{formatted} {symbols.get(currency, currency)}"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

ESTIMATE_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<style>
@page { size: A4; margin: 15mm 15mm 20mm 20mm; }
body { font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif; font-size: 10pt; color: #0A0A0B; }
.header { text-align: center; margin-bottom: 8mm; }
.header h1 { font-size: 16pt; margin: 0 0 4mm 0; }
.header .subtitle { font-size: 10pt; color: #555; margin: 1mm 0; }
.info { margin-bottom: 6mm; font-size: 9pt; }
.info-row { display: flex; justify-content: space-between; margin: 1mm 0; }
table { width: 100%; border-collapse: collapse; margin: 4mm 0; font-size: 9pt; }
th { background: #f0f0f0; padding: 2mm 1mm; text-align: left; border-bottom: 1px solid #333; }
td { padding: 1.5mm 1mm; border-bottom: 1px solid #ddd; vertical-align: top; }
td.num, th.num { text-align: right; }
td.sum, th.sum { text-align: right; font-weight: bold; }
.section-header { background: #f8f8f8; font-weight: bold; }
.totals { margin-top: 6mm; width: 60%; margin-left: auto; font-size: 10pt; }
.totals-row { display: flex; justify-content: space-between; padding: 1.5mm 0; border-bottom: 1px solid #eee; }
.totals-row.grand { font-weight: bold; font-size: 12pt; border-top: 2px solid #333; margin-top: 2mm; }
.footer { margin-top: 10mm; font-size: 8pt; color: #666; text-align: center; }
.page-break { page-break-after: always; }
tr { page-break-inside: avoid; }
thead { display: table-header-group; }
</style>
</head>
<body>
<div class="header">
  <h1>Смета № {{ estimate_id[:8] }}</h1>
  <div class="subtitle">{{ title }}</div>
  <div class="subtitle">{{ client }} | {{ object_name }} | {{ region }}</div>
</div>

<div class="info">
  <div class="info-row"><span>Дата:</span><span>{{ date }}</span></div>
  <div class="info-row"><span>Валюта:</span><span>{{ currency }}</span></div>
  <div class="info-row"><span>НДС:</span><span>{{ vat_rate }}%</span></div>
  <div class="info-row"><span>Накладные расходы:</span><span>{{ overhead_rate }}%</span></div>
</div>

{% for section in sections %}
<table>
  <thead>
    <tr class="section-header">
      <th colspan="7">{{ section.title }} ({{ section.position_count }} поз.)</th>
      <th class="sum">{{ section.subtotal }}</th>
    </tr>
    <tr>
      <th style="width:4%">№</th>
      <th style="width:12%">Код</th>
      <th style="width:35%">Наименование</th>
      <th style="width:7%">Ед.</th>
      <th style="width:10%" class="num">Кол-во</th>
      <th style="width:12%" class="num">Цена</th>
      <th style="width:10%" class="num">Сумма</th>
      <th style="width:10%">Источник</th>
    </tr>
  </thead>
  <tbody>
    {% for pos in section.positions %}
    <tr>
      <td>{{ loop.index }}</td>
      <td>{{ pos.code }}</td>
      <td>{{ pos.name }}</td>
      <td>{{ pos.unit }}</td>
      <td class="num">{{ pos.quantity }}</td>
      <td class="num">{{ pos.price }}</td>
      <td class="sum">{{ pos.sum }}</td>
      <td>{{ pos.source }}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
{% endfor %}

<div class="totals">
  <div class="totals-row"><span>Подытог:</span><span>{{ subtotal }}</span></div>
  <div class="totals-row"><span>Накладные расходы ({{ overhead_rate }}%):</span><span>{{ overhead_amount }}</span></div>
  <div class="totals-row"><span>НДС ({{ vat_rate }}%):</span><span>{{ vat_amount }}</span></div>
  <div class="totals-row grand"><span>ИТОГО:</span><span>{{ total }}</span></div>
</div>

<div class="footer">
  Документ сформирован системой Колибри | Страница <span class="pageNumber"></span>
</div>
</body>
</html>"""


def generate_estimate_pdf(estimate_data: Dict[str, Any]) -> bytes:
    """Generate professional PDF from estimate data. Returns PDF bytes."""
    env = Environment(loader=BaseLoader())
    template = env.from_string(ESTIMATE_TEMPLATE)

    # Format all monetary values
    from decimal import Decimal
    sections = []
    for sec in estimate_data.get("sections", []):
        positions = []
        for pos in sec.get("positions", []):
            positions.append({
                "code": pos.get("code", ""),
                "name": pos.get("name", ""),
                "unit": pos.get("unit", ""),
                "quantity": _format_ru(Decimal(pos.get("quantity", "0"))),
                "price": _format_currency(Decimal(pos.get("price", "0")), estimate_data.get("currency", "RUB")),
                "sum": _format_currency(Decimal(pos.get("sum", "0")), estimate_data.get("currency", "RUB")),
                "source": pos.get("source", ""),
            })
        sections.append({
            "title": sec.get("title", ""),
            "subtotal": _format_currency(Decimal(sec.get("subtotal", "0")), estimate_data.get("currency", "RUB")),
            "position_count": len(positions),
            "positions": positions,
        })

    ctx = {
        "estimate_id": estimate_data.get("id", ""),
        "title": estimate_data.get("title", ""),
        "client": estimate_data.get("client", ""),
        "object_name": estimate_data.get("object_name", ""),
        "region": estimate_data.get("region", ""),
        "date": estimate_data.get("created_at", ""),
        "currency": estimate_data.get("currency", "RUB"),
        "vat_rate": estimate_data.get("vat_rate", "20"),
        "overhead_rate": estimate_data.get("overhead_rate", "0"),
        "subtotal": _format_currency(Decimal(estimate_data.get("subtotal", "0")), estimate_data.get("currency", "RUB")),
        "overhead_amount": _format_currency(Decimal(estimate_data.get("overhead_amount", "0")), estimate_data.get("currency", "RUB")),
        "vat_amount": _format_currency(Decimal(estimate_data.get("vat_amount", "0")), estimate_data.get("currency", "RUB")),
        "total": _format_currency(Decimal(estimate_data.get("total", "0")), estimate_data.get("currency", "RUB")),
        "sections": sections,
    }

    html_str = template.render(**ctx)

    if WEASYPRINT_AVAILABLE:
        return HTML(string=html_str).write_pdf()
    else:
        # Fallback: return HTML as bytes with PDF content-type wrapper
        return html_str.encode("utf-8")


def generate_document_pdf(document_data: Dict[str, Any]) -> bytes:
    """Generate PDF from document HTML content."""
    html_content = document_data.get("content", "")
    title = document_data.get("title", "Документ")

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

    if WEASYPRINT_AVAILABLE:
        return HTML(string=template).write_pdf()
    return template.encode("utf-8")
