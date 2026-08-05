from fastapi import APIRouter, Request, HTTPException, UploadFile
from fastapi.responses import StreamingResponse, Response, FileResponse
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import asyncio
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
import uuid
from estimate_engine import Estimate, recalculate_estimate
from estimate_service import (
    EstimatePublishValidationError,
    EstimateWorkspaceError,
    EstimateWorkspaceMissing,
    EstimateWorkspaceService,
)
from document_render_workers import RenderValidationError, render_document_request
from document_render_workers import ALLOWED_OUTPUT_FORMATS as _RENDER_OUTPUT_FORMATS
from document_render_workers import RENDER_SANDBOX_DEFAULT
from pydantic import BaseModel, ValidationError
from typing import Literal
from typing import Optional, List, Dict, Any
import zipfile
from pathlib import Path

router = APIRouter()

DB_PATH = Path(os.environ.get("KOLIBRI_DB_PATH", os.path.join(os.environ.get("KOLIBRI_DATA_DIR", "/tmp/kolibri-data"), "kolibri.db")))
APP_SESSION_COOKIE_NAME = os.environ.get("KOLIBRI_SESSION_COOKIE_NAME", "kolibri_session")
APP_SESSION_TTL_SECONDS = max(300, int(os.environ.get("KOLIBRI_SESSION_TTL_SECONDS", "1800")))
APP_SESSION_SECURE_COOKIE = os.environ.get("KOLIBRI_SESSION_SECURE", "1") != "0"
DOCUMENT_PACKAGE_STORAGE = Path(RENDER_SANDBOX_DEFAULT).resolve() / "packages"
_ESTIMATE_WORKSPACE_SERVICE = EstimateWorkspaceService()


class EstimateScenarioRequestItem(BaseModel):
    label: str | None = None
    quantity_multiplier: Decimal = Decimal("1")
    price_multiplier: Decimal = Decimal("1")


class EstimateScenarioRequest(BaseModel):
    scenarios: list[EstimateScenarioRequestItem]


class IntakeAssumptionFeedbackItem(BaseModel):
    id: str
    action: Literal["satisfied", "clarified", "rejected", "modified"] = "satisfied"
    replacement_text: str | None = None
    rationale: str | None = None


class IntakeAssumptionFeedbackRequest(BaseModel):
    feedback: list[IntakeAssumptionFeedbackItem]
    replan: bool = True


def _as_decimal(value: Any, *, field_name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (TypeError, InvalidOperation) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}: {value!r}") from exc
    if not result.is_finite():
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}: must be finite")
    return result


def _sum_scope(payload: dict[str, Any]) -> Decimal:
    scope = Decimal("0")
    for section in payload.get("sections", []):
        for item in section.get("items", []):
            scope += _as_decimal(item.get("quantity", 0), field_name="item quantity")
    return scope


