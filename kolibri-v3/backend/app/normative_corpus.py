from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

import httpx
from pypdf import PdfReader


PARSER_VERSION = "normative-corpus/1.0.0"
MAX_NORMATIVE_BYTES = 20 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_SECTIONS = 20_000
MAX_SECTION_CHARACTERS = 6_000
SEARCH_TOKEN = re.compile(r"[0-9A-Za-zА-Яа-яЁё_-]+")
CODE_SPACE = re.compile(r"\s+")


class NormativeCorpusError(RuntimeError):
    pass


class NormativeSourceRejected(NormativeCorpusError):
    pass


class NormativeFetchError(NormativeCorpusError):
    pass


class NormativeParseError(NormativeCorpusError):
    pass


@dataclass(frozen=True, slots=True)
class FetchedNormative:
    content: bytes
    media_type: str
    final_url: str
    etag: str | None = None
    last_modified: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedSection:
    locator: str
    heading: str
    body: str


def canonical_code(value: str) -> str:
    normalized = CODE_SPACE.sub(" ", value.strip()).casefold()
    if not normalized or len(normalized) > 160:
        raise ValueError("normative code is invalid")
    return normalized


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8", "strict"))


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def source_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
        or parsed.fragment
    ):
        raise NormativeSourceRejected(
            "Нормативный источник должен быть официальным HTTPS URL."
        )
    return f"https://{parsed.hostname.casefold()}"


def source_policy(
    database: sqlite3.Connection,
    *,
    url: str,
) -> sqlite3.Row:
    origin = source_origin(url)
    row = database.execute(
        """
        SELECT *
        FROM normative_source_policies
        WHERE origin = ?
        LIMIT 1
        """,
        (origin,),
    ).fetchone()
    if row is None or int(row["storage_allowed"]) != 1:
        raise NormativeSourceRejected(
            "Источник не разрешён политикой нормативного корпуса."
        )
    if str(row["review_status"]) == "blocked":
        raise NormativeSourceRejected(
            "Источник заблокирован политикой нормативного корпуса."
        )
    return row


