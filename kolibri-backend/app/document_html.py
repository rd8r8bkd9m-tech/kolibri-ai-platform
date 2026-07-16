"""Strict, dependency-free sanitizer for editable business-document HTML."""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
from typing import Any


MAX_DOCUMENT_HTML_BYTES = 500_000
ALLOWED_TAGS = frozenset({
    "p", "br", "h1", "h2", "h3", "h4", "strong", "b", "em", "i", "u",
    "ul", "ol", "li", "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "blockquote", "hr", "span", "div", "small", "sup", "sub",
})
VOID_TAGS = frozenset({"br", "hr"})
BLOCKED_CONTENT_TAGS = frozenset({
    "script", "style", "iframe", "object", "embed", "svg", "math", "template",
    "noscript", "form", "input", "button", "textarea", "select", "option",
})
NUMERIC_ATTRIBUTES = frozenset({"colspan", "rowspan"})


class DocumentHtmlError(ValueError):
    pass


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.blocked_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if self.blocked_depth:
            if name in BLOCKED_CONTENT_TAGS:
                self.blocked_depth += 1
            return
        if name in BLOCKED_CONTENT_TAGS:
            self.blocked_depth = 1
            return
        if name not in ALLOWED_TAGS:
            return
        safe_attrs: list[str] = []
        if name in {"td", "th"}:
            for raw_name, raw_value in attrs:
                attr_name = raw_name.lower()
                value = str(raw_value or "")
                if attr_name in NUMERIC_ATTRIBUTES and value.isdigit() and 1 <= int(value) <= 100:
                    safe_attrs.append(f'{attr_name}="{value}"')
        suffix = f" {' '.join(safe_attrs)}" if safe_attrs else ""
        self.output.append(f"<{name}{suffix}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if self.blocked_depth:
            if name in BLOCKED_CONTENT_TAGS:
                self.blocked_depth -= 1
            return
        if name in ALLOWED_TAGS and name not in VOID_TAGS:
            self.output.append(f"</{name}>")

    def handle_data(self, data: str) -> None:
        if not self.blocked_depth:
            self.output.append(escape(data, quote=False))


def sanitize_document_html(value: Any) -> str:
    text = str(value or "")
    if len(text.encode("utf-8")) > MAX_DOCUMENT_HTML_BYTES:
        raise DocumentHtmlError("document_html_too_large")
    parser = _Sanitizer()
    try:
        parser.feed(text)
        parser.close()
    except (ValueError, RecursionError) as exc:
        raise DocumentHtmlError("document_html_invalid") from exc
    sanitized = "".join(parser.output)
    if len(sanitized.encode("utf-8")) > MAX_DOCUMENT_HTML_BYTES:
        raise DocumentHtmlError("document_html_too_large")
    return sanitized
