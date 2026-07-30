from decimal import Decimal

import pytest

from app import pdf_generator


pytestmark = pytest.mark.skipif(
    not pdf_generator.WEASYPRINT_AVAILABLE,
    reason="The production WeasyPrint renderer is required for layout assertions",
)


def _wide_estimate() -> dict:
    price = Decimal("12750.00")
    quantity = Decimal("12345.67")
    item_sum = price * quantity
    positions = [
        {
            "code": f"WORK-{index:04d}",
            "name": "Монтаж железобетонных конструкций и сопутствующие работы",
            "unit": "компл.",
            "quantity": str(quantity),
            "price": str(price),
            "sum": str(item_sum),
            # A deliberately unbreakable value reproduces the production
            # failure where the rightmost source column expanded past A4.
            "source": "REGIONALSOURCEWITHOUTSEPARATORS" * 5,
        }
        for index in range(36)
    ]
    subtotal = item_sum * len(positions)
    return {
        "id": "estimate-layout-regression",
        "title": "Смета на строительство одноэтажного дома 100 м²",
        "client": "Заказчик",
        "object_name": "Одноэтажный дом 100 м²",
        "region": "Лениногорск, Татарстан",
        "created_at": "2026-07-13",
        "currency": "RUB",
        "overhead_rate": "0",
        "vat_rate": "0",
        "subtotal": str(subtotal),
        "overhead_amount": "0",
        "vat_amount": "0",
        "total": str(subtotal),
        "sections": [
            {
                "title": "Основные строительные работы",
                "subtotal": str(subtotal),
                "positions": positions,
            }
        ],
    }


def _classes(box) -> set[str]:
    if box.element is None:
        return set()
    return set(box.element.get("class", "").split())


def test_estimate_table_stays_inside_a4_and_keeps_money_readable():
    from weasyprint import HTML

    document = HTML(string=pdf_generator._build_estimate_html(_wide_estimate())).render()

    expected_a4_width = 210 / 25.4 * 96
    expected_a4_height = 297 / 25.4 * 96
    assert len(document.pages) >= 4
    assert all(page.width == pytest.approx(expected_a4_width) for page in document.pages)
    assert all(page.height == pytest.approx(expected_a4_height) for page in document.pages)

    quantity_cells = []
    money_cells = []
    source_cells = []
    page_four_sources = []
    for page_number, page in enumerate(document.pages, start=1):
        page_box = page._page_box
        content_left = page_box.content_box_x()
        content_right = content_left + page_box.width

        for box in page_box.descendants():
            box_type = type(box).__name__
            if box_type == "TableBox":
                assert box.position_x >= content_left - 0.1
                assert box.position_x + box.border_width() <= content_right + 0.1
            if box_type != "TableCellBox":
                continue

            cell_left = box.position_x
            cell_right = cell_left + box.border_width()
            assert cell_left >= content_left - 0.1
            assert cell_right <= content_right + 0.1

            classes = _classes(box)
            text_boxes = [
                child
                for child in box.descendants()
                if type(child).__name__ == "TextBox"
            ]
            for text_box in text_boxes:
                assert text_box.position_x >= cell_left - 0.1
                assert text_box.position_x + text_box.width <= cell_right + 0.1

            if "money-value" in classes:
                money_cells.append(box)
            if "quantity-value" in classes:
                quantity_cells.append(box)
            if "source-cell" in classes:
                source_cells.append(box)
                if page_number == 4:
                    page_four_sources.append(box)

    assert quantity_cells
    assert money_cells
    assert source_cells
    assert page_four_sources
    assert all(
        len(
            [
                child
                for child in cell.descendants()
                if type(child).__name__ == "LineBox"
            ]
        )
        == 1
        for cell in quantity_cells
    )
    assert all(
        len(
            [
                child
                for child in cell.descendants()
                if type(child).__name__ == "LineBox"
            ]
        )
        == 1
        for cell in money_cells
    )
    assert any(
        len(
            [
                child
                for child in cell.descendants()
                if type(child).__name__ == "LineBox"
            ]
        )
        > 1
        for cell in source_cells
    )


def test_estimate_header_uses_human_date_and_real_page_counter():
    html = pdf_generator._build_estimate_html(_wide_estimate())

    assert "2026-07-13" in html
    assert "counter(page)" in html
    assert "counter(pages)" in html
    assert 'class="pageNumber"' not in html
    assert "Заказчик · Одноэтажный дом 100 м² · Лениногорск, Татарстан" in html