def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_v1_tables():
    conn = _db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS v1_projects (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        title_source TEXT DEFAULT 'default',
        status TEXT DEFAULT 'active',
        version INTEGER DEFAULT 1,
        message_count INTEGER DEFAULT 0,
        metadata TEXT DEFAULT '{}',
        created_at TEXT,
        updated_at TEXT,
        last_message_at TEXT,
        deleted_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_messages (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        version INTEGER DEFAULT 1,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        status TEXT DEFAULT 'completed',
        metadata TEXT DEFAULT '{}',
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (project_id) REFERENCES v1_projects(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS app_sessions (
        id TEXT PRIMARY KEY,
        created_at REAL NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_response_runs (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        model TEXT NOT NULL DEFAULT 'kolibri',
        provider TEXT,
        input TEXT NOT NULL,
        background INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'queued',
        output_text TEXT DEFAULT '',
        error_code TEXT,
        error_message TEXT,
        last_sequence INTEGER NOT NULL DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_response_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        response_id TEXT NOT NULL,
        sequence INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        payload TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (response_id, sequence),
        FOREIGN KEY (response_id) REFERENCES v1_response_runs(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_response_idempotency (
        idempotency_key TEXT PRIMARY KEY,
        response_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (response_id) REFERENCES v1_response_runs(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_realtime_sessions (
        id TEXT PRIMARY KEY,
        response_id TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        metadata TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        FOREIGN KEY (response_id) REFERENCES v1_response_runs(id)
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_v1_response_events_response_id_sequence ON v1_response_events (response_id, sequence)")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_intake_observations (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        modality TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'candidate',
        trust TEXT NOT NULL DEFAULT 'untrusted',
        payload TEXT NOT NULL,
        metadata TEXT NOT NULL DEFAULT '{}',
        provenance TEXT NOT NULL DEFAULT '{}',
        content_sha256 TEXT NOT NULL,
        size_bytes INTEGER DEFAULT 0,
        received_at TEXT,
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (project_id) REFERENCES v1_projects(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_project_briefs (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        is_active INTEGER NOT NULL DEFAULT 1,
        object_type TEXT DEFAULT '',
        region TEXT DEFAULT '',
        purpose TEXT DEFAULT '',
        requirements TEXT DEFAULT '[]',
        constraints TEXT DEFAULT '[]',
        original_intent TEXT DEFAULT '',
        confidence TEXT DEFAULT '0.00',
        metadata TEXT DEFAULT '{}',
        created_at TEXT,
        updated_at TEXT,
        FOREIGN KEY (project_id) REFERENCES v1_projects(id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_document_render_jobs (
        id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL UNIQUE,
        document_id TEXT NOT NULL,
        template_id TEXT NOT NULL,
        template_version TEXT NOT NULL,
        template_locale TEXT NOT NULL,
        template_jurisdiction TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'queued',
        requested_outputs TEXT NOT NULL DEFAULT '[]',
        attempts INTEGER NOT NULL DEFAULT 0,
        warnings TEXT NOT NULL DEFAULT '[]',
        error TEXT,
        tenant_id TEXT,
        project_id TEXT,
        document_data_id TEXT,
        idempotency_key TEXT,
        assets TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_v1_document_render_jobs_idempotency ON v1_document_render_jobs (idempotency_key)""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_v1_document_render_jobs_request_id ON v1_document_render_jobs (request_id)""")
    c.execute("""CREATE TABLE IF NOT EXISTS v1_document_packages (
        id TEXT PRIMARY KEY,
        package_id TEXT NOT NULL UNIQUE,
        request_id TEXT NOT NULL,
        package_status TEXT NOT NULL DEFAULT 'released',
        manifest_hash TEXT NOT NULL,
        idempotency_key TEXT,
        manifest_json TEXT NOT NULL,
        package_path TEXT NOT NULL,
        package_size_bytes INTEGER NOT NULL,
        package_created_outputs TEXT NOT NULL DEFAULT '[]',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_v1_document_packages_request_id ON v1_document_packages (request_id)""")
    c.execute("""CREATE INDEX IF NOT EXISTS idx_v1_document_packages_idempotency ON v1_document_packages (idempotency_key)""")
    conn.commit()
    conn.close()


def _safe_json_loads(value: Any, default: Any = None):
    if not value:
        return default
    if isinstance(value, dict) or isinstance(value, list):
        return value
    if not isinstance(value, str):
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _hash_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _normalize_asset_hash(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.startswith("sha256:"):
        return raw
    return f"sha256:{raw}"


def _normalize_output_formats(formats: Any) -> list[str]:
    if formats is None:
        return []
    if not isinstance(formats, list):
        raise HTTPException(status_code=400, detail="asset formats must be a list")
    normalized: list[str] = []
    for item in formats:
        if not isinstance(item, str):
            raise HTTPException(status_code=400, detail="asset format must be a string")
        value = item.strip().lower()
        if value:
            if value not in _RENDER_OUTPUT_FORMATS:
                raise HTTPException(status_code=400, detail=f"unsupported asset format: {value}")
            normalized.append(value)
    return sorted(set(normalized))


def _serialize_render_job_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    requested_outputs = _safe_json_loads(row["requested_outputs"], default=[])
    assets = _safe_json_loads(row["assets"], default=[])
    warnings = _safe_json_loads(row["warnings"], default=[])
    serialized_assets = []
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            fmt = str(asset.get("format", "")).lower()
            copy_asset = {
                "format": fmt,
                "content_type": asset.get("content_type"),
                "size_bytes": asset.get("size_bytes"),
                "sha256": asset.get("sha256"),
            }
            if fmt:
                copy_asset["download_url"] = f"/api/v1/documents/render/{row['request_id']}/assets/{fmt}"
            serialized_assets.append(copy_asset)
    return {
        "object": "document_render_job",
        "request_id": row["request_id"],
        "document_id": row["document_id"],
        "template_id": row["template_id"],
        "template_version": row["template_version"],
        "status": row["status"],
        "requested_outputs": requested_outputs if isinstance(requested_outputs, list) else [],
        "attempts": row["attempts"] or 0,
        "warnings": warnings if isinstance(warnings, list) else [],
        "error": row["error"],
        "assets": serialized_assets,
        "tenant_id": row["tenant_id"],
        "project_id": row["project_id"],
        "idempotency_key": row["idempotency_key"],
        "template_locale": row["template_locale"],
        "template_jurisdiction": row["template_jurisdiction"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _get_render_job_by_request_id(request_id: str) -> dict[str, Any] | None:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM v1_document_render_jobs WHERE request_id = ? LIMIT 1",
            (request_id,),
        )
        return _serialize_render_job_row(c.fetchone())
    finally:
        conn.close()


def _get_render_job_row_by_request_id(request_id: str) -> sqlite3.Row | None:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM v1_document_render_jobs WHERE request_id = ? LIMIT 1",
            (request_id,),
        )
        return c.fetchone()
    finally:
        conn.close()


def _get_render_job_by_idempotency_key(idempotency_key: str | None) -> dict[str, Any] | None:
    if not idempotency_key:
        return None
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM v1_document_render_jobs WHERE idempotency_key = ? LIMIT 1",
            (idempotency_key,),
        )
        return _serialize_render_job_row(c.fetchone())
    finally:
        conn.close()


def _get_render_job_path(request_id: str, output_format: str) -> Path | None:
    request_id = request_id.strip()
    output_format = output_format.lower().strip()
    if output_format not in _RENDER_OUTPUT_FORMATS:
        return None
    sandbox_root = Path(RENDER_SANDBOX_DEFAULT).resolve()
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT assets FROM v1_document_render_jobs WHERE request_id = ? LIMIT 1",
            (request_id,),
        )
        row = c.fetchone()
        assets = _safe_json_loads(row["assets"], default=[]) if row else []
        if not isinstance(assets, list):
            return None
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            if str(asset.get("format", "")).lower() == output_format:
                path_value = asset.get("path")
                if not isinstance(path_value, str):
                    return None
                candidate = Path(path_value)
                if not candidate.is_absolute():
                    return None
                candidate = candidate.resolve()
                if not str(candidate).startswith(str(sandbox_root)):
                    return None
                if candidate.suffix.lower() != f".{output_format}" or not candidate.exists():
                    return None
                return candidate
        return None
    finally:
        conn.close()


def _upsert_render_job(result: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO v1_document_render_jobs (
                id, request_id, document_id, template_id, template_version, template_locale, template_jurisdiction,
                status, requested_outputs, attempts, warnings, error, tenant_id, project_id, document_data_id,
                idempotency_key, assets, created_at, updated_at
            ) VALUES (
                :request_id, :request_id, :document_id, :template_id, :template_version, :template_locale,
                :template_jurisdiction, :status, :requested_outputs, :attempts, :warnings, :error, :tenant_id,
                :project_id, :document_data_id, :idempotency_key, :assets, :created_at, :created_at
            )
            ON CONFLICT(id) DO UPDATE SET
                request_id = excluded.request_id,
                document_id = excluded.document_id,
                template_id = excluded.template_id,
                template_version = excluded.template_version,
                template_locale = excluded.template_locale,
                template_jurisdiction = excluded.template_jurisdiction,
                status = excluded.status,
                requested_outputs = excluded.requested_outputs,
                attempts = excluded.attempts,
                warnings = excluded.warnings,
                error = excluded.error,
                tenant_id = excluded.tenant_id,
                project_id = excluded.project_id,
                document_data_id = excluded.document_data_id,
                idempotency_key = excluded.idempotency_key,
                assets = excluded.assets,
                updated_at = excluded.updated_at
            """,
            {
                "request_id": result["request_id"],
                "document_id": result["document_id"],
                "template_id": result["template_id"],
                "template_version": result["template_version"],
                "template_locale": result.get("template_locale", ""),
                "template_jurisdiction": result.get("template_jurisdiction", ""),
                "status": result["status"],
                "requested_outputs": json.dumps(result.get("requested_outputs", [])),
                "attempts": int(result.get("attempts", 0)),
                "warnings": json.dumps(result.get("warnings", [])),
                "error": result.get("error"),
                "tenant_id": result.get("tenant_id"),
                "project_id": result.get("project_id"),
                "document_data_id": result.get("document_data_id"),
                "idempotency_key": result.get("idempotency_key"),
                "assets": json.dumps(result.get("assets", [])),
                "created_at": now,
                "updated_at": now,
            },
        )
        conn.commit()
    finally:
        conn.close()


def _serialize_document_package_row(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if not row:
        return None
    package_created_outputs = _safe_json_loads(row["package_created_outputs"], default=[])
    manifest = _safe_json_loads(row["manifest_json"], default={})
    return {
        "object": "document_package",
        "package_id": row["package_id"],
        "request_id": row["request_id"],
        "status": row["package_status"],
        "manifest_hash": row["manifest_hash"],
        "outputs": package_created_outputs if isinstance(package_created_outputs, list) else [],
        "manifest": manifest,
        "package_size_bytes": row["package_size_bytes"],
        "idempotency_key": row["idempotency_key"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "download_url": f"/api/v1/documents/render/{row['request_id']}/packages/{row['package_id']}/download",
    }


def _get_document_package_by_id(package_id: str) -> dict[str, Any] | None:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM v1_document_packages WHERE package_id = ? LIMIT 1",
            (package_id,),
        )
        return _serialize_document_package_row(c.fetchone())
    finally:
        conn.close()


def _get_document_package_by_request_and_id(request_id: str, package_id: str) -> dict[str, Any] | None:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM v1_document_packages WHERE request_id = ? AND package_id = ? LIMIT 1
            """,
            (request_id, package_id),
        )
        return _serialize_document_package_row(c.fetchone())
    finally:
        conn.close()


def _get_document_package_row_by_request_and_id(request_id: str, package_id: str) -> sqlite3.Row | None:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT * FROM v1_document_packages WHERE request_id = ? AND package_id = ? LIMIT 1
            """,
            (request_id, package_id),
        )
        return c.fetchone()
    finally:
        conn.close()


def _get_document_package_by_idempotency(request_id: str, idempotency_key: str | None) -> dict[str, Any] | None:
    if not idempotency_key:
        return None
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT * FROM v1_document_packages WHERE request_id = ? AND idempotency_key = ? LIMIT 1",
            (request_id, idempotency_key),
        )
        return _serialize_document_package_row(c.fetchone())
    finally:
        conn.close()


def _get_package_tenant_id(row: sqlite3.Row | None) -> str | None:
    if not row:
        return None
    manifest = _safe_json_loads(row["manifest_json"], default={})
    if not isinstance(manifest, dict):
        return None
    tenant_id = manifest.get("tenant_id")
    if isinstance(tenant_id, str):
        tenant_id = tenant_id.strip()
        if tenant_id:
            return tenant_id
    return None


def _assert_package_tenant_scope(request: Request, row: sqlite3.Row) -> None:
    manifest_tenant = _get_package_tenant_id(row)
    if not manifest_tenant:
        return
    request_tenant = request.headers.get("X-Tenant-Id") or request.query_params.get("tenant_id")
    if not request_tenant:
        raise HTTPException(status_code=403, detail="missing tenant scope")
    if request_tenant != manifest_tenant:
        raise HTTPException(status_code=403, detail="tenant mismatch")


def _build_package_member_inventory(
    render_job: dict[str, Any] | sqlite3.Row,
    asset_formats: list[str],
) -> list[dict[str, Any]]:
    if isinstance(render_job, sqlite3.Row):
        render_job = dict(render_job)
    assets = _safe_json_loads(render_job.get("assets"), default=[])
    if not isinstance(assets, list):
        return []
    requested = _normalize_output_formats(asset_formats) if asset_formats else []
    if not requested:
        requested = _normalize_output_formats(render_job.get("requested_outputs", []))
    if not requested and assets:
        requested = _normalize_output_formats([str(asset.get("format", "")) for asset in assets if isinstance(asset, dict)])

    available = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        fmt = str(asset.get("format", "")).lower()
        if fmt in requested:
            available[fmt] = {
                "format": fmt,
                "path": asset.get("path"),
                "size_bytes": asset.get("size_bytes"),
                "sha256": _normalize_asset_hash(asset.get("sha256")),
                "content_type": asset.get("content_type"),
            }

    selected = []
    for fmt in requested:
        candidate = available.get(fmt)
        if not candidate:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot create package: missing render member for format={fmt}",
            )
        selected.append(candidate)
    return selected


def _compute_package_id(
    render_job: dict[str, Any] | sqlite3.Row,
    selected_members: list[dict[str, Any]],
) -> str:
    request_id = render_job.get("request_id") if isinstance(render_job, dict) else render_job["request_id"]
    template_id = render_job.get("template_id") if isinstance(render_job, dict) else render_job["template_id"]
    template_version = render_job.get("template_version") if isinstance(render_job, dict) else render_job["template_version"]
    template_locale = render_job.get("template_locale") if isinstance(render_job, dict) else render_job["template_locale"]
    template_jurisdiction = render_job.get("template_jurisdiction") if isinstance(render_job, dict) else render_job["template_jurisdiction"]
    package_seed = {
        "request_id": request_id,
        "template_id": template_id,
        "template_version": template_version,
        "template_locale": template_locale,
        "template_jurisdiction": template_jurisdiction,
        "selected_outputs": sorted({str(member["format"]) for member in selected_members}),
        "member_hashes": {member["format"]: member["sha256"] for member in sorted(selected_members, key=lambda item: item["format"])},
        "document_data_id": render_job.get("document_data_id") if isinstance(render_job, dict) else render_job["document_data_id"],
    }
    return f"docpkg_{hashlib.sha256(json.dumps(package_seed, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:24]}"


def _build_and_store_document_package(
    request_id: str,
    render_job: dict[str, Any],
    selected_members: list[dict[str, Any]],
    idempotency_key: str | None,
    *,
    created_at: str | None = None,
) -> tuple[str, dict[str, Any]]:
    now = created_at or datetime.now(timezone.utc).isoformat()
    package_id = _compute_package_id(render_job, selected_members)
    manifest = _build_document_package_payload(render_job, selected_members, package_id, now)
    package_path, package_hash, package_size = _write_document_package_archive(
        package_id=package_id,
        selected_members=selected_members,
        manifest=manifest,
    )
    _upsert_document_package_record(
        package_id=package_id,
        request_id=request_id,
        manifest=manifest,
        package_path=package_path,
        package_hash=package_hash,
        size_bytes=package_size,
        created_outputs=[member["format"] for member in selected_members],
        idempotency_key=idempotency_key,
        created_at=now,
    )
    return package_id, manifest


def _normalize_text_payload(payload: Any) -> str:
    if isinstance(payload, str):
        text = payload
    else:
        text = json.dumps(payload, ensure_ascii=False)
    text = text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text payload")
    if len(text.encode("utf-8")) > 20000:
        raise HTTPException(status_code=413, detail="Text payload too large")
    return text


def _ingest_file_bytes(file: UploadFile, *, max_bytes: int = 8 * 1024 * 1024) -> bytes:
    content = file.file.read()
    size = len(content)
    if size > max_bytes:
        raise HTTPException(status_code=413, detail=f"File too large: {file.filename}")
    if not content:
        raise HTTPException(status_code=400, detail=f"File is empty: {file.filename}")
    return content


def _is_allowed_mime(content_type: str | None, *, filename: str | None, modality: str | None = None) -> bool:
    allowed_images = {
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/gif",
    }
    allowed_documents = {
        "application/pdf",
        "text/plain",
        "text/markdown",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    allowed_audio = {
        "audio/mpeg",
        "audio/wav",
        "audio/webm",
        "audio/ogg",
        "audio/mp4",
        "audio/x-m4a",
    }
    if modality == "image" and content_type:
        return content_type in allowed_images
    if modality == "voice" and content_type:
        return content_type in allowed_audio

    if content_type:
        if content_type in allowed_images | allowed_documents | allowed_audio:
            return True
        if content_type.startswith("image/"):
            return True
        if content_type.startswith("text/"):
            return True
        if content_type.startswith("audio/"):
            return True

    return bool(filename and filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".pdf", ".txt", ".md", ".doc", ".docx", ".wav", ".mp3", ".m4a", ".ogg", ".webm")))


def _collect_intake_observations_for_project(project_id: str) -> dict[str, list[dict[str, Any]]]:
    conn = _db()
    c = conn.cursor()
    c.execute(
        "SELECT id, modality, status, trust, payload, metadata, provenance, content_sha256, size_bytes, received_at, created_at, updated_at "
        "FROM v1_intake_observations WHERE project_id = ? ORDER BY created_at ASC",
        (project_id,),
    )
    rows = c.fetchall()
    conn.close()

    items = []
    for row in rows:
        r = dict(row)
        r["payload"] = _safe_json_loads(r.get("payload"), {})
        r["metadata"] = _safe_json_loads(r.get("metadata"), {})
        r["provenance"] = _safe_json_loads(r.get("provenance"), {})
        items.append(r)

    return {"items": items, "total": len(items)}


_init_v1_tables()


def _response_status_sequence(conn: sqlite3.Connection, response_id: str) -> int:
    c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(sequence), 0) FROM v1_response_events WHERE response_id = ?", (response_id,))
    return (c.fetchone()[0] or 0) + 1


def _serialize_response_event(response_id: str, event_type: str, payload: dict[str, Any], *, sequence: int | None = None) -> dict[str, Any]:
    event_sequence = sequence if sequence is not None else None
    event = {"type": event_type}
    event.update(payload)
    if response_id and "response_id" not in event:
        event["response_id"] = response_id
    if event_sequence is not None:
        event["sequence"] = event_sequence
    return event


def _append_response_event(
    response_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    status: str | None = None,
    output_text: str | None = None,
    connection: sqlite3.Connection | None = None,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    conn = connection if connection is not None else _db()
    own_connection = connection is None
    try:
        sequence = _response_status_sequence(conn, response_id)
        event = _serialize_response_event(response_id, event_type, payload, sequence=sequence)
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO v1_response_events (response_id, sequence, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (response_id, sequence, event_type, json.dumps(event), now),
        )
        update = "UPDATE v1_response_runs SET last_sequence = ?, updated_at = ?"
        if status is not None:
            update += ", status = ?"
        if output_text is not None:
            update += ", output_text = ?"
        params = [sequence, now]
        if status is not None:
            params.append(status)
        if output_text is not None:
            params.append(output_text)
        params.append(response_id)
        c.execute(update + " WHERE id = ?", params)
        if own_connection:
            conn.commit()
        return sequence
    finally:
        if own_connection:
            conn.close()


def _append_response_event_with_connection(
    response_id: str,
    event_type: str,
    payload: dict[str, Any],
    *,
    status: str | None = None,
    output_text: str | None = None,
    connection: sqlite3.Connection,
) -> int:
    return _append_response_event(
        response_id,
        event_type,
        payload,
        status=status,
        output_text=output_text,
        connection=connection,
    )


def _get_response_row(response_id: str) -> sqlite3.Row | None:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute("SELECT * FROM v1_response_runs WHERE id = ?", (response_id,))
        return c.fetchone()
    finally:
        conn.close()


def _get_response_id_by_idempotency(idempotency_key: str | None) -> str | None:
    if not idempotency_key:
        return None
    conn = _db()
    try:
        c = conn.cursor()
        c.execute("SELECT response_id FROM v1_response_idempotency WHERE idempotency_key = ?", (idempotency_key,))
        row = c.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _response_events_after(response_id: str, starting_after: int) -> list[sqlite3.Row]:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT sequence, event_type, payload FROM v1_response_events WHERE response_id = ? AND sequence > ? ORDER BY sequence ASC",
            (response_id, int(starting_after)),
        )
        return c.fetchall()
    finally:
        conn.close()


def _response_status(response_id: str) -> str | None:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute("SELECT status FROM v1_response_runs WHERE id = ?", (response_id,))
        row = c.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _response_payload_from_row(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "id": row["id"],
        "object": "response",
        "status": row["status"],
        "model": row["model"],
        "provider": row["provider"],
        "project_id": row["project_id"],
        "background": bool(row["background"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "output_text": row["output_text"] or "",
        "last_sequence": row["last_sequence"] or 0,
        "error": None if row["error_code"] is None and row["error_message"] is None else {
            "code": row["error_code"],
            "message": row["error_message"],
        },
    }


async def _run_response_task(response_id: str, messages: list[dict[str, Any]], *, model: str, provider: str | None = None):
    from providers import AIProviderManager
    _append_response_event(response_id, "response.status.updated", {
        "status": "running",
        "response": {"id": response_id, "status": "running"},
    }, status="running")

    manager = AIProviderManager()
    output = None
    try:
        result = await manager.generate(messages=messages, model=model, provider=provider)
        if _response_status(response_id) == "cancelled":
            return
        output = result.get("response", result.get("content", ""))
        if output:
            _append_response_event(response_id, "response.output_text.delta", {"delta": output}, output_text=output)
        _append_response_event(response_id, "response.completed", {
            "response": {"id": response_id, "status": "completed", "output_text": output},
            "status": "completed",
        }, status="completed", output_text=output)
    except Exception as exc:
        if _response_status(response_id) == "cancelled":
            return
        error_message = str(exc)
        conn = _db()
        try:
            c = conn.cursor()
            c.execute(
                "UPDATE v1_response_runs SET status = ?, error_code = ?, error_message = ?, updated_at = ? WHERE id = ?",
                ("failed", "provider_error", error_message, datetime.now(timezone.utc).isoformat(), response_id),
            )
            conn.commit()
        finally:
            conn.close()

        _append_response_event(response_id, "response.failed", {
            "response": {
                "id": response_id,
                "status": "failed",
                "error": {
                    "code": "provider_error",
                    "message": error_message,
                },
            },
            "error_code": "provider_error",
            "response_id": response_id,
            "status": "failed",
        }, status="failed")


def _parse_response_input(raw_input: Any) -> list[dict[str, str]]:
    if isinstance(raw_input, str):
        return [{"role": "user", "content": raw_input}]
    messages: list[dict[str, str]] = []
    if isinstance(raw_input, list):
        for item in raw_input:
            if isinstance(item, dict):
                role = str(item.get("role", "user"))
                content = item.get("content", "")
                if isinstance(content, list):
                    content = "".join(
                        piece.get("text", "") if isinstance(piece, dict) else str(piece)
                        for piece in content
                    )
                messages.append({"role": role, "content": str(content) if content is not None else ""})
    return messages


def _ensure_response_exists(response_id: str) -> bool:
    conn = _db()
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM v1_response_runs WHERE id = ? LIMIT 1", (response_id,))
        return c.fetchone() is not None
    finally:
        conn.close()


def _create_response_record(
    messages: list[dict[str, str]],
    *,
    project_id: str | None = None,
    model: str = "kolibri",
    provider: str | None = None,
    background: bool = False,
) -> str:
    response_id = f"resp_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO v1_response_runs (id, project_id, model, provider, input, background, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (response_id, project_id, model, provider, json.dumps(messages, ensure_ascii=False), 1 if background else 0, "queued", now, now),
        )
        _append_response_event_with_connection(response_id, "response.created", {
            "response": {"id": response_id, "status": "queued"},
        }, status="queued", connection=conn)
        if background:
            _append_response_event_with_connection(response_id, "response.status.updated", {
                "response_id": response_id,
                "status": "queued",
                "response": {"id": response_id, "status": "queued"},
            }, status="queued", connection=conn)
        conn.commit()
    finally:
        conn.close()
    return response_id


def _session_id():
    return f"sess_{uuid.uuid4().hex[:16]}"


def _frame_sse_event(event_type: str, payload: dict[str, Any], sequence: int) -> str:
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event_type}\nid: {sequence}\ndata: {body}\n\n"


async def _stream_response_events_from_db(response_id: str, starting_after: int = 0, *, stop_after_nonterminal_event: bool = False):
    last_sequence = max(0, int(starting_after))
    started = time.monotonic()
    seen_terminal = False
    while True:
        rows = _response_events_after(response_id, last_sequence)
        for row in rows:
            payload = _safe_json_loads(row["payload"], default={})
            if not isinstance(payload, dict):
                payload = {}
            event_type = str(row["event_type"] or payload.get("type") or "message")
            payload = dict(payload)
            sequence = int(row["sequence"])
            last_sequence = max(last_sequence, sequence)
            if stop_after_nonterminal_event and event_type in {"response.created", "response.status.updated"}:
                yield _frame_sse_event(event_type, payload, sequence)
                return
            if event_type not in {"response.completed", "response.failed", "response.cancelled"}:
                yield _frame_sse_event(event_type, payload, sequence)
                continue
            yield _frame_sse_event(event_type, payload, sequence)
            seen_terminal = True
        if stop_after_nonterminal_event:
            if seen_terminal:
                break
        if seen_terminal or _response_status(response_id) in {"completed", "failed", "cancelled"}:
            break
        if time.monotonic() - started > 35:
            break
        await asyncio.sleep(0.2)


def _is_session_active(session_id: Optional[str]) -> bool:
    if not session_id:
        return False
    now = time.time()
    cutoff = now - APP_SESSION_TTL_SECONDS
    conn = _db()
    c = conn.cursor()
    c.execute("DELETE FROM app_sessions WHERE revoked = 1 OR created_at < ?", (cutoff,))
    c.execute("SELECT id FROM app_sessions WHERE id = ? AND revoked = 0", (session_id,))
    active = c.fetchone() is not None
    conn.commit()
    conn.close()
    return active


def _create_session(session_id: Optional[str] = None) -> str:
    sid = session_id or _session_id()
    conn = _db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO app_sessions (id, created_at, revoked) VALUES (?, ?, 0)",
        (sid, time.time()),
    )
    conn.commit()
    conn.close()
    return sid


def _revoke_session(session_id: Optional[str]):
    if not session_id:
        return
    conn = _db()
    c = conn.cursor()
    c.execute("UPDATE app_sessions SET revoked = 1 WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()


def _set_session_cookie(response: Response, session_id: str):
    response.set_cookie(
        key=APP_SESSION_COOKIE_NAME,
        value=session_id,
        max_age=APP_SESSION_TTL_SECONDS,
        httponly=True,
        secure=APP_SESSION_SECURE_COOKIE,
        samesite="lax",
        path="/",
        expires=(datetime.now(timezone.utc) + timedelta(seconds=APP_SESSION_TTL_SECONDS)),
    )


def _clear_session_cookie(response: Response):
    response.delete_cookie(
        key=APP_SESSION_COOKIE_NAME,
        path="/",
    )


def _public_session_payload(session_id: str):
    return {
        "object": "public.session",
        "session_id": session_id,
        "active": True,
        "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=APP_SESSION_TTL_SECONDS)).isoformat(),
    }


class SessionState:
    """Minimal session state tied to session_id."""
    pass

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. " +
    "Отвечай на языке пользователя. Не используй эмодзи."
)


@router.post("/api/v1/shell/bootstrap")
async def shell_bootstrap():
    return {
        "session_id": f"sess_{uuid.uuid4().hex[:16]}",
        "session_type": "anonymous",
        "restored": False,
        "expires_at": None,
    }


@router.get("/api/v1/capabilities")
@router.get("/api/v1/public/capabilities")
async def capabilities():
    return {
        "capabilities": [
            {"id": "chat", "name": "Chat", "enabled": True},
            {"id": "estimates", "name": "Estimates", "enabled": True},
            {"id": "documents", "name": "Documents", "enabled": True},
            {"id": "agents", "name": "Agents", "enabled": False},
        ]
    }


@router.get("/api/v1/auth/session")
async def auth_session(request: Request):
    session_id = request.cookies.get(APP_SESSION_COOKIE_NAME)
    if not _is_session_active(session_id):
        raise HTTPException(status_code=401, detail="session_required")
    return {"user": {"session_id": session_id}, "authenticated": True}


@router.get("/v1/public/session")
@router.get("/api/v1/public/session")
async def get_public_session(request: Request):
    session_id = request.cookies.get(APP_SESSION_COOKIE_NAME)
    if not _is_session_active(session_id):
        raise HTTPException(status_code=401, detail="public_session_required_or_expired")
    return _public_session_payload(session_id)


@router.post("/v1/public/session")
@router.post("/api/v1/public/session")
async def create_public_session(request: Request, response: Response):
    session_id = request.cookies.get(APP_SESSION_COOKIE_NAME)
    if _is_session_active(session_id):
        session_id = _create_session(session_id)
    else:
        session_id = _create_session()
    _set_session_cookie(response, session_id)
    return _public_session_payload(session_id)


@router.post("/v1/auth/logout")
@router.post("/api/v1/auth/logout")
async def logout_session(request: Request, response: Response):
    session_id = request.cookies.get(APP_SESSION_COOKIE_NAME)
    _revoke_session(session_id)
    _clear_session_cookie(response)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@router.get("/api/v1/projects")
async def list_projects(page: int = 1, page_size: int = 100, include_deleted: str = None):
    conn = _db()
    c = conn.cursor()
    where = "" if include_deleted == "true" else "WHERE status != 'deleted'"
    c.execute(f"SELECT * FROM v1_projects {where} ORDER BY updated_at DESC LIMIT ? OFFSET ?",
              (page_size, (page - 1) * page_size))
    rows = [dict(r) for r in c.fetchall()]
    c.execute(f"SELECT COUNT(*) as cnt FROM v1_projects {where}")
    total = c.fetchone()["cnt"]
    conn.close()
    for r in rows:
        if r.get("metadata"):
            try:
                r["metadata"] = json.loads(r["metadata"])
            except:
                r["metadata"] = {}
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.post("/api/v1/projects")
async def create_project(request: Request):
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    pid = str(uuid.uuid4())
    title = body.get("title") or "Новый чат"
    metadata = json.dumps(body.get("metadata", {}))
    conn = _db()
    c = conn.cursor()
    c.execute("INSERT INTO v1_projects (id, title, title_source, status, version, message_count, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (pid, title, "default" if not body.get("title") else "manual", "active", 1, 0, metadata, now, now))
    conn.commit()
    conn.close()
    return {"id": pid, "title": title, "title_source": "default" if not body.get("title") else "manual",
            "status": "active", "version": 1, "message_count": 0, "metadata": json.loads(metadata),
            "created_at": now, "updated_at": now, "last_message_at": None, "deleted_at": None}


@router.get("/api/v1/projects/{project_id}")
async def get_project(project_id: str):
    conn = _db()
    c = conn.cursor()
    c.execute("SELECT * FROM v1_projects WHERE id = ?", (project_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    r = dict(row)
    try:
        r["metadata"] = json.loads(r.get("metadata", "{}"))
    except:
        r["metadata"] = {}
    return r


@router.patch("/api/v1/projects/{project_id}")
async def update_project(project_id: str, request: Request):
    body = await request.json()
    conn = _db()
    c = conn.cursor()
    c.execute("SELECT * FROM v1_projects WHERE id = ?", (project_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Project not found")
    updates = []
    params = []
    if "title" in body:
        updates.append("title = ?")
        params.append(body["title"])
    if "metadata" in body:
        updates.append("metadata = ?")
        params.append(json.dumps(body["metadata"]))
    if updates:
        updates.append("updated_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
        params.append(project_id)
        c.execute(f"UPDATE v1_projects SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    c.execute("SELECT * FROM v1_projects WHERE id = ?", (project_id,))
    r = dict(c.fetchone())
    conn.close()
    try:
        r["metadata"] = json.loads(r.get("metadata", "{}"))
    except:
        r["metadata"] = {}
    return r


@router.delete("/api/v1/projects/{project_id}")
async def delete_project(project_id: str):
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    c = conn.cursor()
    c.execute("UPDATE v1_projects SET status = 'deleted', deleted_at = ? WHERE id = ?", (now, project_id))
    conn.commit()
    conn.close()
    return {"id": project_id, "status": "deleted"}


@router.post("/api/v1/projects/{project_id}/restore")
async def restore_project(project_id: str):
    conn = _db()
    c = conn.cursor()
    c.execute("UPDATE v1_projects SET status = 'active', deleted_at = NULL WHERE id = ?", (project_id,))
    conn.commit()
    c.execute("SELECT * FROM v1_projects WHERE id = ?", (project_id,))
    r = dict(c.fetchone()) if c.fetchone() else None
    conn.close()
    if not r:
        raise HTTPException(status_code=404, detail="Project not found")
    return r


@router.post("/api/v1/projects/{project_id}/claim")
async def claim_project(project_id: str, request: Request):
    return await get_project(project_id)


# ---------------------------------------------------------------------------
# Project Messages
# ---------------------------------------------------------------------------

@router.get("/api/v1/projects/{project_id}/messages")
async def list_messages(project_id: str, after: int = None, limit: int = 500):
    conn = _db()
    c = conn.cursor()
    if after is not None:
        c.execute("SELECT * FROM v1_messages WHERE project_id = ? AND sequence > ? ORDER BY sequence ASC LIMIT ?",
                  (project_id, after, limit))
    else:
        c.execute("SELECT * FROM v1_messages WHERE project_id = ? ORDER BY sequence ASC LIMIT ?",
                  (project_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    c.execute("SELECT COUNT(*) as cnt FROM v1_messages WHERE project_id = ?", (project_id,))
    total = c.fetchone()["cnt"]
    conn.close()
    for r in rows:
        if r.get("metadata"):
            try:
                r["metadata"] = json.loads(r["metadata"])
            except:
                r["metadata"] = {}
    return {"items": rows, "total": total, "after": after or 0, "limit": limit}


@router.post("/api/v1/projects/{project_id}/messages")
async def append_message(project_id: str, request: Request):
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    msg_id = body.get("client_message_id") or str(uuid.uuid4())
    role = body.get("role", "user")
    content = body.get("content", "")
    status = body.get("status", "completed")
    metadata = json.dumps(body.get("metadata", {}))

    conn = _db()
    c = conn.cursor()
    c.execute("SELECT COALESCE(MAX(sequence), 0) + 1 as next_seq FROM v1_messages WHERE project_id = ?", (project_id,))
    seq = c.fetchone()["next_seq"]
    c.execute("INSERT INTO v1_messages (id, project_id, sequence, version, role, content, status, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (msg_id, project_id, seq, 1, role, content, status, metadata, now, now))
    c.execute("UPDATE v1_projects SET message_count = message_count + 1, last_message_at = ?, updated_at = ? WHERE id = ?",
              (now, now, project_id))
    # Auto-generate title from first user message
    if role == "user":
        c.execute("SELECT message_count FROM v1_projects WHERE id = ?", (project_id,))
        mc = c.fetchone()["message_count"]
        if mc <= 1:
            title = content[:60].strip()
            c.execute("UPDATE v1_projects SET title = ?, title_source = 'message' WHERE id = ? AND title_source = 'default'",
                      (title, project_id))
    conn.commit()
    conn.close()
    return {"id": msg_id, "project_id": project_id, "sequence": seq, "version": 1,
            "role": role, "content": content, "status": status,
            "metadata": json.loads(metadata), "created_at": now, "updated_at": now}


@router.patch("/api/v1/projects/{project_id}/messages/{message_id}")
async def update_message(project_id: str, message_id: str, request: Request):
    body = await request.json()
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    c = conn.cursor()
    updates = []
    params = []
    if "content" in body:
        updates.append("content = ?")
        params.append(body["content"])
    if "status" in body:
        updates.append("status = ?")
        params.append(body["status"])
    if "metadata" in body:
        updates.append("metadata = ?")
        params.append(json.dumps(body["metadata"]))
    if updates:
        updates.append("updated_at = ?")
        params.append(now)
        params.append(message_id)
        c.execute(f"UPDATE v1_messages SET {', '.join(updates)} WHERE id = ? AND project_id = ?", params + [project_id])
        conn.commit()
    c.execute("SELECT * FROM v1_messages WHERE id = ? AND project_id = ?", (message_id, project_id))
    r = c.fetchone()
    conn.close()
    if not r:
        raise HTTPException(status_code=404, detail="Message not found")
    result = dict(r)
    try:
        result["metadata"] = json.loads(result.get("metadata", "{}"))
    except:
        result["metadata"] = {}
    return result


def _extract_file_observation(project_id: str, file: UploadFile, *, field_name: str) -> list[dict[str, Any]]:
    file_mime = file.content_type
    filename = file.filename or "file"
    if not _is_allowed_mime(file_mime, filename=filename):
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")

    file_bytes = _ingest_file_bytes(file)
    lowered = (file_mime or "").lower()
    if lowered.startswith("image/"):
        modality = "image"
    elif lowered.startswith("audio/"):
        modality = "voice"
    else:
        modality = "file"

    now = datetime.now(timezone.utc).isoformat()
    obs_id = str(uuid.uuid4())
    payload = {
        "modality": modality,
        "filename": filename,
        "content_type": file_mime,
        "size_bytes": len(file_bytes),
        "form_field": field_name,
        "content_excerpt": file_bytes[:64].hex()[:128],
    }
    metadata = {
        "origin": "intake",
        "source_field": field_name,
        "filename": filename,
    }
    provenance = {
        "source": "user_upload",
        "project_id": project_id,
        "content_type": file_mime,
        "observed_at": now,
        "filename": filename,
    }
    return [
        {
            "id": obs_id,
            "modality": modality,
            "status": "candidate",
            "trust": "untrusted",
            "payload": payload,
            "metadata": metadata,
            "provenance": provenance,
            "content_sha256": hashlib.sha256(file_bytes).hexdigest(),
            "size_bytes": len(file_bytes),
            "received_at": now,
            "created_at": now,
            "updated_at": now,
        }
    ]


def _extract_intake_text_items(modality: str, project_id: str, values: Any, *, form_field: str | None = None) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    if values is None:
        return collected

    if isinstance(values, list):
        values_iter = values
    else:
        values_iter = [values]

    for raw_value in values_iter:
        if isinstance(raw_value, dict):
            content = raw_value.get("transcript") or raw_value.get("text") or raw_value.get("content") or ""
            extra = dict(raw_value)
            extra.pop("transcript", None)
            extra.pop("text", None)
            extra.pop("content", None)
        else:
            content = raw_value
            extra = {}

        text = _normalize_text_payload(content)

        now = datetime.now(timezone.utc).isoformat()
        obs_id = str(uuid.uuid4())
        payload = {
            "modality": modality,
            "text": text,
        }
        if extra:
            payload.update(extra)
        if form_field:
            payload["source_field"] = form_field
        provenance = {
            "source": "user_input",
            "project_id": project_id,
            "modality": modality,
            "received_at": now,
            "source_field": form_field or modality,
        }
        metadata = {
            "origin": "intake",
            "size_bytes": len(text.encode("utf-8")),
        }
        collected.append({
            "id": obs_id,
            "modality": modality,
            "status": "candidate",
            "trust": "untrusted",
            "payload": payload,
            "metadata": metadata,
            "provenance": provenance,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "size_bytes": len(text.encode("utf-8")),
            "received_at": now,
            "created_at": now,
            "updated_at": now,
        })

    return collected


def _parse_intake_payload(project_id: str, body: dict[str, Any] | None = None, form: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    if body:
        observations.extend(_extract_intake_text_items("text", project_id, body.get("text"), form_field="text"))
        observations.extend(_extract_intake_text_items("text", project_id, body.get("content"), form_field="content"))
        observations.extend(_extract_intake_text_items("text", project_id, body.get("message"), form_field="message"))
        observations.extend(_extract_intake_text_items("voice", project_id, body.get("voice"), form_field="voice"))
        observations.extend(_extract_intake_text_items("voice", project_id, body.get("voice_transcript"), form_field="voice_transcript"))

    if form:
        for key in ("text", "message", "content", "voice", "voice_transcript"):
            if key in form and isinstance(form[key], str):
                observations.extend(_extract_intake_text_items(
                    "voice" if "voice" in key else "text",
                    project_id,
                    form.get(key),
                    form_field=key,
                ))

    if form:
        for key in list(form.keys()):
            item = form[key]
            if isinstance(item, UploadFile):
                observations.extend(_extract_file_observation(project_id, item, field_name=key))
            elif isinstance(item, list):
                for nested in item:
                    if isinstance(nested, UploadFile):
                        observations.extend(_extract_file_observation(project_id, nested, field_name=key))

    # Deduplicate by payload hash for the same project to avoid accidental duplicates.
    by_hash = {}
    for observation in observations:
        by_hash_key = f"{project_id}:{observation['modality']}:{observation['content_sha256']}"
        if by_hash_key not in by_hash:
            by_hash[by_hash_key] = observation
    return list(by_hash.values())


def _assert_project_exists(project_id: str, *, cursor):
    cursor.execute("SELECT id FROM v1_projects WHERE id = ?", (project_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Project not found")


def _persist_intake_observations(project_id: str, observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not observations:
        raise HTTPException(status_code=400, detail="No intake observations provided")

    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    c = conn.cursor()
    _assert_project_exists(project_id, cursor=c)

    for observation in observations:
        observation["received_at"] = observation["received_at"] or now
        observation["created_at"] = now
        observation["updated_at"] = now
        observation["trust"] = observation.get("trust") or "untrusted"
        observation["status"] = observation.get("status") or "candidate"
        c.execute(
            "INSERT INTO v1_intake_observations (id, project_id, modality, status, trust, payload, metadata, provenance, content_sha256, size_bytes, received_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                observation["id"],
                project_id,
                observation["modality"],
                observation["status"],
                observation["trust"],
                json.dumps(observation["payload"]),
                json.dumps(observation["metadata"]),
                json.dumps(observation["provenance"]),
                observation["content_sha256"],
                observation.get("size_bytes", 0),
                observation["received_at"],
                now,
                now,
            ),
        )
    conn.commit()

    c.execute(
        "SELECT id, modality, status, trust, payload, metadata, provenance, content_sha256, size_bytes, received_at, created_at, updated_at "
        "FROM v1_intake_observations WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
        (project_id, len(observations)),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()

    for row in rows:
        row["payload"] = _safe_json_loads(row.get("payload"), {})
        row["metadata"] = _safe_json_loads(row.get("metadata"), {})
        row["provenance"] = _safe_json_loads(row.get("provenance"), {})

    return rows


def _shorten_intent_text(value: str, max_len: int = 3000) -> str:
    text = (value or "").strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].strip()


_SAFE_ASSUMPTION_TAGS = ("assumption", "safe_assumption")
_BLOCKER_TAGS = ("blocker", "safety", "legal", "policy", "intent")


def _safe_intent_text(value: str) -> str:
    return (value or "").strip().lower()


def _split_text_list(value: str) -> list[str]:
    parts = []
    for part in re.split(r"[\\n,;]+", value or ""):
        part = part.strip()
        if part:
            parts.append(part)
    return parts


def _extract_project_brief_fields(text: str) -> dict[str, Any]:
    values = {
        "object_type": "",
        "region": "",
        "purpose": "",
        "requirements": [],
        "constraints": [],
    }

    if not text:
        return values

    source = text.replace("\r\n", "\n")
    for line in source.split("\n"):
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip().lower()
        value = raw_value.strip()
        if not value:
            continue
        if key in {"объект", "объектом", "объект проект", "объект проекта", "тип объекта", "object", "объект:", "object_type"}:
            values["object_type"] = value
            continue
        if key in {"регион", "регион/локация", "локация", "местоположение", "region", "город", "город/регион"}:
            values["region"] = value
            continue
        if key in {"назначение", "цель", "purpose", "назначение объекта", "use_case"}:
            values["purpose"] = value
            continue
        if key in {"требования", "требования к", "requirements", "must", "обязательные требования"}:
            values["requirements"] = _split_text_list(value)
            continue
        if key in {"ограничения", "constraints", "restriction", "ограничения по", "ограничение"}:
            values["constraints"] = _split_text_list(value)
            continue

    # If line-based extraction did not catch fields, try a tiny heuristic pass.
    source_lower = source.lower()
    if not values["region"]:
        for marker in ("регион", "город", "область"):
            if f"{marker}:" in source_lower:
                values["region"] = source.split(f"{marker}:")[-1].split("\n", 1)[0].strip()
                break
    if not values["purpose"] and "назначение" in source_lower:
        tail = source_lower.split("назначение", 1)[-1]
        if ":" in tail:
            values["purpose"] = tail.split(":", 1)[1].split("\n", 1)[0].strip()

    return values


def _compute_brief_confidence(fields: dict[str, Any], *, source_has_text: bool) -> Decimal:
    confidence = Decimal("0.20") if source_has_text else Decimal("0.00")
    if fields["object_type"]:
        confidence += Decimal("0.20")
    if fields["region"]:
        confidence += Decimal("0.20")
    if fields["purpose"]:
        confidence += Decimal("0.20")
    if fields["requirements"]:
        confidence += Decimal("0.10")
    if fields["constraints"]:
        confidence += Decimal("0.10")
    return (confidence.min(Decimal("1.00"))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _safe_detect_blockers(value: str) -> list[dict[str, Any]]:
    lowered = _safe_intent_text(value)
    blockers: list[dict[str, Any]] = []

    safety_hits = [
        "взлом",
        "наруш",
        "незакон",
        "обход",
        "поддел",
        "мошен",
        "взрыв",
        "насиль",
        "хак",
        "хакер",
    ]
    legal_hits = [
        "юрид",
        "судеб",
        "штраф",
        "лиценз",
        "наркот",
        "оруж",
        "неглас",
    ]
    intent_hits = [
        "заводить конфликт",
        "атак",
        "оскорб",
        "оскорбление",
        "дискримина",
    ]

    if any(hit in lowered for hit in safety_hits):
        blockers.append({
            "id": "blocker_001",
            "class": "safety",
            "rationale": "Input includes terms that may relate to unsafe activity.",
            "question": "Приведите безопасный и законный альтернативный вариант задачи.",
            "impact": "high",
        })
    if any(hit in lowered for hit in legal_hits):
        blockers.append({
            "id": "blocker_002",
            "class": "legal",
            "rationale": "Input includes legal/compliance-sensitive terms requiring governance check.",
            "question": "Подтвердите соблюдение действующих норм и правовых рамок.",
            "impact": "high",
        })
    if any(hit in lowered for hit in intent_hits):
        blockers.append({
            "id": "blocker_003",
            "class": "intent",
            "rationale": "Input contains intent that is outside normal project-construction scope.",
            "question": "Опишите цель в рамках проектных, строительных или технико-экономических задач.",
            "impact": "medium",
        })

    return blockers


def _safe_detect_assumptions(brief: dict[str, Any]) -> list[dict[str, Any]]:
    assumptions: list[dict[str, Any]] = []
    if not brief.get("object_type"):
        assumptions.append({
            "id": "assumption_001",
            "class": "safe_assumption",
            "statement": "Объект проекта уточняется на следующем сообщении.",
            "impact": "medium",
            "default": "будем считать тип объекта жилой до уточнения",
            "confidence": "0.35",
        })
    if not brief.get("region"):
        assumptions.append({
            "id": "assumption_002",
            "class": "safe_assumption",
            "statement": "Населённый пункт/регион уточнится в диалоге.",
            "impact": "medium",
            "default": "по умолчанию рассматриваем общий профиль объекта",
            "confidence": "0.40",
        })
    if not brief.get("purpose"):
        assumptions.append({
            "id": "assumption_003",
            "class": "safe_assumption",
            "statement": "Назначение проекта будет уточнено в рамках следующего шага.",
            "impact": "medium",
            "default": "строительство/реконструкция по общему назначению",
            "confidence": "0.45",
        })
    if not brief.get("requirements"):
        assumptions.append({
            "id": "assumption_004",
            "class": "safe_assumption",
            "statement": "Технические требования будут расширены после уточнения объекта.",
            "impact": "low",
            "default": "минимальный базовый набор по умолчанию",
            "confidence": "0.60",
        })

    return assumptions


def _classify_intake_state(brief: dict[str, Any]) -> dict[str, Any]:
    original_intent = brief.get("original_intent", "")
    blockers = _safe_detect_blockers(original_intent)
    blockers = [b for b in blockers if b.get("class") in _BLOCKER_TAGS]
    assumptions = _safe_detect_assumptions(brief)
    assumptions = [a for a in assumptions if a.get("class") in _SAFE_ASSUMPTION_TAGS]

    question_bundle = None
    if blockers:
        unique_questions = []
        seen_questions = set()
        for blocker in blockers:
            q = blocker.get("question", "")
            if q and q not in seen_questions:
                unique_questions.append(q)
                seen_questions.add(q)
        question_bundle = {
            "id": "initial_blocking_bundle",
            "is_blocking": True,
            "scope": "project_intake",
            "questions": unique_questions[:3],
            "question_count": len(unique_questions),
        }
    else:
        question_bundle = {
            "id": "initial_nonblocking_gaps",
            "is_blocking": False,
            "scope": "project_intake",
            "questions": [
                "Предоставьте площадь/объём работы.",
                "Опишите бюджетный коридор и сроки.",
            ],
            "question_count": 2,
        }

    return {
        "class": "blocker" if blockers else "safe",
        "blockers": blockers,
        "assumptions": assumptions,
        "question_bundle": question_bundle,
        "question_bundle_count": 1,
        "remaining_questions_count": 0 if not blockers else 1,
    }


def _collect_project_source_intent(project_id: str) -> list[str]:
    observations = _collect_intake_observations_for_project(project_id)["items"]
    intents: list[str] = []
    for observation in observations:
        payload = observation.get("payload") or {}
        if observation.get("modality") in {"text", "voice"}:
            text = payload.get("text") if isinstance(payload, dict) else None
            if text:
                intents.append(text.strip())
    return intents


def _project_brief_from_observations(project_id: str) -> dict[str, Any]:
    intents = _collect_project_source_intent(project_id)
    if not intents:
        raise HTTPException(status_code=400, detail="No content to normalize into brief")

    original_intent = _shorten_intent_text("\n".join(intents))
    fields = _extract_project_brief_fields(original_intent)
    confidence = _compute_brief_confidence(fields, source_has_text=True)
    brief = {
        "project_id": project_id,
        "version": 1,
        "object_type": fields["object_type"],
        "region": fields["region"],
        "purpose": fields["purpose"],
        "requirements": fields["requirements"],
        "constraints": fields["constraints"],
        "original_intent": original_intent,
        "confidence": str(confidence),
        "metadata": {
            "source_items": len(intents),
            "source_kind": "intake_observations",
        },
    }
    brief["intake_register"] = _classify_intake_state(brief)
    return brief


def _active_project_brief_row(project_id: str, conn, cursor) -> Optional[sqlite3.Row]:
    cursor.execute(
        "SELECT * FROM v1_project_briefs WHERE project_id = ? AND is_active = 1 ORDER BY version DESC LIMIT 1",
        (project_id,),
    )
    return cursor.fetchone()


def _serialize_project_brief_row(row: Optional[sqlite3.Row]) -> Optional[dict[str, Any]]:
    if not row:
        return None
    payload = dict(row)
    payload["requirements"] = _safe_json_loads(payload.get("requirements"), [])
    payload["constraints"] = _safe_json_loads(payload.get("constraints"), [])
    payload["metadata"] = _safe_json_loads(payload.get("metadata"), {})
    payload["intake_register"] = payload["metadata"].get("intake_register") or {}
    if not payload["intake_register"]:
        payload["intake_register"] = _classify_intake_state(payload)
    payload["blockers"] = payload["intake_register"].get("blockers", [])
    payload["assumptions"] = payload["intake_register"].get("assumptions", [])
    payload["class"] = payload["intake_register"].get("class", "safe")
    payload["question_bundle"] = payload["intake_register"].get("question_bundle")
    payload["remaining_questions_count"] = payload["intake_register"].get("remaining_questions_count", 0)
    payload["question_bundle_count"] = payload["intake_register"].get("question_bundle_count", 0)
    payload["assumption_feedback"] = payload["metadata"].get("assumption_feedback", [])
    payload["assumption_feedback_updated_at"] = payload["metadata"].get("assumption_feedback_updated_at")
    payload["assumption_feedback_project_version"] = payload["metadata"].get("assumption_feedback_project_version")
    payload["replan_signal"] = payload["metadata"].get("replan_signal")
    return payload


def _brief_signature(project_brief: dict[str, Any]) -> str:
    canonical = json.dumps(
        {
            "object_type": project_brief.get("object_type", ""),
            "region": project_brief.get("region", ""),
            "purpose": project_brief.get("purpose", ""),
            "requirements": project_brief.get("requirements", []),
            "constraints": project_brief.get("constraints", []),
            "original_intent": project_brief.get("original_intent", ""),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _build_project_brief(project_id: str) -> dict[str, Any]:
    conn = _db()
    c = conn.cursor()
    _assert_project_exists(project_id, cursor=c)

    intents = _collect_project_source_intent(project_id)
    if not intents:
        conn.close()
        raise HTTPException(status_code=400, detail="No content to normalize into brief")

    project_brief = _project_brief_from_observations(project_id)
    new_signature = _brief_signature(project_brief)

    c.execute("SELECT id, object_type, region, purpose, requirements, constraints, original_intent, confidence, metadata FROM v1_project_briefs WHERE id IS NOT NULL AND project_id = ? ORDER BY version DESC LIMIT 1", (project_id,))
    last = c.fetchone()
    if last:
        last_payload = {
            "object_type": last["object_type"],
            "region": last["region"],
            "purpose": last["purpose"],
            "requirements": _safe_json_loads(last["requirements"], []),
            "constraints": _safe_json_loads(last["constraints"], []),
            "original_intent": last["original_intent"],
        }
        if _brief_signature(last_payload) == new_signature:
            row = _serialize_project_brief_row(last)
            if row:
                row["updated"] = False
            conn.close()
            return row

    c.execute(
        "UPDATE v1_project_briefs SET is_active = 0 WHERE project_id = ? AND is_active = 1",
        (project_id,),
    )
    c.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM v1_project_briefs WHERE project_id = ?",
        (project_id,),
    )
    version = c.fetchone()[0] or 1
    now = datetime.now(timezone.utc).isoformat()
    brief_id = str(uuid.uuid4())
    brief_metadata = dict(project_brief["metadata"])
    brief_metadata["intake_register"] = project_brief["intake_register"]
    c.execute(
        "INSERT INTO v1_project_briefs (id, project_id, version, is_active, object_type, region, purpose, requirements, constraints, original_intent, confidence, metadata, created_at, updated_at) "
        "VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            brief_id,
            project_id,
            version,
            project_brief["object_type"],
            project_brief["region"],
            project_brief["purpose"],
            json.dumps(project_brief["requirements"], ensure_ascii=False),
            json.dumps(project_brief["constraints"], ensure_ascii=False),
            project_brief["original_intent"],
            project_brief["confidence"],
            json.dumps(brief_metadata, ensure_ascii=False),
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()

    project_brief["id"] = brief_id
    project_brief["version"] = version
    project_brief["is_active"] = 1
    project_brief["created_at"] = now
    project_brief["updated_at"] = now
    project_brief["updated"] = True
    project_brief.update(project_brief["intake_register"])
    return project_brief


def _get_active_project_brief(project_id: str, *, project_exists: bool = True) -> dict[str, Any]:
    conn = _db()
    c = conn.cursor()
    if project_exists:
        _assert_project_exists(project_id, cursor=c)

    row = _active_project_brief_row(project_id, conn, c)
    payload = _serialize_project_brief_row(row)
    conn.close()
    if not payload:
        raise HTTPException(status_code=404, detail="ProjectBrief not found")
    payload["project_id"] = project_id
    return payload


def _serialize_project_brief_register(row: Optional[sqlite3.Row]) -> dict[str, Any]:
    payload = _serialize_project_brief_row(row)
    if not payload:
        raise HTTPException(status_code=404, detail="ProjectBrief not found")
    return {
        "project_id": payload["project_id"],
        "brief_id": payload["id"],
        "version": payload["version"],
        "class": payload.get("class", "safe"),
        "blockers": payload.get("blockers", []),
        "assumptions": payload.get("assumptions", []),
        "assumption_feedback": payload.get("metadata", {}).get("assumption_feedback", []),
        "assumption_feedback_updated_at": payload.get("metadata", {}).get("assumption_feedback_updated_at"),
        "assumption_feedback_project_version": payload.get("metadata", {}).get("assumption_feedback_project_version"),
        "question_bundle": payload.get("question_bundle"),
        "question_bundle_count": payload.get("question_bundle_count", 0),
        "remaining_questions_count": payload.get("remaining_questions_count", 0),
        "updated_at": payload.get("updated_at"),
        "replan_signal": payload.get("metadata", {}).get("replan_signal"),
    }


def _apply_intake_feedback(
    project_id: str,
    feedback: list[IntakeAssumptionFeedbackItem],
    replan: bool = True,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    conn = _db()
    c = conn.cursor()
    _assert_project_exists(project_id, cursor=c)
    row = _active_project_brief_row(project_id, conn, c)
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="ProjectBrief not found")

    metadata = _safe_json_loads(row["metadata"], {})
    feedback_payload = [dict(item.model_dump()) for item in feedback]
    metadata["assumption_feedback"] = feedback_payload
    metadata["assumption_feedback_updated_at"] = now
    metadata["assumption_feedback_project_version"] = row["version"]

    if replan:
        metadata["replan_signal"] = {
            "issued_at": now,
            "source": "intake_feedback",
            "brief_version": row["version"],
            "feedback_count": len(feedback_payload),
        }
    else:
        metadata.pop("replan_signal", None)

    c.execute("UPDATE v1_project_briefs SET metadata = ?, updated_at = ? WHERE id = ?", (
        json.dumps(metadata, ensure_ascii=False),
        now,
        row["id"],
    ))
    conn.commit()
    c.execute("SELECT * FROM v1_project_briefs WHERE id = ?", (row["id"],))
    updated_row = c.fetchone()
    conn.close()
    if not updated_row:
        raise HTTPException(status_code=404, detail="ProjectBrief not found after update")
    return _serialize_project_brief_register(updated_row)


@router.post("/api/v1/projects/{project_id}/source-documents")
async def upload_project_source_documents(project_id: str, request: Request):
    content_type = request.headers.get("content-type", "").lower()
    body = None
    form = None

    if "application/json" in content_type:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Invalid intake payload")
    elif content_type.startswith("multipart/form-data"):
        form_data = await request.form()
        form = {}
        for key, item in form_data.multi_items():
            if key not in form:
                form[key] = item
            else:
                existing = form[key]
                if isinstance(existing, list):
                    existing.append(item)
                else:
                    form[key] = [existing, item]
    else:
        raise HTTPException(status_code=415, detail="Unsupported content type")

    observations = _parse_intake_payload(project_id, body=body, form=form)
    persisted = _persist_intake_observations(project_id, observations)
    _ = _build_project_brief(project_id)
    return {"items": persisted, "total": len(persisted), "project_id": project_id}


@router.get("/api/v1/projects/{project_id}/source-documents")
async def list_project_source_documents(project_id: str):
    return _collect_intake_observations_for_project(project_id)


@router.post("/api/v1/intake")
async def intake(request: Request):
    content_type = request.headers.get("content-type", "").lower()
    body = None
    form = None

    if "application/json" in content_type:
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="Invalid intake payload")
        project_id = body.get("project_id")
    elif content_type.startswith("multipart/form-data"):
        form_data = await request.form()
        form = {}
        for key, item in form_data.multi_items():
            if key not in form:
                form[key] = item
            else:
                existing = form[key]
                if isinstance(existing, list):
                    existing.append(item)
                else:
                    form[key] = [existing, item]
        project_id = form.get("project_id")
        if isinstance(project_id, list):
            project_id = project_id[0]
        if isinstance(project_id, str):
            project_id = project_id.strip()
    else:
        raise HTTPException(status_code=415, detail="Unsupported content type")

    if not project_id:
        raise HTTPException(status_code=400, detail="Missing project_id")

    observations = _parse_intake_payload(project_id, body=body, form=form)
    persisted = _persist_intake_observations(project_id, observations)
    _ = _build_project_brief(project_id)
    return {"project_id": project_id, "items": persisted, "total": len(persisted)}


@router.post("/api/v1/projects/{project_id}/brief")
async def normalize_project_brief(project_id: str):
    return _build_project_brief(project_id)


@router.get("/api/v1/projects/{project_id}/brief")
async def get_project_brief(project_id: str):
    return _get_active_project_brief(project_id)


@router.get("/api/v1/projects/{project_id}/brief/register")
async def get_project_brief_register(project_id: str):
    conn = _db()
    c = conn.cursor()
    _assert_project_exists(project_id, cursor=c)
    row = _active_project_brief_row(project_id, conn, c)
    conn.close()
    return _serialize_project_brief_register(row)


@router.post("/api/v1/projects/{project_id}/brief/register/decision")
async def post_project_brief_register_decision(project_id: str, request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid feedback payload")
    try:
        payload = IntakeAssumptionFeedbackRequest.model_validate(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid feedback payload: {exc}")
    return _apply_intake_feedback(project_id, payload.feedback, replan=payload.replan)


@router.post("/v1/realtime/sessions")
@router.post("/api/v1/realtime/sessions")
async def create_realtime_session(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    response_id = body.get("response_id")
    if response_id and not _ensure_response_exists(response_id):
        raise HTTPException(status_code=400, detail="Unknown response_id for realtime session")

    now = datetime.now(timezone.utc)
    session_id = f"realtime_{uuid.uuid4().hex[:16]}"
    metadata = json.dumps({
        "model": body.get("model", "kolibri"),
        "provider": body.get("provider", None),
        "run_mode": body.get("mode", "chat"),
    })
    ttl_seconds = int(body.get("ttl_seconds", 1800)) if isinstance(body.get("ttl_seconds"), int) else 1800
    created_at = now.isoformat()
    expires_at = (now + timedelta(seconds=ttl_seconds)).isoformat()

    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO v1_realtime_sessions (id, response_id, status, metadata, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, response_id, "active", metadata, created_at, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "id": session_id,
        "response_id": response_id,
        "object": "realtime.session",
        "status": "active",
        "created_at": created_at,
        "expires_at": expires_at,
        "ttl_seconds": ttl_seconds,
    }


# ---------------------------------------------------------------------------
# Chat (legacy + streaming)
# ---------------------------------------------------------------------------

@router.post("/api/v1/chat")
async def chat_v1(request: Request):
    from providers import AIProviderManager
    body = await request.json()
    messages = body.get("messages", [])
    project_id = body.get("project_id")

    manager = AIProviderManager()
    result = await manager.generate(messages=messages, provider="mimo")

    # Persist to project if project_id provided
    if project_id:
        content = result.get("response", result.get("content", ""))
        now = datetime.now(timezone.utc).isoformat()
        conn = _db()
        c = conn.cursor()
        c.execute("SELECT COALESCE(MAX(sequence), 0) + 1 as next_seq FROM v1_messages WHERE project_id = ?", (project_id,))
        seq = c.fetchone()["next_seq"]
        msg_id = str(uuid.uuid4())
        c.execute("INSERT INTO v1_messages (id, project_id, sequence, version, role, content, status, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (msg_id, project_id, seq, 1, "assistant", content, "completed", "{}", now, now))
        c.execute("UPDATE v1_projects SET message_count = message_count + 1, last_message_at = ?, updated_at = ? WHERE id = ?",
                  (now, now, project_id))
        conn.commit()
        conn.close()

    return {
        "content": result.get("response", result.get("content", "")),
        "reasoning": result.get("reasoning"),
        "actions": [],
        "status": "completed",
    }


@router.post("/api/v1/chat/stream")
async def chat_stream_v1(request: Request, starting_after: int = 0):
    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    messages = _parse_response_input(body.get("messages", []))
    policy = body.get("policy")
    background = isinstance(policy, dict) and bool(policy.get("background"))
    background = background or bool(body.get("background"))
    model = body.get("model", "kolibri")
    provider = body.get("provider")
    idempotency_key = None
    idempotency_key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    project_id = body.get("project_id")

    if idempotency_key:
        existing = _get_response_id_by_idempotency(idempotency_key)
        if existing:
            async def resume_existing_stream():
                async for frame in _stream_response_events_from_db(existing, starting_after):
                    yield frame
                yield "data: [DONE]\n\n"
            return StreamingResponse(resume_existing_stream(), media_type="text/event-stream")

    response_id = _create_response_record(
        messages,
        project_id=project_id,
        model=model,
        provider=provider,
        background=background,
    )
    if idempotency_key:
        conn = _db()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO v1_response_idempotency (idempotency_key, response_id, created_at) VALUES (?, ?, ?)",
                (idempotency_key, response_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    if background:
        asyncio.create_task(_run_response_task(response_id, messages, model=model, provider=provider))
        async def stream_background():
            async for frame in _stream_response_events_from_db(response_id, 0, stop_after_nonterminal_event=True):
                yield frame
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream_background(), media_type="text/event-stream")

    await _run_response_task(response_id, messages, model=model, provider=provider)

    async def generate():
        async for frame in _stream_response_events_from_db(response_id, 0):
            yield frame
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Estimates, Documents, Library, Agents, Nodes, Tasks, Cluster, Factory, Responses
# ---------------------------------------------------------------------------

@router.get("/api/v1/estimates")
async def list_estimates(page: int = 1, page_size: int = 20, status: str = None, search: str = None):
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/api/v1/estimates/{estimate_id}")
async def get_estimate(estimate_id: str):
    raise HTTPException(status_code=404, detail="Estimate not found")


@router.post("/api/v1/estimates")
async def create_estimate(request: Request):
    body = await request.json()
    raw_estimate = body.get("estimate") if isinstance(body, dict) else None
    if isinstance(raw_estimate, dict):
        estimate = Estimate.model_validate(raw_estimate)
        workspace = _ESTIMATE_WORKSPACE_SERVICE.autosave(estimate)
        return {
            "object": "estimate.workspace",
            "id": estimate.estimate_id,
            "status": "draft",
            "version": workspace["version"],
            "estimate_id": estimate.estimate_id,
            "estimate": workspace["estimate"],
            "estimate_hash": workspace["estimate_hash"],
            "created_at": workspace["created_at"],
        }
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    return {"id": eid, "version": 1, "status": "draft", "title": body.get("title", "Новая смета"),
            "client": body.get("client", ""), "object_name": body.get("object_name", ""),
            "region": body.get("region", ""), "currency": body.get("currency", "RUB"),
            "overhead_rate": body.get("overhead_rate", "0"), "vat_rate": body.get("vat_rate", "20"),
            "subtotal": "0", "overhead_amount": "0", "vat_amount": "0", "total": "0",
            "sections": [], "created_at": now, "updated_at": now}


@router.put("/api/v1/estimates/{estimate_id}")
async def update_estimate(estimate_id: str, request: Request):
    return await get_estimate(estimate_id)


@router.delete("/api/v1/estimates/{estimate_id}")
async def delete_estimate(estimate_id: str):
    return {"deleted": True}


@router.post("/api/v1/estimates/{estimate_id}/calculate")
async def calculate_estimate(estimate_id: str):
    return await get_estimate(estimate_id)


@router.post("/api/v1/estimates/{estimate_id}/command")
async def estimate_command(estimate_id: str, request: Request):
    return {"applied": False, "message": "Command not implemented", "operations": [], "estimate": {}}


@router.post("/api/v1/estimates/{estimate_id}/duplicate")
async def duplicate_estimate(estimate_id: str):
    return await get_estimate(estimate_id)


@router.get("/api/v1/estimates/{estimate_id}/revisions")
async def list_revisions(estimate_id: str):
    return await list_estimate_versions(estimate_id)


@router.get("/api/v1/estimates/{estimate_id}/revisions/{version}")
async def get_revision(estimate_id: str, version: int):
    try:
        history = _ESTIMATE_WORKSPACE_SERVICE.get_version_history(estimate_id)["versions"]
    except EstimateWorkspaceMissing:
        raise HTTPException(status_code=404, detail="Estimate workspace not found")
    for item in history:
        if item["version"] == version:
            return {"item": item}
    raise HTTPException(status_code=404, detail="Revision not found")


@router.post("/api/v1/estimates/{estimate_id}/autosave")
async def autosave_estimate(estimate_id: str, request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid estimate payload")
    raw_estimate = body.get("estimate", body)
    if not isinstance(raw_estimate, dict):
        raise HTTPException(status_code=400, detail="Invalid estimate payload")
    estimate = Estimate.model_validate(raw_estimate)
    estimate.estimate_id = estimate_id
    workspace = _ESTIMATE_WORKSPACE_SERVICE.autosave(estimate)
    return {
        "object": "estimate.autosave",
        "estimate_id": estimate_id,
        "status": "draft",
        "version": workspace["version"],
        "estimate": workspace["estimate"],
        "estimate_hash": workspace["estimate_hash"],
        "created_at": workspace["created_at"],
    }


@router.post("/api/v1/estimates/{estimate_id}/publish")
async def publish_estimate(estimate_id: str, request: Request):
    body = await request.json()
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid publish payload")
    base_version = body.get("base_version")
    idempotency_key = body.get("idempotency_key")
    try:
        workspace = _ESTIMATE_WORKSPACE_SERVICE.publish(
            estimate_id,
            base_version=base_version,
            idempotency_key=idempotency_key,
        )
    except EstimateWorkspaceMissing:
        raise HTTPException(status_code=404, detail="Estimate workspace not found")
    except EstimatePublishValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except EstimateWorkspaceError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {
        "object": "estimate.publish",
        "estimate_id": estimate_id,
        "status": "approved",
        "version": workspace["version"],
        "estimate": workspace["estimate"],
        "estimate_hash": workspace["estimate_hash"],
        "created_at": workspace["created_at"],
    }


@router.get("/api/v1/estimates/{estimate_id}/lineage")
async def estimate_lineage(estimate_id: str):
    try:
        history = _ESTIMATE_WORKSPACE_SERVICE.get_version_history(estimate_id)
    except EstimateWorkspaceMissing:
        raise HTTPException(status_code=404, detail="Estimate workspace not found")

    source = history["versions"][0] if history["versions"] else history["draft"]
    if not source:
        raise HTTPException(status_code=404, detail="No estimate snapshot for lineage")

    estimate_payload = source.get("estimate", {})
    lineage_lines: list[dict[str, Any]] = []
    for section in estimate_payload.get("sections", []):
        section_title = section.get("title")
        for item in section.get("items", []):
            provenance = item.get("provenance", {}) or {}
            lineage_lines.append(
                {
                    "section": section_title,
                    "line_id": item.get("line_id"),
                    "item_type": item.get("item_type"),
                    "item": item.get("name"),
                    "source": provenance.get("source"),
                    "source_type": provenance.get("source_type"),
                    "source_region": provenance.get("region"),
                    "source_period": provenance.get("price_period"),
                    "source_label": provenance.get("label"),
                    "source_date": provenance.get("price_date") or provenance.get("captured_at"),
                    "source_confidence": provenance.get("confidence", "0"),
                    "status": "verified" if provenance.get("source_type") == "official_fgis" else "missing_evidence",
                }
            )
    return {"estimate_id": estimate_id, "version": source.get("version", 0), "lineage": lineage_lines}


@router.get("/api/v1/estimates/{estimate_id}/versions")
async def list_estimate_versions(estimate_id: str):
    try:
        return _ESTIMATE_WORKSPACE_SERVICE.get_version_history(estimate_id)
    except EstimateWorkspaceMissing:
        raise HTTPException(status_code=404, detail="Estimate workspace not found")


@router.get("/api/v1/estimates/{estimate_id}/export")
async def export_estimate(estimate_id: str):
    try:
        history = _ESTIMATE_WORKSPACE_SERVICE.get_version_history(estimate_id)
    except EstimateWorkspaceMissing:
        raise HTTPException(status_code=404, detail="Estimate workspace not found")

    source = history["versions"][0] if history["versions"] else history["draft"]
    if not source:
        raise HTTPException(status_code=404, detail="No estimate snapshot for export")
    return {
        "estimate_id": estimate_id,
        "version": source["version"],
        "estimate": source["estimate"],
    }


@router.post("/api/v1/estimates/{estimate_id}/import")
async def import_estimate(estimate_id: str, request: Request):
    body = await request.json()
    raw_estimate = body.get("estimate") if isinstance(body, dict) else None
    if not isinstance(raw_estimate, dict):
        raise HTTPException(status_code=400, detail="Invalid estimate import payload")
    try:
        estimate = Estimate.model_validate(raw_estimate)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid estimate payload: {exc}")
    target_id = body.get("estimate_id")
    if isinstance(target_id, str) and target_id.strip():
        estimate.estimate_id = target_id.strip()
    else:
        estimate.estimate_id = estimate_id
    workspace = _ESTIMATE_WORKSPACE_SERVICE.autosave(estimate)
    return {
        "object": "estimate.import",
        "estimate_id": estimate.estimate_id,
        "version": workspace["version"],
        "status": "draft",
        "estimate": workspace["estimate"],
    }


@router.post("/api/v1/estimates/{estimate_id}/scenarios")
async def reconcile_estimate_scenarios(estimate_id: str, request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid scenario payload")
    try:
        payload = EstimateScenarioRequest.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid scenario payload: {exc}")

    try:
        history = _ESTIMATE_WORKSPACE_SERVICE.get_version_history(estimate_id)
    except EstimateWorkspaceMissing:
        raise HTTPException(status_code=404, detail="Estimate workspace not found")

    source = history["draft"]
    if not source:
        raise HTTPException(status_code=404, detail="No estimate snapshot for scenario")

    scenarios = payload.scenarios
    if not scenarios:
        raise HTTPException(status_code=400, detail="Missing scenarios list")

    base_payload = deepcopy(source["estimate"])
    try:
        base_estimate = Estimate.model_validate(base_payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid source estimate payload: {exc}")

    base_total = base_estimate.totals.grand_total
    base_scope = _sum_scope(base_payload)

    projections = []
    for index, entry in enumerate(scenarios, start=1):
        label = str(entry.label or f"scenario-{index}")
        quantity_multiplier = entry.quantity_multiplier
        price_multiplier = entry.price_multiplier
        if quantity_multiplier <= 0:
            raise HTTPException(status_code=400, detail=f"Scenario {index}: quantity_multiplier must be greater than 0")
        if price_multiplier <= 0:
            raise HTTPException(status_code=400, detail=f"Scenario {index}: price_multiplier must be greater than 0")
        scenario_payload = deepcopy(base_payload)

        for section in scenario_payload.get("sections", []):
            for item in section.get("items", []):
                item["quantity"] = str(
                    (_as_decimal(item.get("quantity", 0), field_name="item quantity") * quantity_multiplier).quantize(
                        Decimal("0.0001")
                    )
                )
                if _as_decimal(item.get("material_unit_price", 0), field_name="material_unit_price") != Decimal("0"):
                    item["material_unit_price"] = str(
                        (_as_decimal(item.get("material_unit_price", 0), field_name="material_unit_price") * price_multiplier).quantize(
                            Decimal("0.01")
                        )
                    )
                if _as_decimal(item.get("labor_unit_price", 0), field_name="labor_unit_price") != Decimal("0"):
                    item["labor_unit_price"] = str(
                        (_as_decimal(item.get("labor_unit_price", 0), field_name="labor_unit_price") * price_multiplier).quantize(
                            Decimal("0.01")
                        )
                    )

        scenario_estimate = Estimate.model_validate(scenario_payload)
        scenario_estimate = recalculate_estimate(scenario_estimate)
        scenario_total = scenario_estimate.totals.grand_total
        scenario_scope = _sum_scope(scenario_payload)
        projections.append({
            "label": label,
            "quantity_multiplier": str(quantity_multiplier),
            "price_multiplier": str(price_multiplier),
            "estimate": scenario_estimate.model_dump(mode="json"),
            "delta_total": str(scenario_total - base_total),
            "delta_scope": str(scenario_scope - base_scope),
        })

    return {
        "estimate_id": estimate_id,
        "base_total": str(base_total),
        "scenarios": projections,
    }


@router.get("/api/v1/work-catalog")
async def list_work_catalog(search: str = "", page_size: int = 100):
    return {"items": [], "total": 0, "page": 1, "page_size": page_size}


@router.get("/api/v1/documents")
async def list_documents(page: int = 1, page_size: int = 20, type: str = None):
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/api/v1/documents/{doc_id}")
async def get_document(doc_id: str):
    raise HTTPException(status_code=404, detail="Document not found")


@router.post("/api/v1/documents")
async def create_document(request: Request):
    body = await request.json()
    did = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    return {"id": did, "title": body.get("title", ""), "type": body.get("type", "text"),
            "status": "draft", "client": body.get("client", ""), "project": body.get("project", ""),
            "content": body.get("content", ""), "variables": body.get("variables", {}),
            "template": body.get("template", ""), "estimate_id": body.get("estimate_id"),
            "created_at": now, "updated_at": now}


@router.post("/api/v1/documents/render")
async def create_document_render(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="request body must be an object")

    header_idempotency = request.headers.get("Idempotency-Key")
    body_idempotency = body.get("idempotency_key")
    if header_idempotency and body_idempotency and header_idempotency != body_idempotency:
        raise HTTPException(status_code=400, detail="Idempotency-Key header and idempotency_key body field differ")
    idempotency_key = header_idempotency or body_idempotency
    if idempotency_key:
        body["idempotency_key"] = idempotency_key
        existing = _get_render_job_by_idempotency_key(idempotency_key)
        if existing:
            return existing

    request_id = body.get("request_id")
    if request_id:
        existing = _get_render_job_by_request_id(request_id)
        if existing:
            existing_key = existing.get("idempotency_key")
            if idempotency_key and existing_key and existing_key != idempotency_key:
                raise HTTPException(status_code=409, detail="request_id already used with a different idempotency_key")
            return existing

    try:
        result = render_document_request(body)
    except RenderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="document render failed") from exc

    _upsert_render_job({
        "request_id": result["request_id"],
        "document_id": result["document_id"],
        "template_id": result["template_id"],
        "template_version": result["template_version"],
        "template_locale": result["rendered_locale"],
        "template_jurisdiction": result["rendered_jurisdiction"],
        "status": result["status"],
        "requested_outputs": result["requested_outputs"],
        "attempts": result["attempts"],
        "warnings": result["warnings"],
        "error": result.get("error"),
        "tenant_id": result.get("tenant_id"),
        "project_id": result.get("project_id"),
        "document_data_id": body.get("document_data", {}).get("document_data_id"),
        "idempotency_key": result.get("idempotency_key"),
        "assets": result["assets"],
    })

    return _get_render_job_by_request_id(result["request_id"])


@router.get("/api/v1/documents/render/{request_id}")
async def get_document_render(request_id: str):
    job = _get_render_job_by_request_id(request_id)
    if not job:
        raise HTTPException(status_code=404, detail="render job not found")
    return job


@router.get("/api/v1/documents/render/{request_id}/assets/{output_format}")
async def get_document_render_asset(request_id: str, output_format: str):
    output_format = output_format.lower().strip()
    if output_format not in _RENDER_OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail="unsupported output format")
    job = _get_render_job_by_request_id(request_id)
    if not job:
        raise HTTPException(status_code=404, detail="render job not found")
    path = _get_render_job_path(request_id, output_format)
    if not path:
        raise HTTPException(status_code=404, detail="asset not found")
    media_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(output_format, "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=f"{request_id}.{output_format}")


def _build_document_package_payload(
    render_job: dict[str, Any],
    selected_members: list[dict[str, Any]],
    package_id: str,
    now: str,
) -> dict[str, Any]:
    return {
        "schema_id": "kolibri.document_package",
        "schema_version": "1.0",
        "package_id": package_id,
        "request_id": render_job["request_id"],
        "document_id": render_job["document_id"],
        "template_id": render_job["template_id"],
        "template_version": render_job["template_version"],
        "template_locale": render_job["template_locale"],
        "template_jurisdiction": render_job["template_jurisdiction"],
        "tenant_id": render_job["tenant_id"],
        "project_id": render_job["project_id"],
        "document_data_id": render_job.get("document_data_id"),
        "package_status": "released",
        "member_versions": [
            {
                "kind": "document_render_asset",
                "request_id": render_job["request_id"],
                "format": member["format"],
                "content_hash": member["sha256"],
                "size_bytes": member.get("size_bytes", 0),
                "source_path": member["path"],
            }
            for member in selected_members
        ],
        "exact_inputs": {
            "template_id": render_job["template_id"],
            "template_version": render_job["template_version"],
            "template_locale": render_job["template_locale"],
            "template_jurisdiction": render_job["template_jurisdiction"],
            "document_data_id": render_job.get("document_data_id"),
        },
        "created_at": now,
        "created_by": "system-api",
        "manifest_version": 1,
    }


def _write_document_package_archive(
    package_id: str,
    selected_members: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> tuple[Path, str, int]:
    if not selected_members:
        raise HTTPException(status_code=400, detail="Cannot create package without members")

    DOCUMENT_PACKAGE_STORAGE.mkdir(parents=True, exist_ok=True)
    final_path = DOCUMENT_PACKAGE_STORAGE / f"{package_id}.zip"

    with tempfile.TemporaryDirectory(prefix=f"docpkg-{package_id}-", dir=str(DOCUMENT_PACKAGE_STORAGE)) as tmp_dir:
        staging_root = Path(tmp_dir)
        manifest_path = staging_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")

        archive_path = staging_root / f"{package_id}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(manifest_path, arcname="manifest.json")
            for member in selected_members:
                source_path = Path(member["path"])
                if not source_path.is_absolute():
                    raise HTTPException(status_code=500, detail=f"Invalid asset path for format={member['format']}")
                if not source_path.exists():
                    raise HTTPException(
                        status_code=409,
                        detail=f"Render asset missing while creating package: {source_path.name}",
                    )
                current_hash = _hash_file_sha256(source_path)
                if current_hash != member["sha256"]:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Render asset hash changed; package release blocked for format={member['format']}",
                    )
                zf.write(source_path, arcname=f"assets/{source_path.name}")

        archive_path.replace(final_path)

    if not final_path.exists():
        raise HTTPException(status_code=500, detail="Failed to build package")

    package_size = final_path.stat().st_size
    package_hash = _hash_file_sha256(final_path)
    return final_path, package_hash, package_size


def _upsert_document_package_record(
    package_id: str,
    request_id: str,
    manifest: dict[str, Any],
    package_path: Path,
    package_hash: str,
    size_bytes: int,
    created_outputs: list[str],
    idempotency_key: str | None,
    created_at: str | None = None,
) -> None:
    now = created_at or datetime.now(timezone.utc).isoformat()
    conn = _db()
    try:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO v1_document_packages (
                id, package_id, request_id, package_status, manifest_hash, idempotency_key,
                manifest_json, package_path, package_size_bytes, package_created_outputs, created_at, updated_at
            ) VALUES (
                :id, :package_id, :request_id, :package_status, :manifest_hash, :idempotency_key,
                :manifest_json, :package_path, :package_size_bytes, :package_created_outputs, :created_at, :created_at
            )
            ON CONFLICT(package_id) DO UPDATE SET
                request_id = excluded.request_id,
                package_status = excluded.package_status,
                manifest_hash = excluded.manifest_hash,
                idempotency_key = COALESCE(excluded.idempotency_key, v1_document_packages.idempotency_key),
                manifest_json = excluded.manifest_json,
                package_path = excluded.package_path,
                package_size_bytes = excluded.package_size_bytes,
                package_created_outputs = excluded.package_created_outputs,
                updated_at = excluded.updated_at
            """,
            {
                "id": package_id,
                "package_id": package_id,
                "request_id": request_id,
                "package_status": manifest.get("package_status"),
                "manifest_hash": package_hash,
                "idempotency_key": idempotency_key,
                "manifest_json": json.dumps(manifest, ensure_ascii=False, sort_keys=True),
                "package_path": str(package_path),
                "package_size_bytes": int(size_bytes),
                "package_created_outputs": json.dumps(sorted(set(created_outputs))),
                "created_at": now,
            },
        )
        conn.commit()
    finally:
        conn.close()


@router.post("/api/v1/documents/render/{request_id}/package")
async def create_document_render_package(request_id: str, request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid package body")

    request_id = request_id.strip()
    idempotency_key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    if idempotency_key:
        body["idempotency_key"] = idempotency_key

    existing_by_idempotency = _get_document_package_by_idempotency(request_id, idempotency_key)
    if existing_by_idempotency:
        return existing_by_idempotency

    render_job_row = _get_render_job_row_by_request_id(request_id)
    if not render_job_row:
        raise HTTPException(status_code=404, detail="render job not found")
    render_job = _serialize_render_job_row(render_job_row)
    if not render_job:
        raise HTTPException(status_code=404, detail="render job not found")

    if render_job.get("status") != "rendered":
        raise HTTPException(status_code=409, detail="Cannot create package: render job is not rendered")

    requested_outputs = body.get("asset_formats")
    if requested_outputs is not None:
        requested_outputs = _normalize_output_formats(requested_outputs)
    else:
        requested_outputs = render_job.get("requested_outputs", [])

    selected_members = _build_package_member_inventory(render_job_row, requested_outputs)
    if not selected_members:
        raise HTTPException(status_code=409, detail="Cannot create package: no valid members")

    package_id = _compute_package_id(render_job, selected_members)
    if existing := _get_document_package_by_id(package_id):
        return existing

    _build_and_store_document_package(
        request_id=request_id,
        render_job=render_job,
        selected_members=selected_members,
        idempotency_key=idempotency_key,
    )
    return _get_document_package_by_request_and_id(request_id, package_id)


@router.get("/api/v1/documents/render/{request_id}/packages/{package_id}")
async def get_document_render_package(request_id: str, package_id: str, request: Request):
    package = _get_document_package_by_request_and_id(request_id, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="document package not found")
    row = _get_document_package_row_by_request_and_id(request_id, package_id)
    if row:
        _assert_package_tenant_scope(request, row)
    return package


@router.get("/api/v1/documents/render/{request_id}/packages/{package_id}/download")
async def get_document_render_package_download(request_id: str, package_id: str, request: Request):
    row = _get_document_package_row_by_request_and_id(request_id, package_id)
    if not row:
        raise HTTPException(status_code=404, detail="document package not found")
    _assert_package_tenant_scope(request, row)
    package_path = Path(row["package_path"])
    if not package_path.is_absolute():
        raise HTTPException(status_code=500, detail="Invalid package path")
    if not package_path.exists():
        raise HTTPException(status_code=404, detail="document package file not found")

    current_hash = _hash_file_sha256(package_path)
    if current_hash != row["manifest_hash"]:
        raise HTTPException(status_code=409, detail="document package integrity check failed")

    return FileResponse(
        package_path,
        media_type="application/zip",
        filename=f"{request_id}-{package_id}.zip",
    )


@router.get("/api/v1/documents/render/{request_id}/packages/{package_id}/preview")
async def get_document_render_package_preview(request_id: str, package_id: str, request: Request):
    row = _get_document_package_row_by_request_and_id(request_id, package_id)
    if not row:
        raise HTTPException(status_code=404, detail="document package not found")
    _assert_package_tenant_scope(request, row)
    return {
        "object": "document_package_preview",
        "request_id": row["request_id"],
        "package_id": row["package_id"],
        "manifest_hash": row["manifest_hash"],
        "manifest": _safe_json_loads(row["manifest_json"], default={}),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "download_url": f"/api/v1/documents/render/{row['request_id']}/packages/{row['package_id']}/download",
    }


@router.get("/api/v1/documents/render/{request_id}/packages/{package_id}/assets/{output_format}")
async def get_document_render_package_asset(request_id: str, package_id: str, output_format: str, request: Request):
    output_format = output_format.lower().strip()
    if output_format not in _RENDER_OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail="unsupported output format")

    row = _get_document_package_row_by_request_and_id(request_id, package_id)
    if not row:
        raise HTTPException(status_code=404, detail="document package not found")
    _assert_package_tenant_scope(request, row)

    manifest = _safe_json_loads(row["manifest_json"], default={})
    member_versions = manifest.get("member_versions", [])
    if not isinstance(member_versions, list):
        raise HTTPException(status_code=500, detail="Malformed package manifest")

    matched_member = None
    for member in member_versions:
        if not isinstance(member, dict):
            continue
        if member.get("kind") != "document_render_asset":
            continue
        if str(member.get("format", "")).lower() == output_format:
            matched_member = member
            break
    if not matched_member:
        raise HTTPException(status_code=404, detail="package asset not found")

    source_path = matched_member.get("source_path")
    if not isinstance(source_path, str):
        raise HTTPException(status_code=500, detail="Malformed package manifest")
    path = Path(source_path)
    if not path.is_absolute():
        raise HTTPException(status_code=500, detail="Invalid package asset path")
    if not path.exists():
        raise HTTPException(status_code=404, detail="package asset file not found")
    expected_hash = _normalize_asset_hash(matched_member.get("content_hash"))
    if expected_hash and _hash_file_sha256(path) != expected_hash:
        raise HTTPException(status_code=409, detail="package asset integrity check failed")

    media_type = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }.get(output_format, "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.post("/api/v1/documents/render/{request_id}/packages/{package_id}/regenerate")
async def regenerate_document_render_package(request_id: str, package_id: str, request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    if body is None:
        body = {}
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Invalid regenerate body")

    header_idempotency = request.headers.get("Idempotency-Key")
    body_idempotency = body.get("idempotency_key")
    if header_idempotency and body_idempotency and header_idempotency != body_idempotency:
        raise HTTPException(status_code=400, detail="Idempotency-Key header and idempotency_key body field differ")
    idempotency_key = header_idempotency or body_idempotency

    existing_row = _get_document_package_row_by_request_and_id(request_id, package_id)
    if not existing_row:
        raise HTTPException(status_code=404, detail="document package not found")
    _assert_package_tenant_scope(request, existing_row)

    render_job_row = _get_render_job_row_by_request_id(request_id)
    if not render_job_row:
        raise HTTPException(status_code=404, detail="render job not found")
    render_job = _serialize_render_job_row(render_job_row)
    if not render_job:
        raise HTTPException(status_code=404, detail="render job not found")
    if render_job.get("status") != "rendered":
        raise HTTPException(status_code=409, detail="Cannot regenerate package: render job is not rendered")

    requested_outputs = body.get("asset_formats")
    if requested_outputs is not None:
        requested_outputs = _normalize_output_formats(requested_outputs)
    else:
        existing_outputs = _safe_json_loads(existing_row["package_created_outputs"], default=render_job.get("requested_outputs", []))
        requested_outputs = existing_outputs

    selected_members = _build_package_member_inventory(render_job_row, requested_outputs)
    if not selected_members:
        raise HTTPException(status_code=409, detail="Cannot regenerate package: no valid members")

    rebuilt_package_id, rebuilt_manifest = _build_and_store_document_package(
        request_id=request_id,
        render_job=render_job,
        selected_members=selected_members,
        idempotency_key=(idempotency_key or existing_row["idempotency_key"]),
        created_at=existing_row["created_at"],
    )
    rebuilt_package = _get_document_package_by_request_and_id(request_id, rebuilt_package_id)
    if not rebuilt_package:
        raise HTTPException(status_code=500, detail="Cannot load regenerated document package")

    previous_manifest = _safe_json_loads(existing_row["manifest_json"], default=None)
    changed = (
        rebuilt_package_id != package_id
        or previous_manifest != rebuilt_manifest
    )
    return {
        "changed": changed,
        **rebuilt_package,
    }


@router.put("/api/v1/documents/{doc_id}")
async def update_document(doc_id: str, request: Request):
    return await get_document(doc_id)


@router.delete("/api/v1/documents/{doc_id}")
async def delete_document(doc_id: str):
    return {"deleted": True}


@router.get("/api/v1/library")
async def list_library(page: int = 1, page_size: int = 20, item_type: str = None, search: str = None):
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/api/v1/agents")
async def list_agents(page: int = 1, page_size: int = 20, status: str = None):
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/api/v1/agents/{agent_id}")
async def get_agent(agent_id: str):
    raise HTTPException(status_code=404, detail="Agent not found")


@router.post("/api/v1/agents")
async def create_agent(request: Request):
    body = await request.json()
    return {"id": str(uuid.uuid4()), "name": body.get("name", ""), "role": body.get("role", ""),
            "status": "idle", "node_id": None, "current_task": None, "progress": None,
            "model": body.get("model"), "connection": {}, "freshness": {}, "execution": {},
            "verification": {}, "capabilities": {}, "cost_accumulated": "0",
            "heartbeat_at": None}


@router.get("/api/v1/nodes")
async def list_nodes(page: int = 1, page_size: int = 20, status: str = None):
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/api/v1/tasks")
async def list_tasks(page: int = 1, page_size: int = 20, state: str = None):
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


@router.get("/api/v1/cluster/stats")
async def cluster_stats():
    return {"nodes": {"membership_total": 0, "connected": 0, "fresh": 0, "capability_executable": 0,
                       "active": 0, "verified": 0, "blocked": 0, "quarantined": 0, "stale": 0},
            "agents": {"membership_total": 0, "active": 0, "idle": 0, "paused": 0, "executable": 0, "verified": 0},
            "tasks": {"total": 0, "running": 0, "queued": 0, "completed": 0, "failed": 0, "cancelled": 0},
            "resources": {"avg_cpu": None, "avg_ram": None, "avg_disk": None},
            "truth": {"availability": "unavailable", "source": "local", "as_of": datetime.now(timezone.utc).isoformat(), "task_pages": 0}}


@router.get("/api/v1/control/models")
async def control_models():
    return {"public_model": "mimo-auto", "routes": [], "routing_status": "ok",
            "as_of": datetime.now(timezone.utc).isoformat(), "source": "local"}


@router.get("/api/v1/control/local-models")
async def control_local_models():
    return {"items": [], "admitted_total": 0, "candidate_total": 0,
            "as_of": datetime.now(timezone.utc).isoformat(), "source": "local"}


@router.get("/api/v1/control/learning")
async def control_learning():
    return {"status": "idle", "mode": "off", "candidate_only": False,
            "active_model": None, "candidate_model": None, "gates": [], "candidates": [],
            "as_of": datetime.now(timezone.utc).isoformat(), "source": "local"}


@router.get("/api/v1/control/tasks/summary")
async def control_tasks_summary():
    return {"total": 0, "queued": 0, "running": 0, "waiting_review": 0,
            "completed": 0, "failed": 0, "cancelled": 0, "dead_letter": 0,
            "as_of": datetime.now(timezone.utc).isoformat()}


@router.get("/api/v1/control/events")
async def control_events(task_id: str = None, cursor: str = None, limit: int = 50):
    return {"items": [], "total": 0, "next_cursor": None,
            "as_of": datetime.now(timezone.utc).isoformat(), "source": "local"}


@router.post("/v1/responses")
@router.post("/api/v1/responses")
async def create_response(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    input_data = body.get("input")
    policy = body.get("policy")
    background = isinstance(policy, dict) and bool(policy.get("background"))
    background = background or bool(body.get("background"))
    project_id = body.get("project_id")
    provider = body.get("provider")
    model = body.get("model", "kolibri")
    idempotency_key = request.headers.get("Idempotency-Key") or body.get("idempotency_key")

    messages = _parse_response_input(input_data)
    if idempotency_key:
        existing = _get_response_id_by_idempotency(idempotency_key)
        if existing:
            row = _get_response_row(existing)
            if row:
                return _response_payload_from_row(row)

    response_id = _create_response_record(
        messages,
        project_id=project_id,
        model=model,
        provider=provider,
        background=background,
    )
    if idempotency_key:
        conn = _db()
        try:
            c = conn.cursor()
            c.execute(
                "INSERT OR REPLACE INTO v1_response_idempotency (idempotency_key, response_id, created_at) VALUES (?, ?, ?)",
                (idempotency_key, response_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            conn.close()

    if background:
        asyncio.create_task(_run_response_task(response_id, messages, model=model, provider=provider))
        row = _get_response_row(response_id)
        return _response_payload_from_row(row)

    await _run_response_task(response_id, messages, model=model, provider=provider)
    return _response_payload_from_row(_get_response_row(response_id))


@router.get("/v1/responses/{response_id}")
@router.get("/api/v1/responses/{response_id}")
async def get_response(response_id: str):
    row = _get_response_row(response_id)
    if not row:
        raise HTTPException(status_code=404, detail="Response not found")
    return _response_payload_from_row(row)


@router.get("/v1/responses/{response_id}/events")
@router.get("/api/v1/responses/{response_id}/events")
async def response_events(response_id: str, starting_after: int = 0):
    if not _ensure_response_exists(response_id):
        raise HTTPException(status_code=404, detail="Response not found")

    async def generate():
        async for frame in _stream_response_events_from_db(response_id, starting_after):
            yield frame
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/v1/responses/{response_id}/cancel")
@router.post("/api/v1/responses/{response_id}/cancel")
async def cancel_response(response_id: str):
    conn = _db()
    c = conn.cursor()
    c.execute("SELECT status FROM v1_response_runs WHERE id = ?", (response_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Response not found")
    if row[0] in {"completed", "failed", "cancelled"}:
        conn.close()
        row = _get_response_row(response_id)
        return _response_payload_from_row(row)
    conn.close()
    _append_response_event(response_id, "response.cancelled", {
        "response": {"id": response_id, "status": "cancelled"},
        "status": "cancelled",
    }, status="cancelled")
    return _response_payload_from_row(_get_response_row(response_id))


@router.get("/api/v1/ai/models")
async def get_models():
    from providers import AIProviderManager
    manager = AIProviderManager()
    return {"models": manager.get_model_catalog(), "system_prompt": manager.get_system_prompt()}

@router.get("/api/v1/model/stats")
async def get_model_stats():
    return {"status": "ok", "models": ["mimo-auto"], "active": "mimo-auto"}

@router.post("/api/v1/ai/chat")
async def chat(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    provider = body.get("provider") or None
    model = body.get("model", "auto")
    result = await manager.generate(messages=messages, model=model, provider=provider)
    return result

@router.post("/api/v1/ai/chat/stream")
async def chat_stream(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    provider = body.get("provider") or None
    model = body.get("model", "auto")
    result = await manager.generate(messages=messages, model=model, provider=provider)
    async def generate():
        yield f"data: {json.dumps(result)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("/api/v1/ai/imagine")
async def imagine():
    return {"status": "ok", "message": "Image generation coming soon"}

@router.post("/api/v1/ai/vision/analyze")
async def vision():
    return {"status": "ok", "message": "Vision analysis coming soon"}

@router.post("/api/v1/ai/demo/learn/text")
async def learn():
    return {"status": "ok", "message": "Learning coming soon"}

@router.get("/api/v1/ai/quality/benchmark/history")
async def benchmark():
    return {"history": []}

@router.get("/api/v1/swarm/runtime/status")
async def swarm_status():
    return {"status": "active", "nodes": 4}

@router.get("/api/v1/ai/training/queue/status")
async def training_status():
    return {"queue": []}

@router.post("/api/v1/swarm/runtime/start")
async def swarm_start():
    return {"status": "started"}

@router.post("/api/v1/swarm/runtime/refresh")
async def swarm_refresh():
    return {"status": "refreshed"}

@router.post("/api/v1/swarm/runtime/run")
async def swarm_run():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/text")
async def ingest_text():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/url")
async def ingest_url():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/export")
async def kpack_export():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/import")
async def kpack_import():
    return {"status": "ok"}
