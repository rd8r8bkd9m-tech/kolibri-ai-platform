import pytest

from app.document_html import DocumentHtmlError, sanitize_document_html


@pytest.mark.parametrize(
    "payload",
    [
        '<img src=x onerror="alert(1)">',
        '<script>fetch("/api/v1/tasks")</script><p>Безопасный текст</p>',
        '<svg><a href="javascript:alert(1)">x</a></svg>',
        '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
        '<p style="background:url(https://attacker.invalid/x)">Текст</p>',
    ],
)
def test_document_html_removes_active_content_and_urls(payload: str):
    result = sanitize_document_html(payload)
    lowered = result.lower()
    assert "script" not in lowered
    assert "onerror" not in lowered
    assert "javascript:" not in lowered
    assert "https://" not in lowered
    assert "iframe" not in lowered
    assert "svg" not in lowered


def test_document_html_preserves_basic_business_formatting():
    result = sanitize_document_html(
        '<h2 class="x">Смета</h2><table><tr><td colspan="2" onclick="x">Итого</td></tr></table>'
    )
    assert result == '<h2>Смета</h2><table><tr><td colspan="2">Итого</td></tr></table>'


def test_document_html_rejects_oversized_content():
    with pytest.raises(DocumentHtmlError, match="document_html_too_large"):
        sanitize_document_html("x" * 500_001)
