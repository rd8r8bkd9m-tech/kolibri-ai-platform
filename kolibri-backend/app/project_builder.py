"""Provider-backed, immutable site/application project bundles.

The provider is allowed to propose *only* a bounded JSON file tree.  Kolibri
validates that tree before any bytes enter the artifact store, writes a
deterministic ZIP, and exposes its ``index.html`` through the separately
sandboxed preview route in :mod:`app.tool_router`.

There is deliberately no local/template fallback here.  If every configured
provider fails, returns prose, or proposes an unsafe path, no artifact is
created and the capability probe records a failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import hashlib
import json
from pathlib import PurePosixPath
import re
import unicodedata
import zipfile
from typing import Any


MAX_PROJECT_FILES = 96
MAX_PROJECT_FILE_BYTES = 512 * 1024
MAX_PROJECT_BYTES = 5 * 1024 * 1024
MAX_PROJECT_PROMPT = 20_000
MAX_PROJECT_TITLE = 160
MAX_PROJECT_PATH = 240

_CAPABILITIES = {"site.create", "app.create"}
_TEXT_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".svg",
    ".ts",
    ".tsx",
    ".txt",
    ".webmanifest",
    ".xml",
}
_RESERVED_PATHS = {"kolibri-project.json"}


class ProjectBuildError(RuntimeError):
    """Safe project-build failure with a stable public reason code."""

    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class ProjectFile:
    path: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ProjectPayload:
    title: str
    files: tuple[ProjectFile, ...]


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProjectBuildError("provider_project_json_invalid") from exc


def _safe_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_PROJECT_PATH:
        raise ProjectBuildError("provider_project_path_invalid")
    if value != unicodedata.normalize("NFC", value):
        raise ProjectBuildError("provider_project_path_invalid")
    if "\\" in value or "\x00" in value or value.startswith(("/", "~")):
        raise ProjectBuildError("provider_project_path_invalid")
    path = PurePosixPath(value)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ProjectBuildError("provider_project_path_invalid")
    canonical = path.as_posix()
    if canonical != value or canonical.casefold() in _RESERVED_PATHS:
        raise ProjectBuildError("provider_project_path_invalid")
    suffix = path.suffix.casefold()
    if suffix not in _TEXT_EXTENSIONS:
        raise ProjectBuildError("provider_project_file_type_forbidden")
    return canonical


def parse_project_payload(raw_content: Any) -> ProjectPayload:
    """Parse one exact JSON object; Markdown fences and surrounding prose fail."""

    if not isinstance(raw_content, str):
        raise ProjectBuildError("provider_project_output_not_text")
    stripped = raw_content.strip()
    if not stripped or not stripped.startswith("{") or not stripped.endswith("}"):
        raise ProjectBuildError("provider_project_output_not_json")
    try:
        raw = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProjectBuildError("provider_project_output_not_json") from exc
    if not isinstance(raw, dict) or set(raw) != {"title", "files"}:
        raise ProjectBuildError("provider_project_schema_invalid")

    title = raw.get("title")
    if not isinstance(title, str):
        raise ProjectBuildError("provider_project_title_invalid")
    title = " ".join(title.split())
    if not title or len(title) > MAX_PROJECT_TITLE:
        raise ProjectBuildError("provider_project_title_invalid")

    raw_files = raw.get("files")
    if (
        not isinstance(raw_files, list)
        or not raw_files
        or len(raw_files) > MAX_PROJECT_FILES
    ):
        raise ProjectBuildError("provider_project_files_invalid")

    files: list[ProjectFile] = []
    seen: set[str] = set()
    total_bytes = 0
    for raw_file in raw_files:
        if not isinstance(raw_file, dict) or set(raw_file) != {"path", "content"}:
            raise ProjectBuildError("provider_project_file_schema_invalid")
        path = _safe_path(raw_file.get("path"))
        path_key = path.casefold()
        if path_key in seen:
            raise ProjectBuildError("provider_project_path_duplicate")
        seen.add(path_key)
        content = raw_file.get("content")
        if not isinstance(content, str):
            raise ProjectBuildError("provider_project_content_invalid")
        encoded = content.encode("utf-8")
        if not encoded or len(encoded) > MAX_PROJECT_FILE_BYTES:
            raise ProjectBuildError("provider_project_content_invalid")
        total_bytes += len(encoded)
        if total_bytes > MAX_PROJECT_BYTES:
            raise ProjectBuildError("provider_project_too_large")
        files.append(ProjectFile(path=path, content=encoded))

    if "index.html" not in {item.path for item in files}:
        raise ProjectBuildError("provider_project_index_missing")
    files.sort(key=lambda item: item.path)
    return ProjectPayload(title=title, files=tuple(files))


def deterministic_project_zip(payload: ProjectPayload, capability_id: str) -> bytes:
    if capability_id not in _CAPABILITIES:
        raise ValueError("unsupported project capability")
    manifest = {
        "schema_version": "kolibri.project.v1",
        "capability": capability_id,
        "title": payload.title,
        "entrypoint": "index.html",
        "files": [
            {
                "path": item.path,
                "size_bytes": len(item.content),
                "sha256": hashlib.sha256(item.content).hexdigest(),
            }
            for item in payload.files
        ],
    }
    entries = [("kolibri-project.json", _canonical_json(manifest))]
    entries.extend((item.path, item.content) for item in payload.files)

    output = BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for path, content in entries:
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.flag_bits = 0x800
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    data = output.getvalue()
    if not data.startswith(b"PK\x03\x04"):
        raise ProjectBuildError("project_zip_generation_failed")
    return data


def safe_project_archive_path(value: str) -> str:
    """Validate a preview asset path with the same policy as provider output."""

    return _safe_path(value)


def read_project_archive_file(bundle: bytes, path: str) -> bytes:
    safe_path = safe_project_archive_path(path)
    try:
        with zipfile.ZipFile(BytesIO(bundle)) as archive:
            info = archive.getinfo(safe_path)
            if info.is_dir() or info.file_size <= 0 or info.file_size > MAX_PROJECT_FILE_BYTES:
                raise ProjectBuildError("preview_asset_invalid")
            data = archive.read(info)
    except (KeyError, zipfile.BadZipFile) as exc:
        raise ProjectBuildError("preview_asset_not_found") from exc
    if len(data) != info.file_size:
        raise ProjectBuildError("preview_asset_integrity_failed")
    return data


def _project_system_prompt(capability_id: str) -> str:
    kind = "статического сайта" if capability_id == "site.create" else "браузерного приложения"
    extensions = ", ".join(sorted(_TEXT_EXTENSIONS))
    return (
        f"Создай полный файл-проект {kind}. Верни ровно один JSON-объект без Markdown, "
        "пояснений и code fences. Схема строго такая: "
        '{"title":"Короткое название","files":[{"path":"index.html","content":"..."}]}. '
        f"Разрешены только UTF-8 текстовые файлы с расширениями: {extensions}. "
        "Обязателен index.html. Пути только относительные POSIX, без .., / в начале, "
        "URL, base64/binary и исполняемых серверных файлов. Проект должен быть "
        "самодостаточным и не требовать сборки. Не заявляй о публикации или деплое."
    )


async def invoke_project_provider(capability_id: str, prompt: str) -> dict[str, Any]:
    """Invoke the real configured provider gateway; no local fallback exists."""

    if capability_id not in _CAPABILITIES:
        raise ValueError("unsupported project capability")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROJECT_PROMPT:
        raise ProjectBuildError("project_prompt_invalid")

    # Use the same provider policy/circuit-breakers as chat, but bypass chat's
    # intent rewriting and estimate/image actions: this transport requires one
    # exact project JSON object and validates it below.
    from app import ai_provider

    providers = ai_provider._get_providers_for_task("code")
    if not providers:
        raise ProjectBuildError("project_provider_unavailable", retryable=True)
    messages = [
        {"role": "system", "content": _project_system_prompt(capability_id)},
        {"role": "user", "content": prompt.strip()},
    ]
    for provider in providers:
        try:
            result = await ai_provider._call_ai(provider, messages)
            if not isinstance(result, dict) or not str(result.get("content") or "").strip():
                raise ValueError("provider_returned_empty_content")
            ai_provider._record_provider_success(provider)
            return result
        except Exception as exc:
            ai_provider._record_provider_failure(provider, exc)
            continue
    raise ProjectBuildError("project_provider_routes_exhausted", retryable=True)


def project_bundle_filename(capability_id: str, payload: ProjectPayload) -> str:
    kind = "site" if capability_id == "site.create" else "app"
    identity = hashlib.sha256(
        _canonical_json(
            {
                "title": payload.title,
                "files": [
                    {"path": item.path, "sha256": hashlib.sha256(item.content).hexdigest()}
                    for item in payload.files
                ],
            }
        )
    ).hexdigest()[:12]
    return f"{kind}-{identity}.zip"


__all__ = [
    "ProjectBuildError",
    "ProjectPayload",
    "deterministic_project_zip",
    "invoke_project_provider",
    "parse_project_payload",
    "project_bundle_filename",
    "read_project_archive_file",
    "safe_project_archive_path",
]
