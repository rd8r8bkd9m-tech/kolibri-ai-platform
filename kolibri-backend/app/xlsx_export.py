"""XLSX export — generates Excel files from estimate data."""
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill


def generate_estimate_xlsx(estimate: dict) -> bytes:
    """Generate XLSX file from estimate dict."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Смета"

    # Styles
    header_font = Font(name="Arial", bold=True, size=12)
    title_font = Font(name="Arial", bold=True, size=14)
    normal_font = Font(name="Arial", size=11)
    money_format = '#,##0.00 ₽'
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )
    header_fill = PatternFill(start_color="E8F8F7", end_color="E8F8F7", fill_type="solid")

    # Title
    ws.merge_cells('A1:F1')
    ws['A1'] = estimate.get('title', 'Смета')
    ws['A1'].font = title_font
    ws['A1'].alignment = Alignment(horizontal='center')

    # Info
    row = 3
    info = [
        ('Клиент:', estimate.get('client', '')),
        ('Объект:', estimate.get('object_name', '')),
        ('Регион:', estimate.get('region', '')),
        ('Дата:', estimate.get('created_at', '')[:10] if estimate.get('created_at') else ''),
    ]
    for label, value in info:
        ws[f'A{row}'] = label
        ws[f'A{row}'].font = Font(name="Arial", bold=True, size=11)
        ws[f'B{row}'] = value
        ws[f'B{row}'].font = normal_font
        row += 1

    row += 1

    # Sections
    for section in estimate.get('sections', []):
        ws.merge_cells(f'A{row}:F{row}')
        ws[f'A{row}'] = section.get('title', '')
        ws[f'A{row}'].font = header_font
        ws[f'A{row}'].fill = header_fill
        row += 1

        # Header
        headers = ['Код', 'Наименование', 'Ед.', 'Кол-во', 'Цена', 'Сумма']
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=row, column=col, value=h)
            cell.font = Font(name="Arial", bold=True, size=10)
            cell.border = thin_border
            cell.fill = header_fill
        row += 1

        # Positions
        for pos in section.get('positions', []):
            ws.cell(row=row, column=1, value=pos.get('code', '')).font = normal_font
            ws.cell(row=row, column=2, value=pos.get('name', '')).font = normal_font
            ws.cell(row=row, column=3, value=pos.get('unit', '')).font = normal_font
            ws.cell(row=row, column=4, value=float(pos.get('quantity', 0))).font = normal_font
            ws.cell(row=row, column=5, value=float(pos.get('price', 0))).font = normal_font
            ws.cell(row=row, column=5).number_format = money_format
            ws.cell(row=row, column=6, value=float(pos.get('sum', 0))).font = normal_font
            ws.cell(row=row, column=6).number_format = money_format
            for col in range(1, 7):
                ws.cell(row=row, column=col).border = thin_border
            row += 1

        # Section subtotal
        ws[f'E{row}'] = 'Итого:'
        ws[f'E{row}'].font = Font(name="Arial", bold=True, size=11)
        ws[f'F{row}'] = float(section.get('subtotal', 0))
        ws[f'F{row}'].font = Font(name="Arial", bold=True, size=11)
        ws[f'F{row}'].number_format = money_format
        row += 2

    # Totals
    ws[f'E{row}'] = 'Подытог:'
    ws[f'E{row}'].font = Font(name="Arial", bold=True, size=11)
    ws[f'F{row}'] = float(estimate.get('subtotal', 0))
    ws[f'F{row}'].number_format = money_format
    row += 1

    ws[f'E{row}'] = f'НДС ({estimate.get("vat_rate", "20")}%):'
    ws[f'E{row}'].font = Font(name="Arial", bold=True, size=11)
    ws[f'F{row}'] = float(estimate.get('vat_amount', 0))
    ws[f'F{row}'].number_format = money_format
    row += 1

    ws[f'E{row}'] = 'ИТОГО:'
    ws[f'E{row}'].font = Font(name="Arial", bold=True, size=12)
    ws[f'F{row}'] = float(estimate.get('total', 0))
    ws[f'F{row}'].font = Font(name="Arial", bold=True, size=12, color="3ABAB4")
    ws[f'F{row}'].number_format = money_format

    # Column widths
    ws.column_dimensions['A'].width = 12
    ws.column_dimensions['B'].width = 35
    ws.column_dimensions['C'].width = 8
    ws.column_dimensions['D'].width = 10
    ws.column_dimensions['E'].width = 12
    ws.column_dimensions['F'].width = 15

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
