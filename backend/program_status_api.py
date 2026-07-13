"""Owner-only read projection for the Home-first Program Ledger.

The tracked JSON document is a compatibility source until PostgreSQL owns the
Program Ledger.  This router never invents runtime values: a missing, malformed,
future-dated, or secret-bearing document is an explicit unavailable response.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from execution_api import require_execution_auth


PROGRAM_STATUS_SCHEMA = "kolibri.program-status.v1"
WALLBOARD_STATUS_SCHEMA = "kolibri.wallboard.program-status.v1"
PROGRAM_STATUS_PATH_ENV = "KOLIBRI_PROGRAM_STATUS_PATH"
PROGRAM_STATUS_MAX_AGE_ENV = "KOLIBRI_PROGRAM_STATUS_MAX_AGE_SECONDS"
DEFAULT_MAX_AGE_SECONDS = 900
MAX_STATUS_BYTES = 1_048_576
_SENSITIVE_KEYS = {
    "access_token", "api_key", "authorization", "cookie", "password",
    "private_key", "raw_secret", "refresh_token", "secret", "session_cookie",
}
_SENSITIVE_SUFFIXES = (
    "_access_token", "_api_key", "_authorization", "_cookie", "_password",
    "_private_key", "_raw_secret", "_refresh_token", "_session_cookie",
)

router = APIRouter(tags=["wallboard"])


class ProgramStatusUnavailable(RuntimeError):
    """Safe unavailable reason for the owner wallboard projection."""


def _default_program_status_path() -> Path:
    return Path(__file__).resolve().parents[1] / "release" / "program-status.json"


def _program_status_path() -> Path:
    configured = os.environ.get(PROGRAM_STATUS_PATH_ENV, "").strip()
    return Path(configured).expanduser() if configured else _default_program_status_path()


def _max_age_seconds() -> int:
    raw = os.environ.get(PROGRAM_STATUS_MAX_AGE_ENV, str(DEFAULT_MAX_AGE_SECONDS))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ProgramStatusUnavailable("program_status_max_age_invalid") from exc
    if value < 30 or value > 86_400:
        raise ProgramStatusUnavailable("program_status_max_age_invalid")
    return value


def _contains_sensitive_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES):
                return True
            if _contains_sensitive_key(child):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_sensitive_key(child) for child in value)
    return False


def _parse_utc(value: Any, *, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ProgramStatusUnavailable(f"{field}_invalid")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ProgramStatusUnavailable(f"{field}_invalid") from exc
    return parsed.astimezone(timezone.utc)


def _validated_gate_progress(program: dict[str, Any]) -> dict[str, Any]:
    summary = program.get("summary")
    progress = summary.get("acceptance_gate_progress") if isinstance(summary, dict) else None
    if not isinstance(progress, dict):
        raise ProgramStatusUnavailable("program_status_gate_progress_missing")
    required_counts = ("completed", "in_progress", "blocked", "not_started", "total")
    if any(not isinstance(progress.get(key), int) or progress[key] < 0 for key in required_counts):
        raise ProgramStatusUnavailable("program_status_gate_progress_invalid")
    if sum(progress[key] for key in required_counts[:-1]) != progress["total"]:
        raise ProgramStatusUnavailable("program_status_gate_progress_invalid")
    ratio = progress.get("completed_ratio")
    if not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
        raise ProgramStatusUnavailable("program_status_gate_progress_invalid")
    return progress


def load_program_status_projection(
    *,
    path: Path | None = None,
    observed_at: datetime | None = None,
) -> tuple[dict[str, Any], str]:
    source = path or _program_status_path()
    if source.is_symlink() or not source.is_file():
        raise ProgramStatusUnavailable("program_status_source_unavailable")
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise ProgramStatusUnavailable("program_status_source_unavailable") from exc
    if not raw or len(raw) > MAX_STATUS_BYTES:
        raise ProgramStatusUnavailable("program_status_source_invalid")
    try:
        program = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProgramStatusUnavailable("program_status_source_invalid") from exc
    if not isinstance(program, dict) or program.get("schema_version") != PROGRAM_STATUS_SCHEMA:
        raise ProgramStatusUnavailable("program_status_schema_invalid")
    if _contains_sensitive_key(program):
        raise ProgramStatusUnavailable("program_status_sensitive_data_rejected")

    gates = program.get("gates")
    evidence = program.get("evidence")
    if not isinstance(gates, list) or not isinstance(evidence, list):
        raise ProgramStatusUnavailable("program_status_contract_invalid")
    progress = _validated_gate_progress(program)
    as_of = _parse_utc(program.get("as_of"), field="program_status_as_of")
    now = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_seconds = int((now - as_of).total_seconds())
    if age_seconds < -300:
        raise ProgramStatusUnavailable("program_status_timestamp_future")
    age_seconds = max(0, age_seconds)
    freshness = "stale" if age_seconds > _max_age_seconds() else "live"
    partial = program.get("overall_status") != "completed" or any(
        isinstance(item, dict) and item.get("status") == "partial" for item in evidence
    )
    availability = "stale" if freshness == "stale" else "partial" if partial else "live"
    digest = hashlib.sha256(raw).hexdigest()
    projection = {
        "schema_version": WALLBOARD_STATUS_SCHEMA,
        "availability": availability,
        "source_freshness": freshness,
        "source": "program-ledger/home",
        "as_of": program["as_of"],
        "observed_at": now.isoformat().replace("+00:00", "Z"),
        "age_seconds": age_seconds,
        "source_sha256": f"sha256:{digest}",
        "source_commit": program.get("source_commit"),
        "overall_status": program.get("overall_status"),
        "gate_progress": progress,
        "gates": gates,
        "evidence": evidence,
        "summary": program.get("summary"),
    }
    return projection, digest


def _unavailable(reason: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "schema_version": WALLBOARD_STATUS_SCHEMA,
            "availability": "unavailable",
            "source_freshness": "unavailable",
            "source": "program-ledger/home",
            "reason": reason,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/v1/program/status", dependencies=[Depends(require_execution_auth)])
async def program_status(request: Request) -> Response:
    try:
        projection, digest = load_program_status_projection()
    except ProgramStatusUnavailable as exc:
        return _unavailable(str(exc))
    etag = f'"{digest}"'
    headers = {"Cache-Control": "no-store", "ETag": etag}
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=projection, headers=headers)