class NormativeFetcher:
    def __init__(self, *, timeout_seconds: float = 20.0) -> None:
        self._timeout = httpx.Timeout(
            timeout_seconds,
            connect=min(timeout_seconds, 8.0),
        )

    def fetch(
        self,
        database: sqlite3.Connection,
        *,
        url: str,
    ) -> FetchedNormative:
        current = url
        with httpx.Client(
            timeout=self._timeout,
            follow_redirects=False,
            headers={
                "Accept": "application/pdf,text/plain,text/html;q=0.9",
                "User-Agent": "Kolibri-Normative-Corpus/1.0",
            },
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                source_policy(database, url=current)
                try:
                    with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise NormativeFetchError(
                                    "Источник вернул некорректное перенаправление."
                                )
                            current = urljoin(current, location)
                            continue
                        if response.status_code != 200:
                            raise NormativeFetchError(
                                "Официальный источник временно недоступен."
                            )
                        chunks: list[bytes] = []
                        size = 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > MAX_NORMATIVE_BYTES:
                                raise NormativeFetchError(
                                    "Нормативный документ превышает допустимый размер."
                                )
                            chunks.append(chunk)
                        content = b"".join(chunks)
                        if not content:
                            raise NormativeFetchError(
                                "Официальный источник вернул пустой документ."
                            )
                        media_type = (
                            response.headers.get("content-type", "")
                            .split(";", 1)[0]
                            .strip()
                            .lower()
                        )
                        return FetchedNormative(
                            content=content,
                            media_type=media_type or "application/octet-stream",
                            final_url=str(response.url),
                            etag=response.headers.get("etag"),
                            last_modified=response.headers.get("last-modified"),
                        )
                except httpx.HTTPError as exc:
                    raise NormativeFetchError(
                        "Не удалось получить нормативный документ."
                    ) from exc
        raise NormativeFetchError(
            "Источник выполнил слишком много перенаправлений."
        )


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag in {"script", "style", "noscript", "svg"}:
            self._hidden_depth += 1
        elif tag in {"p", "div", "li", "br", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self._hidden_depth = max(0, self._hidden_depth - 1)
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._hidden_depth == 0:
            self.parts.append(data)


def _clean_text(value: str) -> str:
    lines = [
        re.sub(r"[ \t\u00a0]+", " ", line).strip()
        for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    return "\n".join(line for line in lines if line).strip()


def _chunk_text(value: str) -> list[ParsedSection]:
    paragraphs = [item.strip() for item in value.split("\n") if item.strip()]
    sections: list[ParsedSection] = []
    current: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal current, size
        if not current:
            return
        body = "\n".join(current)
        sections.append(
            ParsedSection(
                locator=f"block:{len(sections) + 1:05d}",
                heading=current[0][:240],
                body=body,
            )
        )
        current = []
        size = 0

    for paragraph in paragraphs:
        if size and size + len(paragraph) + 1 > MAX_SECTION_CHARACTERS:
            flush()
        current.append(paragraph)
        size += len(paragraph) + 1
    flush()
    return sections


def parse_normative_document(
    fetched: FetchedNormative,
) -> tuple[str, list[ParsedSection]]:
    media_type = fetched.media_type
    if fetched.content.startswith(b"%PDF") or media_type == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(fetched.content), strict=False)
            if reader.is_encrypted:
                raise NormativeParseError(
                    "Зашифрованный нормативный PDF не поддерживается."
                )
            pages: list[ParsedSection] = []
            extracted: list[str] = []
            for index, page in enumerate(reader.pages, start=1):
                body = _clean_text(page.extract_text() or "")
                if not body:
                    continue
                extracted.append(body)
                pages.append(
                    ParsedSection(
                        locator=f"page:{index}",
                        heading=f"Страница {index}",
                        body=body[:MAX_SECTION_CHARACTERS],
                    )
                )
            text = "\n\n".join(extracted)
        except NormativeParseError:
            raise
        except Exception as exc:
            raise NormativeParseError(
                "Не удалось разобрать нормативный PDF."
            ) from exc
        sections = pages
    elif media_type in {"text/html", "application/xhtml+xml"}:
        parser = _VisibleTextParser()
        try:
            parser.feed(fetched.content.decode("utf-8", "replace"))
        except Exception as exc:
            raise NormativeParseError(
                "Не удалось разобрать страницу нормативного документа."
            ) from exc
        text = _clean_text("".join(parser.parts))
        sections = _chunk_text(text)
    elif media_type.startswith("text/"):
        text = _clean_text(fetched.content.decode("utf-8", "replace"))
        sections = _chunk_text(text)
    else:
        raise NormativeParseError(
            "Формат нормативного документа пока не поддерживается."
        )
    if not text or not sections:
        raise NormativeParseError(
            "В нормативном документе не найден извлекаемый текст."
        )
    if len(sections) > MAX_SECTIONS:
        raise NormativeParseError(
            "Нормативный документ содержит слишком много разделов."
        )
    return text, sections


def fts_query(value: str) -> str:
    tokens = SEARCH_TOKEN.findall(value)
    if not tokens:
        raise ValueError("search query has no searchable tokens")
    return " AND ".join(f'"{token.replace(chr(34), "")}"' for token in tokens[:12])


def excerpt(body: str, query: str, *, limit: int = 520) -> str:
    lowered = body.casefold()
    positions = [
        lowered.find(token.casefold())
        for token in SEARCH_TOKEN.findall(query)
    ]
    positions = [position for position in positions if position >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - limit // 3)
    end = min(len(body), start + limit)
    value = body[start:end].strip()
    if start > 0:
        value = "… " + value
    if end < len(body):
        value += " …"
    return value


def active_on(
    *,
    status: str,
    effective_from: str | None,
    effective_to: str | None,
    as_of: date,
) -> bool:
    if status != "effective":
        return False
    value = as_of.isoformat()
    return (
        (effective_from is None or effective_from <= value)
        and (effective_to is None or effective_to >= value)
    )


def store_sections(
    database: sqlite3.Connection,
    *,
    edition_id: str,
    document_code: str,
    document_title: str,
    sections: Iterable[ParsedSection],
    applicability: dict[str, Any],
) -> None:
    for ordinal, section in enumerate(sections, start=1):
        section_id = f"norm_section_{uuid.uuid4().hex}"
        database.execute(
            """
            INSERT INTO normative_sections (
                id, edition_id, ordinal, locator, heading, body,
                body_sha256, applicability_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                section_id,
                edition_id,
                ordinal,
                section.locator,
                section.heading,
                section.body,
                sha256_text(section.body),
                canonical_json(applicability),
            ),
        )
        database.execute(
            """
            INSERT INTO normative_sections_fts (
                section_id, document_code, document_title,
                section_heading, body
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                section_id,
                document_code,
                document_title,
                section.heading,
                section.body,
            ),
        )
