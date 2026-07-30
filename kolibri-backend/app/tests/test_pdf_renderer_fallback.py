"""Regression coverage for the independent portable PDF renderer."""

import pytest

from app import pdf_generator


def _runtime_failure(_html: str) -> bytes:
    raise OSError("native renderer unavailable")


def test_document_pdf_uses_portable_renderer_after_weasyprint_runtime_failure(
    monkeypatch,
):
    expected = b"%PDF-1.7\n" + (b"document" * 20)
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(pdf_generator, "WEASYPRINT_AVAILABLE", True)
    monkeypatch.setattr(pdf_generator, "_render_pdf", _runtime_failure)
    monkeypatch.setattr(
        pdf_generator,
        "_reportlab_document_pdf",
        lambda title, content: calls.append((title, content)) or expected,
    )

    result = pdf_generator.generate_document_pdf(
        {"title": "Проверенный PDF", "content": "<p>Содержимое</p>"}
    )

    assert result == expected
    assert calls == [("Проверенный PDF", "<p>Содержимое</p>")]


def test_estimate_pdf_uses_portable_renderer_after_weasyprint_runtime_failure(
    monkeypatch,
):
    expected = b"%PDF-1.7\n" + (b"estimate" * 20)
    estimate = {"title": "Смета", "sections": []}

    monkeypatch.setattr(pdf_generator, "WEASYPRINT_AVAILABLE", True)
    monkeypatch.setattr(pdf_generator, "_render_pdf", _runtime_failure)
    monkeypatch.setattr(pdf_generator, "_build_estimate_html", lambda value: "<html/>")
    monkeypatch.setattr(
        pdf_generator,
        "_reportlab_estimate_pdf",
        lambda value: expected if value is estimate else b"",
    )

    assert pdf_generator.generate_estimate_pdf(estimate) == expected


def test_pdf_generation_fails_closed_when_both_renderers_fail(monkeypatch):
    monkeypatch.setattr(pdf_generator, "WEASYPRINT_AVAILABLE", True)
    monkeypatch.setattr(pdf_generator, "_render_pdf", _runtime_failure)

    def fallback_failure(_title: str, _content: str) -> bytes:
        raise RuntimeError("portable renderer unavailable")

    monkeypatch.setattr(
        pdf_generator,
        "_reportlab_document_pdf",
        fallback_failure,
    )

    with pytest.raises(
        pdf_generator.PDFGenerationUnavailable,
        match="Both configured PDF renderers failed",
    ):
        pdf_generator.generate_document_pdf(
            {"title": "PDF", "content": "<p>Содержимое</p>"}
        )
