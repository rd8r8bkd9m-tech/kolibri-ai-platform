#!/usr/bin/env python3
"""Collect canonical, unsigned P7 functional-gate evidence.

The collector is deliberately an HTTP client, not an in-process test harness.
Every backend assertion crosses a real socket boundary and every artifact
assertion is bound to downloaded bytes.  Browser assertions are accepted only
from a separately produced, release-bound Playwright evidence document.  This
program never loads a signing key and never creates a signature; the release
controller signs the canonical output in a separate trust boundary.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import http.cookiejar
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
import stat
import struct
import sys
import tempfile
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
import zipfile


SCHEMA_VERSION = "kolibri.p7.functional-gates.v3"
BROWSER_SCHEMA_VERSION = "kolibri.p7.browser-evidence.v2"
REQUIRED_BROWSER_VIEWPORTS = {
    "desktop_1440",
    "tablet_768",
    "mobile_390",
    "mobile_360",
}
MIN_PRODUCTION_PROBE_TTL_SECONDS = 7 * 60 * 60
COLLECTOR_IDENTITY = "kolibri-p7-gate-collector"
COLLECTOR_VERSION = "1.0.0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
RELEASE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
EXPECTED_GATES = (
    "release_identity",
    "estimate_create_regional",
    "estimate_recalculate",
    "estimate_revisions",
    "estimate_pdf",
    "capability_registry",
    "chat_durable_stream",
    "web_search_sources",
    "file_lifecycle",
    "document_artifacts",
    "image_lifecycle",
    "site_app_lifecycle",
    "developer_api_keys",
    "structured_apis",
    "shell_desktop_mobile",
    "optional_capability_gates",
)
MAX_HTTP_BODY_BYTES = 128 * 1024 * 1024
MAX_BROWSER_EVIDENCE_BYTES = 16 * 1024 * 1024
BROWSER_EVIDENCE_MAX_AGE = timedelta(minutes=30)
DOCUMENT_FORMATS: dict[str, tuple[str, bytes, dict[str, Any]]] = {
    "pdf": (
        "application/pdf",
        b"%PDF-",
        {"title": "P7 проверенный отчёт", "content": "Проверка P7: реальный PDF артефакт."},
    ),
    "docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"PK",
        {"title": "P7 проверенный документ", "content": "Проверка P7: реальный DOCX артефакт."},
    ),
    "xlsx": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        b"PK",
        {
            "estimate": {
                "title": "P7 проверенная таблица",
                "currency": "RUB",
                "version": 1,
                "region": "Лениногорск, Республика Татарстан",
                "sections": [
                    {
                        "title": "Проверка",
                        "subtotal": "1000.00",
                        "positions": [
                            {
                                "code": "P7-001",
                                "name": "Проверочная позиция",
                                "unit": "шт.",
                                "quantity": "2",
                                "price": "500.00",
                                "sum": "1000.00",
                            }
                        ],
                    }
                ],
                "subtotal": "1000.00",
                "overhead_rate": "0",
                "overhead_amount": "0.00",
                "vat_rate": "0",
                "vat_amount": "0.00",
                "total": "1000.00",
            }
        },
    ),
    "pptx": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        b"PK",
        {
            "title": "P7 проверенная презентация",
            "slides": [
                {"title": "P7", "bullets": ["Реальные bytes", "Повторное открытие"]},
                {"title": "Итог", "content": "Артефакт проверен."},
            ],
        },
    ),
}


class GateCollectorError(RuntimeError):
    """A bounded, non-secret error that blocks one or more release gates."""

    def __init__(self, code: str):
        self.code = _safe_code(code)
        super().__init__(self.code)


def _safe_code(value: Any) -> str:
    text = re.sub(r"[^a-z0-9_.-]+", "_", str(value or "gate_failed").lower()).strip("_")
    return (text or "gate_failed")[:120]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise GateCollectorError("target_origin_invalid")
    return f"{parsed.scheme}://{parsed.netloc}"


def _content_type(headers: Mapping[str, str]) -> str:
    return str(headers.get("content-type") or "").split(";", 1)[0].strip().lower()


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str

    def json(self) -> Any:
        try:
            return json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GateCollectorError("http_response_json_invalid") from exc


class HttpSession:
    """Cookie-preserving, same-origin HTTP transport using the standard library."""

    def __init__(self, origin: str, *, timeout: float):
        self.origin = _origin(origin)
        self.timeout = max(1.0, float(timeout))
        self.cookies = http.cookiejar.CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self.cookies))

    def _url(self, path: str) -> str:
        raw = str(path or "").strip()
        supplied = urlsplit(raw)
        candidate = raw if supplied.scheme or supplied.netloc else urljoin(f"{self.origin}/", raw.lstrip("/"))
        parsed_origin = urlsplit(self.origin)
        parsed = urlsplit(candidate)
        if (
            (parsed.scheme, parsed.netloc) != (parsed_origin.scheme, parsed_origin.netloc)
            or parsed.username is not None
            or parsed.password is not None
            or bool(parsed.fragment)
        ):
            raise GateCollectorError("cross_origin_request_forbidden")
        return candidate

    def _bounded_body(self, response: Any) -> bytes:
        declared = response.headers.get("Content-Length")
        if declared:
            try:
                if int(declared) > MAX_HTTP_BODY_BYTES:
                    raise GateCollectorError("http_response_too_large")
            except ValueError as exc:
                raise GateCollectorError("http_content_length_invalid") from exc
        body = response.read(MAX_HTTP_BODY_BYTES + 1)
        if len(body) > MAX_HTTP_BODY_BYTES:
            raise GateCollectorError("http_response_too_large")
        return body

    def _assert_final_origin(self, url: str) -> None:
        expected = urlsplit(self.origin)
        actual = urlsplit(url)
        if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
            raise GateCollectorError("cross_origin_redirect_forbidden")

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> HttpResponse:
        if json_body is not None and body is not None:
            raise GateCollectorError("http_body_ambiguous")
        url = self._url(path)
        if query:
            separator = "&" if urlsplit(url).query else "?"
            url = f"{url}{separator}{urlencode({key: str(value) for key, value in query.items()})}"
        request_headers = {
            "Accept": "application/json",
            "User-Agent": f"Kolibri-P7-Gate-Collector/{COLLECTOR_VERSION}",
            **{str(key): str(value) for key, value in (headers or {}).items()},
        }
        request_body = body
        if json_body is not None:
            request_body = canonical_json(json_body)
            request_headers.setdefault("Content-Type", "application/json")
        request = Request(url, data=request_body, headers=request_headers, method=method.upper())
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                final_url = response.geturl()
                self._assert_final_origin(final_url)
                return HttpResponse(
                    status=int(response.status),
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=self._bounded_body(response),
                    url=final_url,
                )
        except HTTPError as exc:
            final_url = exc.geturl()
            self._assert_final_origin(final_url)
            return HttpResponse(
                status=int(exc.code),
                headers={key.lower(): value for key, value in exc.headers.items()},
                body=self._bounded_body(exc),
                url=final_url,
            )
        except (URLError, TimeoutError, OSError) as exc:
            raise GateCollectorError("http_transport_failed") from exc

    def multipart(
        self,
        path: str,
        *,
        field_name: str,
        filename: str,
        content_type: str,
        content: bytes,
    ) -> HttpResponse:
        boundary = f"kolibri-p7-{secrets.token_hex(12)}"
        disposition = (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
        ).encode("ascii")
        body = b"".join(
            (
                f"--{boundary}\r\n".encode("ascii"),
                disposition,
                f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
                content,
                f"\r\n--{boundary}--\r\n".encode("ascii"),
            )
        )
        return self.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )


def _expect(response: HttpResponse, allowed: int | Iterable[int], code: str) -> HttpResponse:
    statuses = {allowed} if isinstance(allowed, int) else set(allowed)
    if response.status not in statuses:
        raise GateCollectorError(f"{code}_http_{response.status}")
    return response


def _object(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GateCollectorError(code)
    return value


def _list(value: Any, code: str) -> list[Any]:
    if not isinstance(value, list):
        raise GateCollectorError(code)
    return value


def _required_text(value: Any, code: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise GateCollectorError(code)
    return text


def _decimal(value: Any, code: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise GateCollectorError(code) from exc
    if not parsed.is_finite():
        raise GateCollectorError(code)
    return parsed


def _estimate_total_is_deterministic(estimate: Mapping[str, Any]) -> bool:
    subtotal = Decimal("0")
    try:
        for section in _list(estimate.get("sections"), "estimate_sections_invalid"):
            section_total = Decimal("0")
            for position in _list(_object(section, "estimate_section_invalid").get("positions"), "estimate_positions_invalid"):
                item = _object(position, "estimate_position_invalid")
                expected = (_decimal(item.get("quantity"), "estimate_quantity_invalid") * _decimal(item.get("price"), "estimate_price_invalid")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if _decimal(item.get("sum"), "estimate_sum_invalid") != expected:
                    return False
                section_total += expected
            section_total = section_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if _decimal(_object(section, "estimate_section_invalid").get("subtotal"), "estimate_subtotal_invalid") != section_total:
                return False
            subtotal += section_total
        subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        overhead = (subtotal * _decimal(estimate.get("overhead_rate"), "estimate_overhead_invalid") / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        vat = ((subtotal + overhead) * _decimal(estimate.get("vat_rate"), "estimate_vat_invalid") / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total = subtotal + overhead + vat
        return all(
            (
                _decimal(estimate.get("subtotal"), "estimate_total_invalid") == subtotal,
                _decimal(estimate.get("overhead_amount"), "estimate_total_invalid") == overhead,
                _decimal(estimate.get("vat_amount"), "estimate_total_invalid") == vat,
                _decimal(estimate.get("total"), "estimate_total_invalid") == total,
            )
        )
    except GateCollectorError:
        return False


def _estimate_create_payload(data: Mapping[str, Any]) -> dict[str, Any]:
    allowed_top = (
        "title",
        "client",
        "object_name",
        "region",
        "currency",
        "overhead_rate",
        "vat_rate",
        "estimate_status",
        "pricing_status",
        "scope_status",
        "source_note",
        "assumptions",
        "questions",
        "price_sources",
        "evidence_issues",
    )
    payload = {key: data[key] for key in allowed_top if key in data}
    sections: list[dict[str, Any]] = []
    for raw_section in _list(data.get("sections"), "estimate_sections_missing"):
        section = _object(raw_section, "estimate_section_invalid")
        positions: list[dict[str, Any]] = []
        for raw_position in _list(section.get("positions"), "estimate_positions_invalid"):
            position = _object(raw_position, "estimate_position_invalid")
            positions.append(
                {
                    key: position[key]
                    for key in (
                        "code",
                        "name",
                        "unit",
                        "quantity",
                        "price",
                        "source",
                        "price_evidence",
                        "comment",
                    )
                    if key in position
                }
            )
        sections.append({"title": section.get("title"), "positions": positions})
    payload["sections"] = sections
    return payload


def _estimate_signature(data: Mapping[str, Any]) -> str:
    value = {
        "title": data.get("title"),
        "object_name": data.get("object_name"),
        "region": data.get("region"),
        "sections": [
            {
                "title": section.get("title"),
                "positions": [
                    {"code": item.get("code"), "name": item.get("name"), "unit": item.get("unit")}
                    for item in section.get("positions", [])
                    if isinstance(item, dict)
                ],
            }
            for section in data.get("sections", [])
            if isinstance(section, dict)
        ],
    }
    return _sha256(canonical_json(value))


def _extract_estimate_action(payload: Mapping[str, Any]) -> dict[str, Any]:
    actions = _list(payload.get("actions"), "estimate_actions_missing")
    for action in actions:
        if isinstance(action, dict) and action.get("type") == "create_estimate":
            return _object(action.get("data"), "estimate_action_data_invalid")
    raise GateCollectorError("estimate_action_missing")


def _artifact_from_tool(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = _object(payload.get("result"), "tool_result_invalid")
    artifact = result.get("artifact") if isinstance(result.get("artifact"), dict) else result
    artifact = _object(artifact, "tool_artifact_missing")
    digest = str(artifact.get("sha256") or "")
    if not SHA256_RE.fullmatch(digest):
        raise GateCollectorError("tool_artifact_sha256_invalid")
    return artifact


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    return None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(b"\xff\xd8"):
        return None
    offset = 2
    while offset + 9 <= len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        marker = data[offset + 1]
        offset += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            return None
        length = int.from_bytes(data[offset : offset + 2], "big")
        if length < 2 or offset + length > len(data):
            return None
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if length < 7:
                return None
            return (
                int.from_bytes(data[offset + 5 : offset + 7], "big"),
                int.from_bytes(data[offset + 3 : offset + 5], "big"),
            )
        offset += length
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    kind = data[12:16]
    if kind == b"VP8X" and len(data) >= 30:
        return (
            1 + int.from_bytes(data[24:27], "little"),
            1 + int.from_bytes(data[27:30], "little"),
        )
    if kind == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        return (
            int.from_bytes(data[26:28], "little") & 0x3FFF,
            int.from_bytes(data[28:30], "little") & 0x3FFF,
        )
    if kind == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        return ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
    return None


def image_dimensions(data: bytes, mime_type: str) -> tuple[int, int]:
    dimensions = {
        "image/png": _png_dimensions,
        "image/jpeg": _jpeg_dimensions,
        "image/webp": _webp_dimensions,
    }.get(mime_type, lambda _data: None)(data)
    if dimensions is None or min(dimensions) <= 0:
        raise GateCollectorError("image_dimensions_invalid")
    return dimensions


def _pdf_bytes_valid(data: bytes) -> bool:
    return (
        len(data) > 256
        and data.startswith(b"%PDF-")
        and b"%%EOF" in data[-1024:]
    )


def _safe_zip(data: bytes, code: str) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(BytesIO(data))
        entries = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise GateCollectorError(code) from exc
    if not entries or len(entries) > 2048:
        archive.close()
        raise GateCollectorError(code)
    total_uncompressed = 0
    for entry in entries:
        normalized = entry.filename.replace("\\", "/")
        parts = [part for part in normalized.split("/") if part]
        total_uncompressed += int(entry.file_size)
        if (
            normalized.startswith("/")
            or ".." in parts
            or bool(entry.flag_bits & 0x1)
            or total_uncompressed > 256 * 1024 * 1024
        ):
            archive.close()
            raise GateCollectorError(code)
    return archive


def _ooxml_bytes_valid(data: bytes, format_id: str) -> bool:
    expected = {
        "docx": {"[Content_Types].xml", "word/document.xml"},
        "xlsx": {"[Content_Types].xml", "xl/workbook.xml"},
        "pptx": {"[Content_Types].xml", "ppt/presentation.xml"},
    }.get(format_id)
    if expected is None:
        return False
    try:
        with _safe_zip(data, f"document_{format_id}_archive_invalid") as archive:
            names = set(archive.namelist())
            return expected.issubset(names) and all(
                archive.getinfo(name).file_size > 0 for name in expected
            )
    except GateCollectorError:
        return False


def _project_archive_valid(data: bytes) -> bool:
    try:
        with _safe_zip(data, "project_archive_invalid") as archive:
            names = set(archive.namelist())
            if "index.html" not in names or archive.getinfo("index.html").file_size > 2 * 1024 * 1024:
                return False
            index = archive.read("index.html")
            return b"<html" in index.lower() or b"<!doctype html" in index.lower()
    except (GateCollectorError, OSError, RuntimeError, zipfile.BadZipFile):
        return False


def _sse_events(response: HttpResponse) -> list[tuple[str, Any]]:
    if _content_type(response.headers) != "text/event-stream":
        raise GateCollectorError("sse_content_type_invalid")
    try:
        text = response.body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateCollectorError("sse_encoding_invalid") from exc
    events: list[tuple[str, Any]] = []
    for block in re.split(r"\r?\n\r?\n", text):
        if not block.strip():
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if not data_lines:
            continue
        data_text = "\n".join(data_lines)
        if data_text == "[DONE]":
            events.append((event_name, "[DONE]"))
            continue
        try:
            events.append((event_name, json.loads(data_text)))
        except json.JSONDecodeError as exc:
            raise GateCollectorError("sse_json_invalid") from exc
    if not events:
        raise GateCollectorError("sse_events_missing")
    return events


def _recursive_has_key(value: Any, forbidden: str) -> bool:
    if isinstance(value, dict):
        return any(key == forbidden or _recursive_has_key(item, forbidden) for key, item in value.items())
    if isinstance(value, list):
        return any(_recursive_has_key(item, forbidden) for item in value)
    return False


def _read_secret_file(path: Path) -> str:
    try:
        info = path.lstat()
    except OSError as exc:
        raise GateCollectorError("owner_token_file_unreadable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or info.st_size > 4096:
        raise GateCollectorError("owner_token_file_invalid")
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise GateCollectorError("owner_token_file_unreadable") from exc
    if not value or len(value) > 1024 or "\n" in value or "\r" in value:
        raise GateCollectorError("owner_token_file_invalid")
    return value


def _load_browser_evidence(
    path: Path,
    *,
    release_id: str,
    manifest_sha256: str,
    backend_origin: str,
    frontend_origin: str,
) -> tuple[dict[str, Any], str]:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_size <= 0
            or info.st_size > MAX_BROWSER_EVIDENCE_BYTES
        ):
            raise GateCollectorError("browser_evidence_file_invalid")
        raw = path.read_bytes()
        payload = json.loads(raw)
    except GateCollectorError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise GateCollectorError("browser_evidence_invalid") from exc
    payload = _object(payload, "browser_evidence_invalid")
    binding = {
        "schema_version": BROWSER_SCHEMA_VERSION,
        "release_id": release_id,
        "manifest_sha256": manifest_sha256,
        "backend_origin": backend_origin,
        "frontend_origin": frontend_origin,
    }
    if any(payload.get(key) != value for key, value in binding.items()):
        raise GateCollectorError("browser_evidence_binding_mismatch")
    if payload.get("runner") != "playwright":
        raise GateCollectorError("browser_evidence_runner_invalid")
    run_id = str(payload.get("run_id") or "")
    if not SAFE_ID_RE.fullmatch(run_id):
        raise GateCollectorError("browser_evidence_run_id_invalid")
    collected_at = str(payload.get("collected_at") or "")
    try:
        collected = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GateCollectorError("browser_evidence_timestamp_invalid") from exc
    if collected.tzinfo is None:
        raise GateCollectorError("browser_evidence_timestamp_invalid")
    age = datetime.now(timezone.utc) - collected.astimezone(timezone.utc)
    if age < -timedelta(minutes=5) or age > BROWSER_EVIDENCE_MAX_AGE:
        raise GateCollectorError("browser_evidence_stale")
    return payload, _sha256(raw)


class P7GateCollector:
    def __init__(
        self,
        *,
        release_id: str,
        manifest_sha256: str,
        backend_origin: str,
        frontend_origin: str,
        browser_evidence_path: Path,
        owner_token_file: Path,
        timeout: float = 30.0,
    ):
        if not RELEASE_ID_RE.fullmatch(release_id):
            raise GateCollectorError("release_id_invalid")
        if not SHA256_RE.fullmatch(manifest_sha256):
            raise GateCollectorError("manifest_sha256_invalid")
        self.release_id = release_id
        self.manifest_sha256 = manifest_sha256
        self.backend_origin = _origin(backend_origin)
        self.frontend_origin = _origin(frontend_origin)
        self.backend = HttpSession(self.backend_origin, timeout=timeout)
        self.frontend = HttpSession(self.frontend_origin, timeout=timeout)
        self.timeout = max(1.0, float(timeout))
        self.owner_token = _read_secret_file(owner_token_file)
        self.run_id = f"p7-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(6)}"
        self.browser, self.browser_sha256 = _load_browser_evidence(
            browser_evidence_path,
            release_id=release_id,
            manifest_sha256=manifest_sha256,
            backend_origin=self.backend_origin,
            frontend_origin=self.frontend_origin,
        )
        self.state: dict[str, Any] = {}

    @property
    def owner_headers(self) -> dict[str, str]:
        return {"X-Kolibri-Owner-Token": self.owner_token}

    @property
    def api_headers(self) -> dict[str, str]:
        key = _required_text(self.state.get("api_key"), "operational_api_key_missing")
        return {"Authorization": f"Bearer {key}"}

    def _gate(self, method: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            value = method()
            if not isinstance(value, dict):
                raise GateCollectorError("gate_result_invalid")
            return {"status": "passed", **value}
        except GateCollectorError as exc:
            return {"status": "failed", "error_code": exc.code}
        except Exception as exc:  # no provider/secret text crosses evidence boundary
            return {"status": "failed", "error_code": _safe_code(type(exc).__name__)}

    def _bootstrap(self) -> None:
        response = _expect(
            self.backend.request("POST", "/api/v1/shell/bootstrap", json_body={}),
            200,
            "shell_bootstrap",
        )
        session = _object(response.json(), "shell_bootstrap_invalid")
        if not SAFE_ID_RE.fullmatch(str(session.get("session_id") or "")):
            raise GateCollectorError("shell_session_id_invalid")

    def _create_api_key(self, label: str) -> tuple[dict[str, Any], str]:
        response = _expect(
            self.backend.request(
                "POST",
                "/v1/api-keys",
                json_body={"name": f"P7 {label} {self.run_id}"[:80]},
                headers=self.owner_headers,
            ),
            201,
            "api_key_create",
        )
        payload = _object(response.json(), "api_key_create_invalid")
        key_id = _required_text(payload.get("id"), "api_key_id_missing")
        secret = _required_text(payload.get("secret"), "api_key_secret_missing")
        if payload.get("secret_shown_once") is not True:
            raise GateCollectorError("api_key_secret_once_unproved")
        return payload, secret

    def _revoke_api_key(self, key_id: str) -> HttpResponse:
        return self.backend.request(
            "DELETE",
            f"/v1/api-keys/{quote(key_id, safe='')}",
            headers=self.owner_headers,
        )

    def gate_developer_api_keys(self) -> dict[str, Any]:
        created, secret = self._create_api_key("revocation-proof")
        key_id = str(created["id"])
        revoked: HttpResponse | None = None
        try:
            used = self.backend.request(
                "GET", "/v1/models", headers={"Authorization": f"Bearer {secret}"}
            )
            _expect(used, 200, "api_key_use")
            listing = _expect(
                self.backend.request("GET", "/v1/api-keys", headers=self.owner_headers),
                200,
                "api_key_list",
            )
            listed = _object(listing.json(), "api_key_list_invalid")
            if _recursive_has_key(listed, "secret"):
                raise GateCollectorError("api_key_secret_leaked_in_list")
        finally:
            revoked = self._revoke_api_key(key_id)
        _expect(revoked, 200, "api_key_revoke")
        denied = self.backend.request(
            "GET", "/v1/models", headers={"Authorization": f"Bearer {secret}"}
        )
        if denied.status not in {401, 403}:
            raise GateCollectorError("revoked_api_key_accepted")

        operational, operational_secret = self._create_api_key("functional-gates")
        self.state["api_key"] = operational_secret
        self.state["api_key_id"] = str(operational["id"])
        return {
            "create_http_status": 201,
            "secret_shown_once": True,
            "created_key_request_http_status": used.status,
            "list_http_status": listing.status,
            "secret_present_in_list": False,
            "revoke_http_status": revoked.status,
            "revoked_key_request_http_status": denied.status,
        }

    def gate_release_identity(self) -> dict[str, Any]:
        health_response = _expect(
            self.backend.request("GET", "/api/health"), 200, "backend_health"
        )
        health = _object(health_response.json(), "backend_health_invalid")
        backend_release = _required_text(health.get("release_id"), "backend_release_missing")
        backend_header = _required_text(
            health_response.headers.get("x-kolibri-release"), "backend_release_header_missing"
        )
        frontend_response = _expect(
            self.frontend.request("GET", "/", headers={"Accept": "text/html"}),
            200,
            "frontend_root",
        )
        if _content_type(frontend_response.headers) != "text/html" or b"<html" not in frontend_response.body.lower():
            raise GateCollectorError("frontend_html_invalid")
        frontend_header = _required_text(
            frontend_response.headers.get("x-kolibri-release"), "frontend_release_header_missing"
        )
        frontend_build = _required_text(
            self.browser.get("frontend_build_release_id"), "frontend_build_release_missing"
        )
        if {backend_release, backend_header, frontend_header, frontend_build} != {self.release_id}:
            raise GateCollectorError("release_identity_mismatch")
        return {
            "backend_release_id": backend_release,
            "frontend_release_id": frontend_build,
            "response_header_release_id": frontend_header,
        }

    def _request_estimate_draft(self, prompt: str) -> dict[str, Any]:
        response = _expect(
            self.backend.request(
                "POST",
                "/api/v1/responses",
                json_body={"model": "kolibri", "input": prompt},
                headers={"Idempotency-Key": f"estimate-{secrets.token_hex(8)}"},
            ),
            200,
            "estimate_provider_response",
        )
        payload = _object(response.json(), "estimate_provider_response_invalid")
        if payload.get("status") != "completed":
            raise GateCollectorError("estimate_provider_not_completed")
        return _extract_estimate_action(payload)

    def gate_estimate_create_regional(self) -> dict[str, Any]:
        target = self._request_estimate_draft(
            "Составь реальную смету одноэтажного дома 100 м² в Лениногорске, Татарстан, "
            "с актуальными подтверждёнными региональными ценами и источниками."
        )
        control = self._request_estimate_draft(
            "Составь реальную смету отдельного кирпичного гаража 36 м² в Казани, Татарстан, "
            "с актуальными подтверждёнными региональными ценами и источниками."
        )
        target_text = " ".join(
            str(target.get(key) or "") for key in ("title", "object_name", "region")
        ).casefold()
        target_sections = [
            section for section in target.get("sections", []) if isinstance(section, dict)
        ]
        target_positions = [
            position
            for section in target_sections
            for position in section.get("positions", [])
            if isinstance(position, dict)
        ]
        unique_sections = {
            str(section.get("title") or "").strip().casefold()
            for section in target_sections
            if str(section.get("title") or "").strip()
        }
        unique_positions = {
            (
                str(position.get("code") or "").strip().casefold(),
                str(position.get("name") or "").strip().casefold(),
            )
            for position in target_positions
            if str(position.get("name") or "").strip()
        }
        individualized = (
            "100" in target_text
            and "лениногор" in target_text
            and len(unique_sections) >= 3
            and len(unique_positions) >= 6
        )
        template_reuse = _estimate_signature(target) == _estimate_signature(control)
        if not individualized:
            raise GateCollectorError("estimate_scope_not_individualized")
        if template_reuse:
            raise GateCollectorError("estimate_template_reuse_detected")

        create_response = _expect(
            self.backend.request(
                "POST", "/api/v1/estimates", json_body=_estimate_create_payload(target)
            ),
            201,
            "estimate_create",
        )
        created = _object(create_response.json(), "estimate_create_invalid")
        estimate_id = _required_text(created.get("id"), "estimate_id_missing")
        truth_status = str(created.get("pricing_status") or created.get("estimate_status") or "")
        evidence = [
            record
            for section in created.get("sections", [])
            if isinstance(section, dict)
            for position in section.get("positions", [])
            if isinstance(position, dict)
            for record in position.get("price_evidence", [])
            if isinstance(record, dict)
        ]
        created_positions = [
            position
            for section in created.get("sections", [])
            if isinstance(section, dict)
            for position in section.get("positions", [])
            if isinstance(position, dict)
        ]
        every_position_has_evidence = bool(created_positions) and all(
            isinstance(position.get("price_evidence"), list)
            and any(isinstance(record, dict) for record in position["price_evidence"])
            for position in created_positions
        )
        if (
            truth_status not in {"source_backed", "verified"}
            or len(created_positions) < 6
            or not every_position_has_evidence
        ):
            raise GateCollectorError("estimate_truth_evidence_missing")
        self.state.update(
            {
                "estimate_id": estimate_id,
                "estimate_before": created,
                "estimate_etag": create_response.headers.get("etag") or f'"{created.get("version")}"',
            }
        )
        return {
            "http_status": create_response.status,
            "estimate_id": estimate_id,
            "individualized_scope": True,
            "template_reuse_detected": False,
            "truth_status": truth_status,
            "evidence_count": len(evidence),
            "section_count": len(target_sections),
            "position_count": len(created_positions),
        }

    def gate_estimate_recalculate(self) -> dict[str, Any]:
        estimate_id = _required_text(self.state.get("estimate_id"), "estimate_dependency_missing")
        before = _object(self.state.get("estimate_before"), "estimate_dependency_missing")
        version_before = int(before.get("version") or 0)
        payload = _estimate_create_payload(before)
        changed = False
        for section in payload.get("sections", []):
            for position in section.get("positions", []):
                quantity = _decimal(position.get("quantity"), "estimate_quantity_invalid")
                if quantity > 0:
                    position["quantity"] = str((quantity + Decimal("1")).normalize())
                    changed = True
                    break
            if changed:
                break
        if not changed:
            raise GateCollectorError("estimate_position_not_editable")
        update_response = _expect(
            self.backend.request(
                "PUT",
                f"/api/v1/estimates/{quote(estimate_id, safe='')}",
                json_body=payload,
                headers={"If-Match": str(self.state["estimate_etag"])},
            ),
            200,
            "estimate_update",
        )
        after = _object(update_response.json(), "estimate_update_invalid")
        version_after = int(after.get("version") or 0)
        deterministic = _estimate_total_is_deterministic(after)
        reloaded_response = _expect(
            self.backend.request("GET", f"/api/v1/estimates/{quote(estimate_id, safe='')}") ,
            200,
            "estimate_reload",
        )
        reloaded = _object(reloaded_response.json(), "estimate_reload_invalid")
        persisted = (
            int(reloaded.get("version") or 0) == version_after
            and str(reloaded.get("total")) == str(after.get("total"))
        )
        if version_after <= version_before or str(after.get("total")) == str(before.get("total")):
            raise GateCollectorError("estimate_version_or_total_unchanged")
        if not deterministic or not persisted:
            raise GateCollectorError("estimate_recalculation_unproved")
        self.state["estimate_after"] = after
        return {
            "http_status": update_response.status,
            "server_decimal_recalculation": True,
            "version_before": version_before,
            "version_after": version_after,
            "total_before": str(before.get("total")),
            "total_after": str(after.get("total")),
            "persisted_after_reload": True,
        }

    def gate_estimate_revisions(self) -> dict[str, Any]:
        estimate_id = _required_text(self.state.get("estimate_id"), "estimate_dependency_missing")
        before = _object(self.state.get("estimate_before"), "estimate_dependency_missing")
        response = _expect(
            self.backend.request("GET", f"/api/v1/estimates/{quote(estimate_id, safe='')}/revisions"),
            200,
            "estimate_revisions",
        )
        payload = _object(response.json(), "estimate_revisions_invalid")
        items = _list(payload.get("items"), "estimate_revisions_invalid")
        version = int(before.get("version") or 0)
        revision_path = f"/api/v1/estimates/{quote(estimate_id, safe='')}/revisions/{version}"
        first = _expect(self.backend.request("GET", revision_path), 200, "estimate_revision_get")
        second = _expect(self.backend.request("GET", revision_path), 200, "estimate_revision_get")
        first_payload = _object(first.json(), "estimate_revision_invalid")
        snapshot = _object(first_payload.get("snapshot"), "estimate_revision_snapshot_missing")
        second_payload = _object(second.json(), "estimate_revision_invalid")
        second_snapshot = _object(
            second_payload.get("snapshot"), "estimate_revision_snapshot_missing"
        )
        immutable = (
            canonical_json(snapshot) == canonical_json(second_snapshot)
            and str(snapshot.get("total")) == str(before.get("total"))
            and int(snapshot.get("version") or 0) == version
        )
        if len(items) < 2 or not immutable:
            raise GateCollectorError("estimate_revision_immutability_unproved")
        return {
            "http_status": response.status,
            "revision_count": len(items),
            "previous_revision_immutable": True,
        }

    def gate_estimate_pdf(self) -> dict[str, Any]:
        estimate_id = _required_text(self.state.get("estimate_id"), "estimate_dependency_missing")
        after = _object(self.state.get("estimate_after"), "estimate_dependency_missing")
        response = _expect(
            self.backend.request(
                "GET",
                f"/api/v1/estimates/{quote(estimate_id, safe='')}/pdf",
                query={"version": int(after.get("version") or 0)},
                headers={"Accept": "application/pdf"},
            ),
            200,
            "estimate_pdf",
        )
        mime = _content_type(response.headers)
        if mime != "application/pdf" or len(response.body) <= 1024 or not _pdf_bytes_valid(response.body):
            raise GateCollectorError("estimate_pdf_bytes_invalid")
        return {
            "http_status": response.status,
            "content_type": mime,
            "magic": "%PDF-",
            "size_bytes": len(response.body),
            "sha256": _sha256(response.body),
        }

    def gate_capability_registry(self) -> dict[str, Any]:
        response = _expect(
            self.backend.request("GET", "/v1/capabilities"), 200, "capability_registry"
        )
        payload = _object(response.json(), "capability_registry_invalid")
        if payload.get("release_id") != self.release_id:
            raise GateCollectorError("capability_registry_release_mismatch")
        try:
            probe_ttl_seconds = int(payload.get("probe_ttl_seconds") or 0)
        except (TypeError, ValueError) as exc:
            raise GateCollectorError("capability_probe_ttl_invalid") from exc
        if probe_ttl_seconds < MIN_PRODUCTION_PROBE_TTL_SECONDS:
            raise GateCollectorError("capability_probe_ttl_too_short")
        capabilities = _list(payload.get("capabilities"), "capability_registry_invalid")
        canonical_statuses = ["available", "degraded", "unavailable"]
        if len(capabilities) < 10:
            raise GateCollectorError("capability_registry_too_small")
        counts = _object(payload.get("counts"), "capability_counts_missing")
        if set(counts) != set(canonical_statuses):
            raise GateCollectorError("capability_status_contract_invalid")
        for raw in capabilities:
            item = _object(raw, "capability_item_invalid")
            if item.get("status") not in canonical_statuses:
                raise GateCollectorError("capability_status_invalid")
            if item.get("status") == "available":
                routes = _list(item.get("routes"), "capability_routes_invalid")
                selected = item.get("selected_route_id")
                live = [
                    route
                    for route in routes
                    if isinstance(route, dict)
                    and route.get("id") == selected
                    and isinstance(route.get("probe"), dict)
                    and route["probe"].get("state") == "succeeded"
                    and route["probe"].get("fresh") is True
                ]
                if (
                    item.get("invocable") is not True
                    or item.get("source") != {"type": "live_invocation"}
                    or not item.get("verified_at")
                    or not live
                ):
                    raise GateCollectorError("capability_live_probe_binding_invalid")
            elif item.get("invocable") is not False:
                raise GateCollectorError("capability_unproved_invocable")
        self.state["capability_registry"] = payload
        return {
            "http_status": response.status,
            "source": "backend_runtime_registry",
            "release_id": self.release_id,
            "probe_ttl_seconds": probe_ttl_seconds,
            "release_bound": True,
            "statuses": canonical_statuses,
            "invocable_requires_live_probe": True,
            "capability_count": len(capabilities),
        }

    def _project_message(
        self,
        project_id: str,
        *,
        role: str,
        content: str,
        response_id: str | None = None,
    ) -> dict[str, Any]:
        metadata = {"response_id": response_id} if response_id else {}
        response = _expect(
            self.backend.request(
                "POST",
                f"/api/v1/projects/{quote(project_id, safe='')}/messages",
                json_body={
                    "role": role,
                    "content": content,
                    "status": "completed",
                    "metadata": metadata,
                    "client_message_id": f"p7-{secrets.token_hex(8)}",
                },
                headers={"Idempotency-Key": f"p7-message-{secrets.token_hex(8)}"},
            ),
            {200, 201},
            "project_message",
        )
        return _object(response.json(), "project_message_invalid")

    def _wait_response(self, response_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while True:
            response = _expect(
                self.backend.request(
                    "GET",
                    f"/v1/responses/{quote(response_id, safe='')}",
                    headers=self.api_headers,
                ),
                200,
                "response_poll",
            )
            payload = _object(response.json(), "response_poll_invalid")
            if payload.get("status") in {"completed", "failed", "cancelled"}:
                return payload
            if time.monotonic() >= deadline:
                raise GateCollectorError("response_poll_timeout")
            time.sleep(0.25)

    def gate_chat_durable_stream(self) -> dict[str, Any]:
        project_response = _expect(
            self.backend.request(
                "POST",
                "/api/v1/projects",
                json_body={"title": f"P7 durable stream {self.run_id}"},
                headers={"Idempotency-Key": f"p7-project-{secrets.token_hex(8)}"},
            ),
            {200, 201},
            "project_create",
        )
        project = _object(project_response.json(), "project_create_invalid")
        project_id = _required_text(project.get("id"), "project_id_missing")
        self.state["project_id"] = project_id
        prompt = "Ответь одной короткой фразой: проверка долговечного потока Kolibri P7."
        self._project_message(project_id, role="user", content=prompt)
        stream = _expect(
            self.backend.request(
                "POST",
                "/v1/responses",
                json_body={"model": "kolibri", "input": prompt, "stream": True},
                headers={**self.api_headers, "Idempotency-Key": f"p7-stream-{secrets.token_hex(8)}"},
            ),
            {200, 201},
            "response_stream",
        )
        events = _sse_events(stream)
        created_events = [payload for name, payload in events if name == "response.created" and isinstance(payload, dict)]
        if not created_events:
            raise GateCollectorError("response_created_event_missing")
        created_response = _object(created_events[0].get("response"), "response_created_payload_invalid")
        response_id = _required_text(created_response.get("id"), "response_id_missing")
        deltas = [
            str(payload.get("delta") or "")
            for name, payload in events
            if name == "response.output_text.delta" and isinstance(payload, dict) and payload.get("delta")
        ]
        terminal = [payload for name, payload in events if name == "response.completed" and isinstance(payload, dict)]
        if not deltas or not terminal:
            raise GateCollectorError("response_stream_terminal_or_delta_missing")
        terminal_response = _object(terminal[-1].get("response"), "response_terminal_invalid")
        assistant_text = _required_text(terminal_response.get("output_text") or "".join(deltas), "response_text_missing")
        self._project_message(
            project_id, role="assistant", content=assistant_text, response_id=response_id
        )

        background = _expect(
            self.backend.request(
                "POST",
                "/v1/responses",
                json_body={
                    "model": "kolibri",
                    "input": "Подготовь глубокий фоновый P7 ответ, ожидая отмены.",
                    "background": True,
                    "policy": {"mode": "deep", "reasoning_effort": "high", "tool_choice": "auto", "background": True},
                },
                headers={**self.api_headers, "Idempotency-Key": f"p7-cancel-{secrets.token_hex(8)}"},
            ),
            200,
            "background_response",
        )
        background_payload = _object(background.json(), "background_response_invalid")
        cancel_id = _required_text(background_payload.get("id"), "background_response_id_missing")
        if background_payload.get("status") not in {"queued", "in_progress"}:
            raise GateCollectorError("background_response_not_cancellable")
        cancelled = _expect(
            self.backend.request(
                "POST",
                f"/v1/responses/{quote(cancel_id, safe='')}/cancel",
                json_body={},
                headers=self.api_headers,
            ),
            200,
            "response_cancel",
        )
        cancelled_payload = _object(cancelled.json(), "response_cancel_invalid")
        if cancelled_payload.get("status") != "cancelled":
            raise GateCollectorError("response_cancel_not_terminal")
        retried = _expect(
            self.backend.request(
                "POST",
                f"/v1/responses/{quote(cancel_id, safe='')}/retry",
                json_body={},
                headers={**self.api_headers, "Idempotency-Key": f"p7-retry-{secrets.token_hex(8)}"},
            ),
            200,
            "response_retry",
        )
        retry_payload = _object(retried.json(), "response_retry_invalid")
        if retry_payload.get("status") not in {"completed", "failed", "cancelled"}:
            retry_payload = self._wait_response(_required_text(retry_payload.get("id"), "retry_id_missing"))
        if retry_payload.get("status") != "completed":
            raise GateCollectorError("response_retry_not_completed")
        retry_id = _required_text(retry_payload.get("id"), "retry_id_missing")
        self._project_message(
            project_id,
            role="assistant",
            content=_required_text(retry_payload.get("output_text"), "retry_text_missing"),
            response_id=retry_id,
        )

        history = _expect(
            self.backend.request("GET", f"/api/v1/projects/{quote(project_id, safe='')}/messages"),
            200,
            "project_history_reload",
        )
        messages = _list(_object(history.json(), "project_history_invalid").get("items"), "project_history_invalid")
        assistant_ids = [
            str(message.get("metadata", {}).get("response_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "assistant"
        ]
        duplicate = any(assistant_ids.count(item) > 1 for item in set(assistant_ids) if item)
        persisted = response_id in assistant_ids and retry_id in assistant_ids
        if duplicate or not persisted:
            raise GateCollectorError("project_history_response_binding_invalid")
        return {
            "create_http_status": stream.status,
            "text_delta_count": len(deltas),
            "terminal_state": "completed",
            "history_persisted_after_reload": True,
            "cancel_terminal_state": "cancelled",
            "retry_terminal_state": "completed",
            "duplicate_assistant_detected": False,
            "project_id": project_id,
            "response_id": response_id,
        }

    def gate_web_search_sources(self) -> dict[str, Any]:
        project_id = _required_text(self.state.get("project_id"), "project_dependency_missing")
        response = _expect(
            self.backend.request(
                "POST",
                "/api/v1/tools/invoke",
                json_body={
                    "tool": "web.search",
                    "arguments": {
                        "query": "официальные актуальные цены строительных материалов Татарстан",
                        "limit": 5,
                    },
                },
            ),
            200,
            "web_search",
        )
        payload = _object(response.json(), "web_search_invalid")
        result = _object(payload.get("result"), "web_search_result_invalid")
        raw_sources = _list(result.get("sources"), "web_search_sources_missing")
        observed_at = _utc_now()
        sources: list[dict[str, str]] = []
        for raw in raw_sources:
            source = _object(raw, "web_search_source_invalid")
            url = _required_text(source.get("url"), "web_search_source_url_missing")
            if urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
                raise GateCollectorError("web_search_source_not_https")
            sources.append(
                {
                    "url": url,
                    "title": _required_text(source.get("title"), "web_search_source_title_missing"),
                    "retrieved_at": observed_at,
                }
            )
        if not sources:
            raise GateCollectorError("web_search_sources_missing")
        marker = f"P7-WEB-{self.run_id}"
        self._project_message(
            project_id,
            role="tool",
            content=f"{marker}\n{json.dumps(sources, ensure_ascii=False, sort_keys=True)}",
            response_id=f"web-{self.run_id}",
        )
        history = _expect(
            self.backend.request("GET", f"/api/v1/projects/{quote(project_id, safe='')}/messages"),
            200,
            "web_search_reload",
        )
        history_text = "\n".join(
            str(item.get("content") or "")
            for item in _list(_object(history.json(), "web_search_reload_invalid").get("items"), "web_search_reload_invalid")
            if isinstance(item, dict)
        )
        persisted = marker in history_text and all(source["url"] in history_text for source in sources)
        if not persisted:
            raise GateCollectorError("web_search_not_persisted")
        return {
            "http_status": response.status,
            "provider_invoked": True,
            "persisted_after_reload": True,
            "sources": sources,
        }

    def _download_reopen(self, artifact: Mapping[str, Any]) -> tuple[HttpResponse, str, HttpResponse, str]:
        expected = _required_text(artifact.get("sha256"), "artifact_sha_missing")
        if not SHA256_RE.fullmatch(expected):
            raise GateCollectorError("artifact_sha_invalid")
        download_url = _required_text(artifact.get("download_url"), "artifact_download_url_missing")
        content_url = _required_text(artifact.get("url"), "artifact_url_missing")
        reopen_url = _required_text(artifact.get("reopen_url"), "artifact_reopen_url_missing")
        download = _expect(self.backend.request("GET", download_url), 200, "artifact_download")
        reopened_bytes = _expect(self.backend.request("GET", content_url), 200, "artifact_reopen_bytes")
        reopen = _expect(self.backend.request("GET", reopen_url), 200, "artifact_reopen_metadata")
        reopen_payload = _object(reopen.json(), "artifact_reopen_metadata_invalid")
        integrity = _object(reopen_payload.get("integrity"), "artifact_reopen_integrity_missing")
        download_sha = _sha256(download.body)
        reopen_sha = _sha256(reopened_bytes.body)
        if {download_sha, reopen_sha, str(integrity.get("digest") or "")} != {expected}:
            raise GateCollectorError("artifact_integrity_mismatch")
        return download, download_sha, reopened_bytes, reopen_sha

    def gate_file_lifecycle(self) -> dict[str, Any]:
        marker = f"kolibri-p7-file-{self.run_id}"
        content = (f"{marker}\nФайл для реального поиска и повторного открытия.\n" * 8).encode("utf-8")
        upload = _expect(
            self.backend.multipart(
                "/api/v1/files",
                field_name="file",
                filename=f"{marker}.txt",
                content_type="text/plain",
                content=content,
            ),
            201,
            "file_upload",
        )
        artifact = _object(_object(upload.json(), "file_upload_invalid").get("artifact"), "file_upload_artifact_missing")
        upload_sha = _required_text(artifact.get("sha256"), "file_upload_sha_missing")
        if upload_sha != _sha256(content):
            raise GateCollectorError("file_upload_sha_mismatch")
        artifact_id = _required_text(artifact.get("id"), "file_artifact_id_missing")
        analysis = _expect(
            self.backend.request("POST", f"/api/v1/files/{quote(artifact_id, safe='')}/analyze", json_body={}),
            201,
            "file_analysis",
        )
        analysis_artifact = _object(
            _object(analysis.json(), "file_analysis_invalid").get("artifact"),
            "file_analysis_artifact_missing",
        )
        analysis_sha = _required_text(analysis_artifact.get("sha256"), "file_analysis_sha_missing")
        if not SHA256_RE.fullmatch(analysis_sha):
            raise GateCollectorError("file_analysis_sha_invalid")
        search = _expect(
            self.backend.request("GET", "/api/v1/files/search", query={"q": marker, "limit": 20}),
            200,
            "file_search",
        )
        items = _list(_object(search.json(), "file_search_invalid").get("items"), "file_search_invalid")
        found = any(
            isinstance(item, dict)
            and isinstance(item.get("artifact"), dict)
            and item["artifact"].get("id") == artifact_id
            and marker.casefold() in str(item.get("snippet") or "").casefold()
            for item in items
        )
        if not found:
            raise GateCollectorError("file_search_content_missing")
        download, download_sha, reopen, reopen_sha = self._download_reopen(artifact)
        return {
            "upload_http_status": upload.status,
            "upload_sha256": upload_sha,
            "analysis_http_status": analysis.status,
            "analysis_sha256": analysis_sha,
            "search_http_status": search.status,
            "search_found_uploaded_content": True,
            "reopen_http_status": reopen.status,
            "download_http_status": download.status,
            "reopen_sha256": reopen_sha,
            "download_sha256": download_sha,
        }

    def _invoke_tool(self, tool: str, arguments: Mapping[str, Any]) -> tuple[HttpResponse, dict[str, Any]]:
        response = _expect(
            self.backend.request(
                "POST",
                "/api/v1/tools/invoke",
                json_body={"tool": tool, "arguments": dict(arguments)},
            ),
            200,
            f"tool_{tool}",
        )
        payload = _object(response.json(), "tool_response_invalid")
        if payload.get("status") != "completed" or payload.get("tool") != tool:
            raise GateCollectorError("tool_terminal_contract_invalid")
        return response, payload

    def gate_document_artifacts(self) -> dict[str, Any]:
        formats: dict[str, Any] = {}
        for format_id, (mime, magic, arguments) in DOCUMENT_FORMATS.items():
            response, payload = self._invoke_tool(f"document.{format_id}", arguments)
            artifact = _artifact_from_tool(payload)
            download, download_sha, reopened, reopen_sha = self._download_reopen(artifact)
            actual_mime = _content_type(download.headers)
            container_valid = (
                _pdf_bytes_valid(download.body)
                if format_id == "pdf"
                else _ooxml_bytes_valid(download.body, format_id)
            )
            if (
                actual_mime != mime
                or not download.body.startswith(magic)
                or len(download.body) <= 256
                or not container_valid
                or int(artifact.get("size_bytes") or 0) != len(download.body)
                or artifact.get("mime_type") != mime
                or artifact.get("sha256") != download_sha
            ):
                raise GateCollectorError(f"document_{format_id}_bytes_invalid")
            formats[format_id] = {
                "http_status": response.status,
                "mime_type": mime,
                "magic": "%PDF-" if format_id == "pdf" else "PK",
                "size_bytes": len(download.body),
                "sha256": download_sha,
                "download_sha256": download_sha,
                "reopen_sha256": reopen_sha,
            }
        return {"formats": formats}

    def gate_image_lifecycle(self) -> dict[str, Any]:
        lifecycle = _object(
            self.browser.get("image_lifecycle"), "browser_image_lifecycle_missing"
        )
        generate_status = int(lifecycle.get("generate_http_status") or 0)
        edit_status = int(lifecycle.get("edit_http_status") or 0)
        generated_id = str(lifecycle.get("generated_artifact_id") or "")
        edited_id = str(lifecycle.get("edited_artifact_id") or "")
        generated_sha = str(lifecycle.get("generated_sha256") or "")
        edited_sha = str(lifecycle.get("edited_sha256") or "")
        if (
            generate_status not in {200, 201}
            or edit_status not in {200, 201}
            or lifecycle.get("provider_tool_invoked") is not True
            or lifecycle.get("rendered_in_shell") is not True
            or not SAFE_ID_RE.fullmatch(generated_id)
            or not SAFE_ID_RE.fullmatch(edited_id)
            or generated_id == edited_id
            or not SHA256_RE.fullmatch(generated_sha)
            or not SHA256_RE.fullmatch(edited_sha)
            or generated_sha == edited_sha
        ):
            raise GateCollectorError("browser_image_lifecycle_invalid")

        def image_path(field: str, artifact_id: str) -> str:
            path = str(lifecycle.get(field) or "")
            parsed = urlsplit(path)
            absolute_same_origin = (
                bool(parsed.scheme or parsed.netloc)
                and (parsed.scheme, parsed.netloc)
                == (urlsplit(self.backend_origin).scheme, urlsplit(self.backend_origin).netloc)
            )
            relative_same_origin = path.startswith("/") and not parsed.scheme and not parsed.netloc
            if (
                not (absolute_same_origin or relative_same_origin)
                or parsed.fragment
                or artifact_id not in parsed.path
            ):
                raise GateCollectorError("browser_image_artifact_url_invalid")
            return path

        generated_url = image_path("generated_url", generated_id)
        generated_download_url = image_path("generated_download_url", generated_id)
        edited_url = image_path("edited_url", edited_id)
        edited_download_url = image_path("edited_download_url", edited_id)

        generated_reopen = _expect(
            self.backend.request("GET", generated_url), 200, "generated_image_reopen"
        )
        generated_download = _expect(
            self.backend.request("GET", generated_download_url),
            200,
            "generated_image_download",
        )
        edited_reopen = _expect(
            self.backend.request("GET", edited_url), 200, "edited_image_reopen"
        )
        edited_download = _expect(
            self.backend.request("GET", edited_download_url),
            200,
            "edited_image_download",
        )
        generated_mime = _content_type(generated_download.headers)
        edited_mime = _content_type(edited_download.headers)
        generated_dimensions = image_dimensions(generated_download.body, generated_mime)
        width, height = image_dimensions(edited_download.body, edited_mime)
        if (
            generated_mime not in {"image/png", "image/jpeg", "image/webp"}
            or edited_mime not in {"image/png", "image/jpeg", "image/webp"}
            or _content_type(generated_reopen.headers) != generated_mime
            or _content_type(edited_reopen.headers) != edited_mime
            or _sha256(generated_download.body) != generated_sha
            or _sha256(generated_reopen.body) != generated_sha
            or _sha256(edited_download.body) != edited_sha
            or _sha256(edited_reopen.body) != edited_sha
            or min(generated_dimensions) < 64
            or width < 64
            or height < 64
        ):
            raise GateCollectorError("browser_image_artifact_bytes_invalid")
        self.state["edited_image_sha256"] = edited_sha
        return {
            "generate_http_status": generate_status,
            "edit_http_status": edit_status,
            "provider_tool_invoked": True,
            "mime_type": edited_mime,
            "width": width,
            "height": height,
            "generated_sha256": generated_sha,
            "edited_sha256": edited_sha,
            "download_sha256": edited_sha,
            "reopen_sha256": edited_sha,
            "rendered_in_shell": True,
        }

    def gate_site_app_lifecycle(self) -> dict[str, Any]:
        artifacts: dict[str, Any] = {}
        for kind in ("site", "app"):
            response, payload = self._invoke_tool(
                f"{kind}.create",
                {"prompt": f"Создай минимальный рабочий {kind} P7 с доступным интерфейсом и заголовком Kolibri proof."},
            )
            result = _object(payload.get("result"), "project_tool_result_invalid")
            artifact = _object(result.get("artifact"), "project_artifact_missing")
            download, download_sha, reopened, reopen_sha = self._download_reopen(artifact)
            preview_url = _required_text(result.get("preview_url"), "project_preview_url_missing")
            preview = _expect(
                self.backend.request("GET", preview_url, headers={"Accept": "text/html"}),
                200,
                "project_preview",
            )
            csp = str(preview.headers.get("content-security-policy") or "")
            sandbox = (
                "sandbox allow-scripts" in csp
                and "connect-src 'none'" in csp
                and preview.headers.get("x-content-type-options") == "nosniff"
                and bool(preview.headers.get("permissions-policy"))
            )
            if (
                _content_type(download.headers) != "application/zip"
                or artifact.get("mime_type") != "application/zip"
                or not download.body.startswith(b"PK")
                or len(download.body) <= 256
                or not _project_archive_valid(download.body)
                or artifact.get("sha256") != download_sha
                or _content_type(preview.headers) != "text/html"
                or b"<html" not in preview.body.lower()
                or not sandbox
            ):
                raise GateCollectorError(f"{kind}_project_lifecycle_invalid")
            artifacts[kind] = {
                "http_status": response.status,
                "mime_type": "application/zip",
                "magic": "PK",
                "size_bytes": len(download.body),
                "sha256": download_sha,
                "preview_http_status": preview.status,
                "preview_content_type": "text/html",
                "sandbox_headers_verified": True,
                "download_sha256": download_sha,
                "reopen_sha256": reopen_sha,
            }
        return {"artifacts": artifacts}

    @staticmethod
    def _structured_schema() -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "minLength": 1, "maxLength": 120},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
            },
            "required": ["answer", "score"],
            "additionalProperties": False,
        }

    @classmethod
    def _valid_structured_value(cls, value: Any) -> bool:
        return (
            isinstance(value, dict)
            and set(value) == {"answer", "score"}
            and isinstance(value["answer"], str)
            and 1 <= len(value["answer"]) <= 120
            and isinstance(value["score"], int)
            and not isinstance(value["score"], bool)
            and 0 <= value["score"] <= 10
        )

    def gate_structured_apis(self) -> dict[str, Any]:
        schema = self._structured_schema()
        responses = _expect(
            self.backend.request(
                "POST",
                "/v1/responses",
                json_body={
                    "model": "kolibri",
                    "input": "Верни JSON: answer='P7', score=10.",
                    "stream": True,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "p7_result",
                            "schema": schema,
                            "strict": True,
                        }
                    },
                },
                headers={**self.api_headers, "Idempotency-Key": f"p7-structured-{secrets.token_hex(8)}"},
            ),
            200,
            "structured_responses",
        )
        response_events = _sse_events(responses)
        response_deltas = [
            str(payload.get("delta") or "")
            for name, payload in response_events
            if name == "response.output_text.delta" and isinstance(payload, dict)
        ]
        response_terminal = any(name == "response.completed" for name, _payload in response_events)
        try:
            response_value = json.loads("".join(response_deltas))
        except json.JSONDecodeError as exc:
            raise GateCollectorError("responses_structured_json_invalid") from exc
        responses_valid = response_terminal and self._valid_structured_value(response_value)

        chat = _expect(
            self.backend.request(
                "POST",
                "/v1/chat/completions",
                json_body={
                    "model": "kolibri",
                    "messages": [{"role": "user", "content": "Верни JSON: answer='P7', score=10."}],
                    "stream": True,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "p7_result",
                            "schema": schema,
                            "strict": True,
                        },
                    },
                },
                headers={**self.api_headers, "Idempotency-Key": f"p7-chat-{secrets.token_hex(8)}"},
            ),
            200,
            "structured_chat",
        )
        chat_events = _sse_events(chat)
        chat_text: list[str] = []
        chat_model_ok = True
        done = False
        for _name, payload in chat_events:
            if payload == "[DONE]":
                done = True
                continue
            if not isinstance(payload, dict):
                continue
            chat_model_ok = chat_model_ok and payload.get("model") == "kolibri"
            choices = payload.get("choices")
            if isinstance(choices, list) and choices and isinstance(choices[0], dict):
                delta = choices[0].get("delta")
                if isinstance(delta, dict) and delta.get("content"):
                    chat_text.append(str(delta["content"]))
        try:
            chat_value = json.loads("".join(chat_text))
        except json.JSONDecodeError as exc:
            raise GateCollectorError("chat_structured_json_invalid") from exc
        chat_valid = done and chat_model_ok and self._valid_structured_value(chat_value)
        if not responses_valid or not chat_valid:
            raise GateCollectorError("structured_api_contract_invalid")
        return {
            "responses_http_status": responses.status,
            "responses_stream_valid": True,
            "chat_http_status": chat.status,
            "chat_stream_valid": True,
            "structured_json_schema_valid": True,
            "model": "kolibri",
        }

    def gate_shell_desktop_mobile(self) -> dict[str, Any]:
        viewports = _object(self.browser.get("viewports"), "browser_viewports_missing")
        if set(viewports) != REQUIRED_BROWSER_VIEWPORTS:
            raise GateCollectorError("browser_viewport_matrix_invalid")
        normalized: dict[str, Any] = {}
        for viewport_id, raw in viewports.items():
            value = _object(raw, "browser_viewport_invalid")
            required = (
                value.get("status") == "passed"
                and int(value.get("console_errors") or 0) == 0
                and int(value.get("unexplained_failed_requests") or 0) == 0
                and value.get("visible_controls_actionable") is True
                and value.get("horizontal_overflow") is False
            )
            if not required:
                raise GateCollectorError(f"browser_{viewport_id}_failed")
            normalized[viewport_id] = {
                "status": "passed",
                "console_errors": 0,
                "unexplained_failed_requests": 0,
                "visible_controls_actionable": True,
                "horizontal_overflow": False,
            }
        if self.browser.get("reload_reopens_all_artifact_types") is not True:
            raise GateCollectorError("browser_reload_artifacts_failed")
        return {
            "viewports": normalized,
            "reload_reopens_all_artifact_types": True,
            "browser_evidence_sha256": self.browser_sha256,
        }

    def gate_optional_capability_gates(self) -> dict[str, Any]:
        registry = _object(self.state.get("capability_registry"), "capability_registry_dependency_missing")
        degraded = [
            item
            for item in _list(registry.get("capabilities"), "capability_registry_invalid")
            if isinstance(item, dict) and item.get("status") == "degraded"
        ]
        technical = all(
            isinstance(item.get("reason"), dict)
            and bool(str(item["reason"].get("code") or "").strip())
            and bool(str(item["reason"].get("message") or "").strip())
            for item in degraded
        )
        owner_gate_checks: list[bool] = []
        for path in ("/api/v1/integrations/connect", "/api/v1/automations/run"):
            unauthenticated = self.backend.request("POST", path, json_body={})
            authenticated = self.backend.request(
                "POST", path, json_body={}, headers=self.owner_headers
            )
            owner_gate_checks.append(
                unauthenticated.status in {401, 403}
                and authenticated.status in {501, 503}
            )
        unavailable_hidden = self.browser.get("unavailable_capabilities_hidden") is True
        placeholder = self.browser.get("placeholder_or_fake_success_detected") is True
        if not technical or not all(owner_gate_checks) or not unavailable_hidden or placeholder:
            raise GateCollectorError("optional_capability_policy_failed")
        return {
            "unavailable_capabilities_hidden": True,
            "degraded_reasons_are_technical": True,
            "external_integrations_owner_gated": True,
            "placeholder_or_fake_success_detected": False,
        }

    def collect(self) -> tuple[dict[str, Any], bool]:
        results: dict[str, dict[str, Any]] = {}
        try:
            self._bootstrap()
        except GateCollectorError as exc:
            results = {
                gate: {"status": "failed", "error_code": exc.code}
                for gate in EXPECTED_GATES
            }
        else:
            # API-key proof runs first because later public /v1 checks use a
            # short-lived key created through the same real owner-gated API.
            results["developer_api_keys"] = self._gate(self.gate_developer_api_keys)
            ordered: Sequence[tuple[str, Callable[[], dict[str, Any]]]] = (
                ("release_identity", self.gate_release_identity),
                ("estimate_create_regional", self.gate_estimate_create_regional),
                ("estimate_recalculate", self.gate_estimate_recalculate),
                ("estimate_revisions", self.gate_estimate_revisions),
                ("estimate_pdf", self.gate_estimate_pdf),
                ("capability_registry", self.gate_capability_registry),
                ("chat_durable_stream", self.gate_chat_durable_stream),
                ("web_search_sources", self.gate_web_search_sources),
                ("file_lifecycle", self.gate_file_lifecycle),
                ("document_artifacts", self.gate_document_artifacts),
                ("image_lifecycle", self.gate_image_lifecycle),
                ("site_app_lifecycle", self.gate_site_app_lifecycle),
                ("structured_apis", self.gate_structured_apis),
                ("shell_desktop_mobile", self.gate_shell_desktop_mobile),
                ("optional_capability_gates", self.gate_optional_capability_gates),
            )
            for gate_id, method in ordered:
                results[gate_id] = self._gate(method)
        finally:
            operational_key_id = self.state.get("api_key_id")
            if isinstance(operational_key_id, str) and operational_key_id:
                try:
                    cleanup_ok = self._revoke_api_key(operational_key_id).status == 200
                except GateCollectorError:
                    cleanup_ok = False
                if not cleanup_ok:
                    result = results.setdefault(
                        "developer_api_keys",
                        {"status": "failed", "error_code": "api_key_cleanup_failed"},
                    )
                    result.update({"status": "failed", "error_code": "api_key_cleanup_failed"})
            self.state.pop("api_key", None)

        results = {gate: results.get(gate, {"status": "failed", "error_code": "gate_not_run"}) for gate in EXPECTED_GATES}
        evidence = {
            "schema_version": SCHEMA_VERSION,
            "release_id": self.release_id,
            "manifest_sha256": self.manifest_sha256,
            "collector": {
                "identity": COLLECTOR_IDENTITY,
                "implementation": "kolibri-p7-gate-collector",
                "version": COLLECTOR_VERSION,
                "run_id": self.run_id,
                "target": {
                    "release_id": self.release_id,
                    "manifest_sha256": self.manifest_sha256,
                    "backend_origin": self.backend_origin,
                    "frontend_origin": self.frontend_origin,
                },
            },
            "results": results,
        }
        passed = all(result.get("status") == "passed" for result in results.values())
        return evidence, passed


def write_canonical_evidence(path: Path, evidence: Mapping[str, Any], *, overwrite: bool = False) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        raise GateCollectorError("output_exists")
    payload = canonical_json(evidence) + b"\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.chmod(temporary_name, 0o640)
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect unsigned Kolibri P7 functional-gate evidence over real HTTP."
    )
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--backend-origin", required=True)
    parser.add_argument("--frontend-origin", required=True)
    parser.add_argument("--browser-evidence", type=Path, required=True)
    parser.add_argument("--owner-token-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        collector = P7GateCollector(
            release_id=args.release_id,
            manifest_sha256=args.manifest_sha256,
            backend_origin=args.backend_origin,
            frontend_origin=args.frontend_origin,
            browser_evidence_path=args.browser_evidence,
            owner_token_file=args.owner_token_file,
            timeout=args.timeout,
        )
        evidence, passed = collector.collect()
        write_canonical_evidence(args.output, evidence, overwrite=args.overwrite)
    except GateCollectorError as exc:
        print(json.dumps({"status": "failed", "error_code": exc.code}, sort_keys=True), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "passed" if passed else "failed",
                "output": str(args.output.expanduser().resolve()),
                "run_id": evidence["collector"]["run_id"],
                "evidence_sha256": _sha256(canonical_json(evidence) + b"\n"),
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
