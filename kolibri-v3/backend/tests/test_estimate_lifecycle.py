from __future__ import annotations

from app.estimate_artifact import (
    empty_estimate_document,
    estimate_lifecycle_status,
    estimate_required_fields,
    estimate_view,
)


def test_empty_estimate_needs_input_and_never_presents_zero_as_ready() -> None:
    document = empty_estimate_document("2026-08-01T12:00:00Z")
    assert estimate_lifecycle_status(document, "ready") == "needs_input"
    assert estimate_required_fields(document) == [
        "Регион объекта",
        "Описание объекта и состав работ",
        "Основные размеры или объёмы",
    ]
    view = estimate_view(
        project_id="project_lifecycle_0001",
        document_id="document_lifecycle_0001",
        version=1,
        status="ready",
        document=document,
    )
    assert view["status"] == "needs_input"
    assert view["requiredFields"]
    assert view["totals"] == {"subtotal": "0.00", "total": "0.00"}


def test_ready_requires_complete_nonzero_rows_and_explicit_ready_state() -> None:
    document = empty_estimate_document("2026-08-01T12:00:00Z")
    document["region"] = "Москва"
    document["rows"] = [
        {
            "id": "row_lifecycle_0001",
            "section": "Работы",
            "kind": "work",
            "description": "Монтаж",
            "unit": "м²",
            "quantity": "10",
            "unit_price": "100.00",
            "line_total": "1000.00",
        }
    ]
    document["totals"] = {"subtotal": "1000.00", "total": "1000.00"}
    assert estimate_lifecycle_status(document, "draft") == "draft"
    assert estimate_lifecycle_status(document, "calculating") == "calculating"
    assert estimate_lifecycle_status(document, "ready") == "ready"
    assert estimate_lifecycle_status(document, "failed") == "failed"
