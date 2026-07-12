"""Scoped browser access to the canonical OpenAI-compatible Responses API.

Owner API keys continue to use the durable execution store.  A browser gets a
short-lived, same-origin, HttpOnly session which can see only its own ephemeral
project and responses.  Session tokens are opaque and only their SHA-256 hash
is persisted.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from capability_gateway import CapabilityRequestError, get_capability_gateway
from data_paths import DB_PATH
from estimate_artifacts import EstimateArtifactError, materialize_public_estimate_task
from image_artifacts import ImageArtifactError, get_public_image_artifact_store
from execution_api import (
    ProjectCreate,
    ResponseCreate,
    cancel_response as cancel_owner_response,
    create_project as create_owner_project,
    create_response as create_owner_response,
    get_project as get_owner_project,
    get_learning_boundary,
    get_response as get_owner_response,
    list_projects as list_owner_projects,
    list_response_events as list_owner_response_events,
    list_response_input_items as list_owner_response_input_items,
    list_responses as list_owner_responses,
    require_execution_auth,
    sanitize_learning_value,
)
from formulalm_boundary import (
    FormulaLMConflictError,
    FormulaLMPolicyError,
    scan_learning_payload,
)
from openai_compatibility import response_input_item_list
from public_chat_stream import PublicChatStreamError, verified_public_payload
from public_errors import (
    public_execution_failure,
    public_provider_failure,
    public_verification_failure,
)
from product_capabilities import (
    build_product_capability_matrix,
    requested_materialized_capability,
    verified_provider_health,
)
from provider_gateway import deterministic_verifier_evidence, get_provider_gateway
from providers import ProviderGatewayError
from response_tool_gateway import ResponseToolExecution, execute_response_tools
from sqlite_lifecycle import closing_sqlite_transaction
from vertical_tasks import (
    EstimateVerticalTask,
    ImageVerticalTask,
    build_deterministic_estimate_fallback,
    build_vertical_result,
    deterministic_estimate_fallback_text,
    deterministic_estimate_fallback_verification,
    deterministic_estimate_result_text,
    deterministic_estimate_result_verification,
    estimate_product_outcome,
    failed_vertical_result,
    prepare_vertical_task,
)
from web_search_gateway import TOOL_ID as WEB_SEARCH_TOOL_ID
from web_search_gateway import (
    WebSearchError,
    WebSearchPolicyError,
    get_web_search_gateway,
)
from work_summary import (
    build_work_summary,
    reasoning_output_item,
    summary_from_metadata,
    summary_metadata,
)


COOKIE_NAME = "kolibri_public_session"
MAX_REQUEST_BYTES = 1024 * 1024
MAX_MESSAGES = 100
MAX_SESSION_COOKIE_CANDIDATES = 8
ESTIMATE_PROVIDER_TOTAL_BUDGET_SECONDS = 85.0
ESTIMATE_PROVIDER_INITIAL_BUDGET_SECONDS = 55.0
ESTIMATE_PROVIDER_REPAIR_BUDGET_SECONDS = 25.0
_ESTIMATE_REPAIRABLE_VALIDATION_CODES = frozenset({
    "response_json_invalid",
    "multiple_json_objects",
    "response_too_large",
    "schema_version_missing",
    "schema_version_invalid",
    "decline_contract_invalid",
    "schema_validation_failed",
    "sections_invalid",
    "normative_basis_invalid",
    "price_provenance_invalid",
    "quantity_provenance_invalid",
    "price_evidence_invalid",
    "unit_invalid",
    "estimate_spec_invalid",
})
PUBLIC_TOOL_ALIASES = frozenset({
    WEB_SEARCH_TOOL_ID, "web_search", "web_search_preview", "search_web",
})
_CANONICAL_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_PUBLIC_SESSION_TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


def _now() -> float:
    return time.time()


def _opaque_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _provider_routing(value: Any) -> dict[str, Any]:
    """Return the internal routing envelope without ever exposing it publicly."""

    if not isinstance(value, dict):
        return {}
    technical = value.get("technical")
    if isinstance(technical, dict) and isinstance(technical.get("provider_routing"), dict):
        return technical["provider_routing"]
    return value if any(key in value for key in ("attempts", "evidence", "error_type")) else {}


def _image_factory_provider_result(
    *,
    completion: Any,
    artifact: dict[str, Any],
    materialization: dict[str, Any],
) -> dict[str, Any]:
    """Bind a truthful caption to one verified, persisted image artifact."""

    caption = "Изображение создано и готово к просмотру."
    encoded = caption.encode("utf-8")
    provider_evidence = {
        "type": "provider_execution",
        "provider": "factory",
        "provider_model": "image_generation",
        "route_transport": "home_control_plane",
        "exit_code": 0,
        "output_sha256": hashlib.sha256(encoded).hexdigest(),
        "output_bytes": len(encoded),
        "completion_signal": "fenced_verified_image_artifact",
        "factory_binding_sha256": completion.factory_binding_sha256,
    }
    verifier = deterministic_verifier_evidence(
        caption,
        provider_evidence,
        [],
        [],
        artifact_refs=[artifact],
    )
    if verifier.get("verdict") != "passed":
        raise ImageArtifactError("image_public_verifier_failed")
    return {
        "status": "success",
        "model": "kolibri",
        "response": caption,
        "technical": {
            "provider_routing": {
                "selected_provider": "factory",
                "attempts": [{
                    "status": "succeeded",
                    "task_id": str(completion.technical.get("task_id") or ""),
                    "attempt_id": str(completion.technical.get("attempt_id") or ""),
                }],
                "artifact_refs": [artifact],
                "evidence": [provider_evidence, materialization, verifier],
                "verifier_evidence": verifier,
            },
        },
    }


def _native_web_search_binding(routing: dict[str, Any]) -> dict[str, Any] | None:
    tool_calls = routing.get("tool_calls") if isinstance(routing.get("tool_calls"), list) else []
    web_calls = [
        item for item in tool_calls
        if isinstance(item, dict)
        and item.get("status") == "succeeded"
        and str(item.get("tool") or item.get("capability_id") or "") in {
            "web_search", WEB_SEARCH_TOOL_ID,
        }
        and isinstance(item.get("call_id"), str)
        and item.get("call_id")
    ]
    verifier = routing.get("verifier_evidence")
    if not isinstance(verifier, dict):
        verifier = next((
            item for item in routing.get("evidence", [])
            if isinstance(item, dict) and item.get("type") == "deterministic_verifier"
        ), None)
    verified_ids = set(verifier.get("verified_tool_call_ids") or []) if isinstance(verifier, dict) else set()
    call_ids = sorted({str(item["call_id"]) for item in web_calls})
    if not (
        isinstance(verifier, dict)
        and verifier.get("verdict") == "passed"
        and _CANONICAL_SHA256.fullmatch(str(verifier.get("binding_sha256") or "").lower())
        and call_ids
        and set(call_ids).issubset(verified_ids)
    ):
        return None
    return {
        "schema_version": "kolibri.native-web-search-binding.v1",
        "tool_id": WEB_SEARCH_TOOL_ID,
        "tool_call_ids": call_ids,
        "verifier_binding_sha256": str(verifier["binding_sha256"]).lower(),
        "source_claim": "provider_asserted_unverified",
    }


def _estimate_source_contract(
    *,
    routing: dict[str, Any],
    tool_execution: ResponseToolExecution,
) -> dict[str, Any]:
    if tool_execution.citations:
        return {
            "estimate_source_mode": "controlled_search",
            "source_evidence": tool_execution.citations,
        }
    if tool_execution.provider_tools:
        validator = getattr(get_web_search_gateway(), "_canonical_citation_url", None)
        return {
            "estimate_source_mode": "provider_asserted",
            "source_evidence": [],
            "native_tool_binding": _native_web_search_binding(routing),
            "citation_url_validator": validator if callable(validator) else None,
        }
    # A typed price request never silently drops to model-memory prices.
    return {"estimate_source_mode": "controlled_search", "source_evidence": []}


def _provider_asserted_public_citations(task: dict[str, Any]) -> list[dict[str, Any]]:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    research = result.get("price_research") if isinstance(result.get("price_research"), dict) else {}
    binding = research.get("native_tool_binding") if isinstance(research.get("native_tool_binding"), dict) else {}
    if research.get("status") != "provider_asserted_unverified" or not binding:
        return []
    citations: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in research.get("lines", []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("source_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        citations.append({
            "id": f"cite_{len(citations) + 1}",
            "title": str(item.get("source_title") or "Source")[:200],
            "snippet": str(item.get("source_snippet") or item.get("source_quote") or "")[:1_000],
            "url": url,
            "source_host": str(item.get("source_host") or "")[:253],
            "provider": "native-web-search-provider-assertion",
            "retrieved_at": str(item.get("source_retrieved_at") or "")[:80],
            "content_sha256": str(item.get("source_content_sha256") or "").lower(),
            "verification_status": "provider_asserted_unverified",
            "tool_call_ids": list(binding.get("tool_call_ids") or []),
            "tool_verifier_binding_sha256": binding.get("verifier_binding_sha256"),
        })
    return citations


def _sha256_artifact_hashes(*values: Any) -> list[str]:
    """Collect only canonical content digests from already bounded evidence."""

    found: set[str] = set()

    def walk(value: Any, *, key: str = "", depth: int = 0) -> None:
        if depth > 12:
            return
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, key=str(child_key).lower(), depth=depth + 1)
            return
        if isinstance(value, (list, tuple)):
            for child in value:
                walk(child, key=key, depth=depth + 1)
            return
        if not isinstance(value, str):
            return
        digest = value.lower().removeprefix("sha256:")
        if (
            _CANONICAL_SHA256.fullmatch(digest)
            and any(marker in key for marker in ("sha256", "digest", "content_hash"))
            and not any(marker in key for marker in ("binding", "idempotency", "authorization"))
        ):
            found.add(f"sha256:{digest}")

    for item in values:
        walk(item)
    return sorted(found)


def _record_public_learning_tap(
    *,
    session: dict[str, Any],
    body: ResponseCreate,
    response_id: str,
    response_status: str,
    response_text: str,
    verification: dict[str, Any] | None,
    provider_routing: dict[str, Any] | None,
    tool_execution: ResponseToolExecution,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a candidate-only FormulaLM tap isolated from public execution.

    Raw session identifiers never cross the learning boundary.  The trace binds
    the exact ephemeral response, session, project and provider/tool attempt
    evidence by hashes.  ``enqueue_trace`` performs the strict secret/PII scan
    and stores no trace content when consent, licence, retention or quality
    policy rejects it.  It cannot train, create a candidate or promote weights
    in the request path.
    """

    session_sha256 = _sha256(str(session["id"]))
    project_sha256 = _sha256(str(session["project_id"]))
    routing = provider_routing if isinstance(provider_routing, dict) else {}
    attempts = routing.get("attempts") if isinstance(routing.get("attempts"), list) else []
    evidence = routing.get("evidence") if isinstance(routing.get("evidence"), list) else []
    tool_attempts = list(tool_execution.attempts)
    tool_calls = list(tool_execution.tool_calls)
    formula_tool_taps = list(tool_execution.formulalm_taps)
    verification = verification if isinstance(verification, dict) else {}
    attempt_binding = {
        "schema_version": "kolibri.public-learning-binding.v1",
        "response_id": response_id,
        "public_session_sha256": session_sha256,
        "project_sha256": project_sha256,
        "execution_mode": body.execution_mode,
        "provider_attempts": attempts,
        "provider_evidence": evidence,
        "tool_attempts": tool_attempts,
        "tool_calls": tool_calls,
        "verification": verification,
    }
    # Hash sanitized structures so even a malicious provider error cannot turn
    # a secret or PII value into a durable/public correlation oracle.  The raw
    # trace still goes to ``enqueue_trace`` so its scanner rejects the intake.
    attempt_binding_sha256 = _json_hash(scan_learning_payload(attempt_binding).sanitized)
    trace = {
        "request": {
            "input": body.input,
            "instructions": body.instructions,
            "tools": body.tools,
        },
        "response": {
            "status": response_status,
            "output_text": response_text if response_status == "completed" else "",
            "task": task,
        },
        "decisions": {
            "selected_provider": routing.get("selected_provider"),
            "fallback_used": routing.get("fallback_used"),
            "provider_attempts": attempts,
            "tool_attempts": tool_attempts,
            "tool_calls": tool_calls,
            "formulalm_tool_taps": formula_tool_taps,
        },
        "binding": {
            "response_id": response_id,
            "public_session_sha256": session_sha256,
            "project_sha256": project_sha256,
            "attempt_evidence_sha256": attempt_binding_sha256,
            "verification": verification,
        },
    }
    content_sha256 = _json_hash(scan_learning_payload(trace).sanitized)
    passed = response_status == "completed" and verification.get("status") == "passed"
    verification_type = str(verification.get("type") or "provider_response")
    deterministic_engine_passed = passed and verification_type == "deterministic_estimate_engine"
    provider_passed = passed and not deterministic_engine_passed
    quality = {
        "response_status": response_status,
        "quality_verdict": "passed" if passed else "failed",
        "verifier_verdict": "passed" if passed else "failed",
        "credit_assignment": {
            "provider_execution": 1.0 if provider_passed and evidence else 0.0,
            "deterministic_estimate_engine": 1.0 if deterministic_engine_passed else 0.0,
            "tool_execution": 1.0 if provider_passed and tool_calls else 0.0,
            "verifier": 1.0 if passed else 0.0,
        },
    }
    policy = body.learning.model_dump(mode="json")
    artifact_hashes = _sha256_artifact_hashes(evidence, tool_execution.evidence, task)
    base = {
        "content_sha256": content_sha256,
        "attempt_evidence_sha256": attempt_binding_sha256,
        "candidate_only": True,
        "async_queue": False,
        "auto_promote": False,
        "request_path_training": False,
        "production_weight_mutation": False,
    }
    try:
        intake = get_learning_boundary().enqueue_trace(
            idempotency_key=f"public-trace:{response_id}",
            source_trace_id=response_id,
            source_response_id=response_id,
            capability=policy["capability"],
            trace=trace,
            provenance={
                "actor": (
                    "public-deterministic-estimate-engine"
                    if deterministic_engine_passed
                    else "public-provider-gateway"
                ),
                "principal": f"public-session:{session_sha256[:16]}",
                "policy_version": "kolibri.formulalm-public-policy.v1",
                "response_id": response_id,
                "public_session_sha256": session_sha256,
                "project_sha256": project_sha256,
                "attempt_evidence_sha256": attempt_binding_sha256,
            },
            policy=policy,
            quality=quality,
            artifact_hashes=artifact_hashes,
        )
        return {
            **base,
            "status": intake["status"],
            "rejection_code": intake.get("rejection_code"),
            "async_queue": intake["status"] == "queued",
        }
    except (FormulaLMPolicyError, FormulaLMConflictError) as exc:
        return {**base, "status": "rejected", "rejection_code": exc.code}
    except Exception:
        # Learning is deliberately fail-isolated from customer inference.  The
        # public result stays truthful and records no synthetic success claim.
        return {
            **base,
            "status": "unavailable",
            "rejection_code": "learning_boundary_unavailable",
        }


def _normalized_origin(value: str) -> str:
    text = value.strip().rstrip("/")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"}:
        raise HTTPException(status_code=403, detail="public_session_origin_invalid")
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise HTTPException(status_code=403, detail="public_session_origin_invalid")
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _configured_origins() -> frozenset[str]:
    raw = os.environ.get(
        "KOLIBRI_PUBLIC_SESSION_ORIGINS",
        os.environ.get(
            "KOLIBRI_CORS_ORIGINS",
            "https://kolibriai.ru,https://www.kolibriai.ru,"
            "http://127.0.0.1:5174,http://localhost:5174,"
            "http://127.0.0.1:4174,http://localhost:4174",
        ),
    )
    values: set[str] = set()
    for item in raw.split(","):
        if not item.strip() or item.strip() == "*":
            continue
        try:
            values.add(_normalized_origin(item))
        except HTTPException:
            continue
    return frozenset(values)


_PUBLIC_ORIGINS = _configured_origins()


def configure_public_response_origins(origins: list[str] | tuple[str, ...]) -> None:
    global _PUBLIC_ORIGINS
    _PUBLIC_ORIGINS = frozenset(_normalized_origin(item) for item in origins)


def _required_origin(request: Request) -> str:
    raw = request.headers.get("Origin", "")
    if not raw:
        raise HTTPException(status_code=403, detail="public_session_origin_required")
    origin = _normalized_origin(raw)
    if origin not in _PUBLIC_ORIGINS:
        raise HTTPException(status_code=403, detail="public_session_origin_forbidden")
    return origin


def _validate_session_origin(request: Request, session: dict[str, Any], *, required: bool) -> None:
    fetch_site = request.headers.get("Sec-Fetch-Site", "").strip().lower()
    if fetch_site in {"cross-site", "none"}:
        raise HTTPException(status_code=403, detail="public_session_cross_site_forbidden")
    raw = request.headers.get("Origin", "")
    if required and not raw:
        raise HTTPException(status_code=403, detail="public_session_origin_required")
    if raw:
        origin = _normalized_origin(raw)
        if origin not in _PUBLIC_ORIGINS or not hmac.compare_digest(origin, session["origin"]):
            raise HTTPException(status_code=403, detail="public_session_origin_mismatch")


def _session_ttl_seconds() -> int:
    try:
        value = int(os.environ.get("KOLIBRI_PUBLIC_SESSION_TTL_SECONDS", "900"))
    except ValueError:
        value = 900
    return min(3600, max(60, value))


def _response_rate_limit() -> int:
    try:
        value = int(os.environ.get("KOLIBRI_PUBLIC_SESSION_REQUESTS_PER_MINUTE", "30"))
    except ValueError:
        value = 30
    return min(300, max(1, value))


class PublicResponseStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS public_response_sessions (
                    session_id TEXT PRIMARY KEY,
                    token_sha256 TEXT NOT NULL UNIQUE,
                    origin TEXT NOT NULL,
                    project_id TEXT NOT NULL UNIQUE,
                    issued_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS public_session_responses (
                    response_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    context_json TEXT NOT NULL,
                    input_json TEXT,
                    http_status INTEGER NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(session_id, idempotency_key),
                    FOREIGN KEY(session_id) REFERENCES public_response_sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_public_responses_session
                    ON public_session_responses(session_id, created_at);
                CREATE TABLE IF NOT EXISTS public_session_response_events (
                    response_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY(response_id, sequence),
                    FOREIGN KEY(response_id) REFERENCES public_session_responses(response_id),
                    FOREIGN KEY(session_id) REFERENCES public_response_sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_public_response_events_session
                    ON public_session_response_events(session_id, response_id, sequence);
                CREATE TABLE IF NOT EXISTS public_session_projects (
                    project_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    title TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    deleted_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(session_id, idempotency_key),
                    FOREIGN KEY(session_id) REFERENCES public_response_sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_public_projects_session
                    ON public_session_projects(session_id, updated_at DESC);
                CREATE TABLE IF NOT EXISTS public_session_messages (
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_id TEXT,
                    metadata_json TEXT NOT NULL,
                    deleted_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    UNIQUE(session_id, project_id, idempotency_key),
                    FOREIGN KEY(session_id) REFERENCES public_response_sessions(session_id),
                    FOREIGN KEY(project_id) REFERENCES public_session_projects(project_id)
                );
                CREATE INDEX IF NOT EXISTS idx_public_messages_project
                    ON public_session_messages(session_id, project_id, created_at);
                CREATE TABLE IF NOT EXISTS public_session_mutations (
                    session_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    PRIMARY KEY(session_id, scope, idempotency_key),
                    FOREIGN KEY(session_id) REFERENCES public_response_sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS public_session_rate_limits (
                    subject_sha256 TEXT PRIMARY KEY,
                    window_started REAL NOT NULL,
                    request_count INTEGER NOT NULL
                );
                """
            )
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(public_session_responses)")
            }
            if "input_json" not in columns:
                # Existing public responses expire quickly.  Do not backfill
                # this field from context_json because that value can contain
                # previous-response history and provider-only instructions.
                connection.execute(
                    "ALTER TABLE public_session_responses ADD COLUMN input_json TEXT"
                )

    @staticmethod
    def _session_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["session_id"],
            "origin": row["origin"],
            "project_id": row["project_id"],
            "issued_at": float(row["issued_at"]),
            "expires_at": float(row["expires_at"]),
        }

    def _cleanup(self, connection: sqlite3.Connection, now: float) -> None:
        inactive_sessions = (
            "SELECT session_id FROM public_response_sessions "
            "WHERE expires_at <= ? OR revoked = 1"
        )
        connection.execute(
            "DELETE FROM public_session_messages WHERE expires_at <= ? "
            f"OR session_id IN ({inactive_sessions})",
            (now, now),
        )
        connection.execute(
            "DELETE FROM public_session_projects WHERE expires_at <= ? "
            f"OR session_id IN ({inactive_sessions})",
            (now, now),
        )
        connection.execute(
            "DELETE FROM public_session_mutations WHERE expires_at <= ? "
            f"OR session_id IN ({inactive_sessions})",
            (now, now),
        )
        connection.execute(
            "DELETE FROM public_session_response_events WHERE expires_at <= ? "
            f"OR session_id IN ({inactive_sessions})",
            (now, now),
        )
        connection.execute(
            "DELETE FROM public_session_responses WHERE expires_at <= ? "
            f"OR session_id IN ({inactive_sessions})",
            (now, now),
        )
        connection.execute("DELETE FROM public_response_sessions WHERE expires_at <= ? OR revoked = 1", (now,))
        connection.execute("DELETE FROM public_session_rate_limits WHERE window_started < ?", (now - 120,))

    def consume_rate(self, subject: str, *, limit: int, window_seconds: int = 60) -> bool:
        now = _now()
        subject_hash = _sha256(subject)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            row = connection.execute(
                "SELECT window_started, request_count FROM public_session_rate_limits WHERE subject_sha256 = ?",
                (subject_hash,),
            ).fetchone()
            if row is None or now - float(row["window_started"]) >= window_seconds:
                connection.execute(
                    "INSERT OR REPLACE INTO public_session_rate_limits(subject_sha256, window_started, request_count) VALUES (?, ?, 1)",
                    (subject_hash, now),
                )
                return True
            if int(row["request_count"]) >= limit:
                return False
            connection.execute(
                "UPDATE public_session_rate_limits SET request_count = request_count + 1 WHERE subject_sha256 = ?",
                (subject_hash,),
            )
            return True

    def issue(self, origin: str, *, ttl_seconds: int) -> tuple[dict[str, Any], str]:
        now = _now()
        session_credential = secrets.token_urlsafe(32)
        session = {
            "id": _opaque_id("psess"),
            "origin": origin,
            "project_id": _opaque_id("project_ephemeral"),
            "issued_at": now,
            "expires_at": now + ttl_seconds,
        }
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            connection.execute(
                """INSERT INTO public_response_sessions
                   (session_id, token_sha256, origin, project_id, issued_at, expires_at, revoked)
                   VALUES (?, ?, ?, ?, ?, ?, 0)""",
                (
                    session["id"], _sha256(session_credential), origin, session["project_id"],
                    session["issued_at"], session["expires_at"],
                ),
            )
            default_project_request = {
                "title": "New project",
                "metadata": {"source": "public_session"},
            }
            connection.execute(
                """INSERT INTO public_session_projects
                   (project_id, session_id, idempotency_key, request_sha256, title,
                    metadata_json, deleted_at, created_at, updated_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                (
                    session["project_id"],
                    session["id"],
                    _sha256("session-default-project"),
                    _json_hash(default_project_request),
                    default_project_request["title"],
                    json.dumps(
                        default_project_request["metadata"],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    now,
                    now,
                    session["expires_at"],
                ),
            )
        return session, session_credential

    def resolve(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        now = _now()
        token_hash = _sha256(token)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT * FROM public_response_sessions
                   WHERE token_sha256 = ? AND revoked = 0 AND expires_at > ?""",
                (token_hash, now),
            ).fetchone()
        return self._session_row(row) if row is not None else None

    def begin_response(
        self,
        session: dict[str, Any],
        *,
        response_id: str,
        idempotency_key: str,
        request_sha256: str,
        payload: dict[str, Any],
        context: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], bool, int]:
        now = _now()
        idempotency_hash = _sha256(idempotency_key)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT request_sha256, payload, http_status FROM public_session_responses
                   WHERE session_id = ? AND idempotency_key = ?""",
                (session["id"], idempotency_hash),
            ).fetchone()
            if row is not None:
                if not hmac.compare_digest(row["request_sha256"], request_sha256):
                    raise HTTPException(status_code=409, detail="idempotency_key_reused_with_different_payload")
                return json.loads(row["payload"]), False, int(row["http_status"])
            connection.execute(
                """INSERT INTO public_session_responses
                   (response_id, session_id, project_id, idempotency_key, request_sha256,
                    payload, context_json, input_json, http_status, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 202, ?, ?)""",
                (
                    response_id, session["id"], session["project_id"], idempotency_hash,
                    request_sha256, json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(context, ensure_ascii=False, sort_keys=True),
                    json.dumps(context, ensure_ascii=False, sort_keys=True), now,
                    session["expires_at"],
                ),
            )
        return payload, True, 202

    def finish_response(
        self,
        session_id: str,
        response_id: str,
        payload: dict[str, Any],
        context: list[dict[str, Any]],
        *,
        http_status: int,
    ) -> dict[str, Any]:
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            current = connection.execute(
                """SELECT payload FROM public_session_responses
                   WHERE response_id = ? AND session_id = ?""",
                (response_id, session_id),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="response_not_found")
            current_payload = json.loads(current["payload"])
            current_status = str(current_payload.get("status") or "")
            if current_status in {"completed", "failed", "cancelled", "incomplete"}:
                # Terminal state is fenced.  In particular a provider thread
                # that finishes after cancellation can never overwrite it.
                return current_payload
            cursor = connection.execute(
                """UPDATE public_session_responses
                   SET payload = ?, context_json = ?, http_status = ?
                   WHERE response_id = ? AND session_id = ?""",
                (
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    json.dumps(context, ensure_ascii=False, sort_keys=True),
                    http_status, response_id, session_id,
                ),
            )
        return payload

    def append_response_event(
        self,
        session_id: str,
        response_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist one monotonic replayable event and return its public body."""

        now = _now()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT expires_at FROM public_session_responses
                   WHERE response_id = ? AND session_id = ? AND expires_at > ?""",
                (response_id, session_id, now),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="response_not_found")
            sequence_row = connection.execute(
                """SELECT COALESCE(MAX(sequence), -1) + 1
                   FROM public_session_response_events
                   WHERE response_id = ? AND session_id = ?""",
                (response_id, session_id),
            ).fetchone()
            sequence = int(sequence_row[0])
            event_payload = {**payload, "sequence_number": sequence}
            connection.execute(
                """INSERT INTO public_session_response_events
                   (response_id, session_id, sequence, event_type, payload_json,
                    created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    response_id,
                    session_id,
                    sequence,
                    event_type,
                    json.dumps(event_payload, ensure_ascii=False, sort_keys=True),
                    now,
                    float(row["expires_at"]),
                ),
            )
        return event_payload

    def list_response_events(
        self,
        session_id: str,
        response_id: str,
        *,
        after_sequence: int = -1,
    ) -> list[tuple[str, dict[str, Any]]]:
        now = _now()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            rows = connection.execute(
                """SELECT event_type, payload_json
                   FROM public_session_response_events
                   WHERE session_id = ? AND response_id = ? AND sequence > ?
                     AND expires_at > ?
                   ORDER BY sequence ASC""",
                (session_id, response_id, after_sequence, now),
            ).fetchall()
        return [
            (str(row["event_type"]), json.loads(row["payload_json"]))
            for row in rows
        ]

    def cancel_response(
        self,
        session_id: str,
        response_id: str,
    ) -> dict[str, Any]:
        """Atomically fence an active response and persist one cancel event."""

        now = _now()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """SELECT payload, context_json, expires_at
                   FROM public_session_responses
                   WHERE response_id = ? AND session_id = ? AND expires_at > ?""",
                (response_id, session_id, now),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="response_not_found")
            payload = json.loads(row["payload"])
            if payload.get("status") in {"completed", "failed", "cancelled", "incomplete"}:
                return payload
            cancelled = {
                **payload,
                "status": "cancelled",
                "completed_at": int(now),
                "error": None,
            }
            connection.execute(
                """UPDATE public_session_responses
                   SET payload = ?, http_status = 200
                   WHERE response_id = ? AND session_id = ?""",
                (
                    json.dumps(cancelled, ensure_ascii=False, sort_keys=True),
                    response_id,
                    session_id,
                ),
            )
            sequence_row = connection.execute(
                """SELECT COALESCE(MAX(sequence), -1) + 1
                   FROM public_session_response_events
                   WHERE response_id = ? AND session_id = ?""",
                (response_id, session_id),
            ).fetchone()
            sequence = int(sequence_row[0])
            event_payload = {
                "type": "response.cancelled",
                "sequence_number": sequence,
                "response": cancelled,
            }
            connection.execute(
                """INSERT INTO public_session_response_events
                   (response_id, session_id, sequence, event_type, payload_json,
                    created_at, expires_at)
                   VALUES (?, ?, ?, 'response.cancelled', ?, ?, ?)""",
                (
                    response_id,
                    session_id,
                    sequence,
                    json.dumps(event_payload, ensure_ascii=False, sort_keys=True),
                    now,
                    float(row["expires_at"]),
                ),
            )
        return cancelled

    def get_response(self, session_id: str, response_id: str) -> tuple[dict[str, Any], list[dict[str, Any]], int] | None:
        now = _now()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT payload, context_json, http_status FROM public_session_responses
                   WHERE session_id = ? AND response_id = ? AND expires_at > ?""",
                (session_id, response_id, now),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload"]), json.loads(row["context_json"]), int(row["http_status"])

    def list_responses(
        self,
        session_id: str,
        *,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        now = _now()
        project_clause = "" if project_id is None else " AND project_id = ?"
        parameters: tuple[Any, ...] = (
            (session_id, now)
            if project_id is None
            else (session_id, now, project_id)
        )
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            rows = connection.execute(
                """SELECT payload FROM public_session_responses
                   WHERE session_id = ? AND expires_at > ?"""
                + project_clause
                + " ORDER BY created_at DESC",
                parameters,
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get_response_input(self, session_id: str, response_id: str) -> list[dict[str, Any]]:
        now = _now()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT input_json FROM public_session_responses
                   WHERE session_id = ? AND response_id = ? AND expires_at > ?""",
                (session_id, response_id, now),
            ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404,
                detail="response_not_found",
                headers={"Cache-Control": "no-store"},
            )
        if row["input_json"] is None:
            raise HTTPException(
                status_code=409,
                detail="input_items_not_recorded_for_legacy_response",
                headers={"Cache-Control": "no-store"},
            )
        value = json.loads(row["input_json"])
        return value if isinstance(value, list) else []

    @staticmethod
    def _project_payload(row: sqlite3.Row) -> dict[str, Any]:
        deleted_at = float(row["deleted_at"]) if row["deleted_at"] is not None else None
        return {
            "id": row["project_id"],
            "object": "project.ephemeral",
            "title": row["title"],
            "status": "deleted" if deleted_at is not None else "active",
            "durable": False,
            "metadata": json.loads(row["metadata_json"]),
            "message_count": int(row["message_count"]),
            "created_at": int(float(row["created_at"])),
            "updated_at": int(float(row["updated_at"])),
            "deleted_at": int(deleted_at) if deleted_at is not None else None,
        }

    @staticmethod
    def _message_payload(row: sqlite3.Row) -> dict[str, Any]:
        deleted_at = float(row["deleted_at"]) if row["deleted_at"] is not None else None
        return {
            "id": row["message_id"],
            "object": "project.message",
            "project_id": row["project_id"],
            "role": row["role"],
            "content": row["content"],
            "status": "deleted" if deleted_at is not None else row["status"],
            "message_status": row["status"],
            "response_id": row["response_id"],
            "metadata": json.loads(row["metadata_json"]),
            "created_at": int(float(row["created_at"])),
            "updated_at": int(float(row["updated_at"])),
            "deleted_at": int(deleted_at) if deleted_at is not None else None,
        }

    @staticmethod
    def _project_query() -> str:
        return """SELECT p.*,
                         (SELECT COUNT(*) FROM public_session_messages m
                           WHERE m.session_id = p.session_id
                             AND m.project_id = p.project_id
                             AND m.deleted_at IS NULL) AS message_count
                    FROM public_session_projects p"""

    def get_project(
        self,
        session_id: str,
        project_id: str,
        *,
        include_deleted: bool = False,
    ) -> dict[str, Any] | None:
        now = _now()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                self._project_query()
                + " WHERE p.session_id = ? AND p.project_id = ? AND p.expires_at > ?",
                (session_id, project_id, now),
            ).fetchone()
        if row is None or (row["deleted_at"] is not None and not include_deleted):
            return None
        return self._project_payload(row)

    def list_projects(
        self,
        session_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        now = _now()
        deleted_clause = "" if include_deleted else " AND p.deleted_at IS NULL"
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            rows = connection.execute(
                self._project_query()
                + " WHERE p.session_id = ? AND p.expires_at > ?"
                + deleted_clause
                + " ORDER BY p.updated_at DESC, p.project_id",
                (session_id, now),
            ).fetchall()
        return [self._project_payload(row) for row in rows]

    def create_project(
        self,
        session: dict[str, Any],
        *,
        project_id: str,
        idempotency_key: str,
        request_sha256: str,
        title: str,
        metadata: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        now = _now()
        key_hash = _sha256(idempotency_key)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            existing = connection.execute(
                """SELECT project_id, request_sha256 FROM public_session_projects
                     WHERE session_id = ? AND idempotency_key = ?""",
                (session["id"], key_hash),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(existing["request_sha256"], request_sha256):
                    raise HTTPException(
                        status_code=409,
                        detail="idempotency_key_reused_with_different_payload",
                    )
                row = connection.execute(
                    self._project_query()
                    + " WHERE p.session_id = ? AND p.project_id = ?",
                    (session["id"], existing["project_id"]),
                ).fetchone()
                assert row is not None
                return self._project_payload(row), False
            connection.execute(
                """INSERT INTO public_session_projects
                   (project_id, session_id, idempotency_key, request_sha256, title,
                    metadata_json, deleted_at, created_at, updated_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                (
                    project_id,
                    session["id"],
                    key_hash,
                    request_sha256,
                    title,
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                    session["expires_at"],
                ),
            )
            row = connection.execute(
                self._project_query()
                + " WHERE p.session_id = ? AND p.project_id = ?",
                (session["id"], project_id),
            ).fetchone()
            assert row is not None
            return self._project_payload(row), True

    @staticmethod
    def _idempotent_mutation_result(
        connection: sqlite3.Connection,
        *,
        session_id: str,
        scope: str,
        key_hash: str,
        request_sha256: str,
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """SELECT request_sha256, result_json FROM public_session_mutations
                 WHERE session_id = ? AND scope = ? AND idempotency_key = ?""",
            (session_id, scope, key_hash),
        ).fetchone()
        if row is None:
            return None
        if not hmac.compare_digest(row["request_sha256"], request_sha256):
            raise HTTPException(
                status_code=409,
                detail="idempotency_key_reused_with_different_payload",
            )
        return json.loads(row["result_json"])

    @staticmethod
    def _record_mutation(
        connection: sqlite3.Connection,
        *,
        session: dict[str, Any],
        scope: str,
        key_hash: str,
        request_sha256: str,
        result: dict[str, Any],
        now: float,
    ) -> None:
        connection.execute(
            """INSERT INTO public_session_mutations
               (session_id, scope, idempotency_key, request_sha256, result_json,
                created_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                session["id"],
                scope,
                key_hash,
                request_sha256,
                json.dumps(result, ensure_ascii=False, sort_keys=True),
                now,
                session["expires_at"],
            ),
        )

    def update_project(
        self,
        session: dict[str, Any],
        project_id: str,
        *,
        idempotency_key: str,
        request_sha256: str,
        title: str | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = _now()
        scope = f"project:{project_id}:update"
        key_hash = _sha256(idempotency_key)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            repeated = self._idempotent_mutation_result(
                connection,
                session_id=session["id"],
                scope=scope,
                key_hash=key_hash,
                request_sha256=request_sha256,
            )
            if repeated is not None:
                return repeated
            current = connection.execute(
                """SELECT title, metadata_json, deleted_at FROM public_session_projects
                     WHERE session_id = ? AND project_id = ? AND expires_at > ?""",
                (session["id"], project_id, now),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="project_not_found")
            if current["deleted_at"] is not None:
                raise HTTPException(status_code=409, detail="project_is_deleted")
            connection.execute(
                """UPDATE public_session_projects
                      SET title = ?, metadata_json = ?, updated_at = ?
                    WHERE session_id = ? AND project_id = ?""",
                (
                    title if title is not None else current["title"],
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                    if metadata is not None
                    else current["metadata_json"],
                    now,
                    session["id"],
                    project_id,
                ),
            )
            row = connection.execute(
                self._project_query()
                + " WHERE p.session_id = ? AND p.project_id = ?",
                (session["id"], project_id),
            ).fetchone()
            assert row is not None
            result = self._project_payload(row)
            self._record_mutation(
                connection,
                session=session,
                scope=scope,
                key_hash=key_hash,
                request_sha256=request_sha256,
                result=result,
                now=now,
            )
            return result

    def set_project_deleted(
        self,
        session: dict[str, Any],
        project_id: str,
        *,
        deleted: bool,
        idempotency_key: str,
        request_sha256: str,
    ) -> dict[str, Any]:
        now = _now()
        operation = "delete" if deleted else "restore"
        scope = f"project:{project_id}:{operation}"
        key_hash = _sha256(idempotency_key)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            repeated = self._idempotent_mutation_result(
                connection,
                session_id=session["id"],
                scope=scope,
                key_hash=key_hash,
                request_sha256=request_sha256,
            )
            if repeated is not None:
                return repeated
            current = connection.execute(
                """SELECT project_id FROM public_session_projects
                     WHERE session_id = ? AND project_id = ? AND expires_at > ?""",
                (session["id"], project_id, now),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="project_not_found")
            connection.execute(
                """UPDATE public_session_projects
                      SET deleted_at = ?, updated_at = ?
                    WHERE session_id = ? AND project_id = ?""",
                (now if deleted else None, now, session["id"], project_id),
            )
            row = connection.execute(
                self._project_query()
                + " WHERE p.session_id = ? AND p.project_id = ?",
                (session["id"], project_id),
            ).fetchone()
            assert row is not None
            result = self._project_payload(row)
            self._record_mutation(
                connection,
                session=session,
                scope=scope,
                key_hash=key_hash,
                request_sha256=request_sha256,
                result=result,
                now=now,
            )
            return result

    def list_messages(
        self,
        session_id: str,
        project_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        now = _now()
        deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            rows = connection.execute(
                """SELECT * FROM public_session_messages
                    WHERE session_id = ? AND project_id = ? AND expires_at > ?"""
                + deleted_clause
                + " ORDER BY created_at, message_id",
                (session_id, project_id, now),
            ).fetchall()
        return [self._message_payload(row) for row in rows]

    def get_message(
        self,
        session_id: str,
        project_id: str,
        message_id: str,
        *,
        include_deleted: bool = False,
    ) -> dict[str, Any] | None:
        now = _now()
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            self._cleanup(connection, now)
            row = connection.execute(
                """SELECT * FROM public_session_messages
                    WHERE session_id = ? AND project_id = ? AND message_id = ?
                      AND expires_at > ?""",
                (session_id, project_id, message_id, now),
            ).fetchone()
        if row is None or (row["deleted_at"] is not None and not include_deleted):
            return None
        return self._message_payload(row)

    def create_message(
        self,
        session: dict[str, Any],
        project_id: str,
        *,
        message_id: str,
        idempotency_key: str,
        request_sha256: str,
        role: str,
        content: str,
        status: str,
        response_id: str | None,
        metadata: dict[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        now = _now()
        key_hash = _sha256(idempotency_key)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            project = connection.execute(
                """SELECT deleted_at FROM public_session_projects
                     WHERE session_id = ? AND project_id = ? AND expires_at > ?""",
                (session["id"], project_id, now),
            ).fetchone()
            if project is None:
                raise HTTPException(status_code=404, detail="project_not_found")
            if project["deleted_at"] is not None:
                raise HTTPException(status_code=409, detail="project_is_deleted")
            existing = connection.execute(
                """SELECT message_id, request_sha256 FROM public_session_messages
                     WHERE session_id = ? AND project_id = ? AND idempotency_key = ?""",
                (session["id"], project_id, key_hash),
            ).fetchone()
            if existing is not None:
                if not hmac.compare_digest(existing["request_sha256"], request_sha256):
                    raise HTTPException(
                        status_code=409,
                        detail="idempotency_key_reused_with_different_payload",
                    )
                row = connection.execute(
                    """SELECT * FROM public_session_messages
                        WHERE session_id = ? AND project_id = ? AND message_id = ?""",
                    (session["id"], project_id, existing["message_id"]),
                ).fetchone()
                assert row is not None
                return self._message_payload(row), False
            connection.execute(
                """INSERT INTO public_session_messages
                   (message_id, session_id, project_id, idempotency_key, request_sha256,
                    role, content, status, response_id, metadata_json, deleted_at,
                    created_at, updated_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                (
                    message_id,
                    session["id"],
                    project_id,
                    key_hash,
                    request_sha256,
                    role,
                    content,
                    status,
                    response_id,
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    now,
                    now,
                    session["expires_at"],
                ),
            )
            connection.execute(
                """UPDATE public_session_projects SET updated_at = ?
                    WHERE session_id = ? AND project_id = ?""",
                (now, session["id"], project_id),
            )
            row = connection.execute(
                """SELECT * FROM public_session_messages
                    WHERE session_id = ? AND project_id = ? AND message_id = ?""",
                (session["id"], project_id, message_id),
            ).fetchone()
            assert row is not None
            return self._message_payload(row), True

    def update_message(
        self,
        session: dict[str, Any],
        project_id: str,
        message_id: str,
        *,
        idempotency_key: str,
        request_sha256: str,
        content: str | None,
        status: str | None,
        response_id: str | None,
        response_id_supplied: bool,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        now = _now()
        scope = f"project:{project_id}:message:{message_id}:update"
        key_hash = _sha256(idempotency_key)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            repeated = self._idempotent_mutation_result(
                connection,
                session_id=session["id"],
                scope=scope,
                key_hash=key_hash,
                request_sha256=request_sha256,
            )
            if repeated is not None:
                return repeated
            current = connection.execute(
                """SELECT * FROM public_session_messages
                    WHERE session_id = ? AND project_id = ? AND message_id = ?
                      AND expires_at > ?""",
                (session["id"], project_id, message_id, now),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="message_not_found")
            if current["deleted_at"] is not None:
                raise HTTPException(status_code=409, detail="message_is_deleted")
            connection.execute(
                """UPDATE public_session_messages
                      SET content = ?, status = ?, response_id = ?, metadata_json = ?,
                          updated_at = ?
                    WHERE session_id = ? AND project_id = ? AND message_id = ?""",
                (
                    content if content is not None else current["content"],
                    status if status is not None else current["status"],
                    response_id if response_id_supplied else current["response_id"],
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                    if metadata is not None
                    else current["metadata_json"],
                    now,
                    session["id"],
                    project_id,
                    message_id,
                ),
            )
            connection.execute(
                """UPDATE public_session_projects SET updated_at = ?
                    WHERE session_id = ? AND project_id = ?""",
                (now, session["id"], project_id),
            )
            row = connection.execute(
                """SELECT * FROM public_session_messages
                    WHERE session_id = ? AND project_id = ? AND message_id = ?""",
                (session["id"], project_id, message_id),
            ).fetchone()
            assert row is not None
            result = self._message_payload(row)
            self._record_mutation(
                connection,
                session=session,
                scope=scope,
                key_hash=key_hash,
                request_sha256=request_sha256,
                result=result,
                now=now,
            )
            return result

    def set_message_deleted(
        self,
        session: dict[str, Any],
        project_id: str,
        message_id: str,
        *,
        deleted: bool,
        idempotency_key: str,
        request_sha256: str,
    ) -> dict[str, Any]:
        now = _now()
        operation = "delete" if deleted else "restore"
        scope = f"project:{project_id}:message:{message_id}:{operation}"
        key_hash = _sha256(idempotency_key)
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._cleanup(connection, now)
            repeated = self._idempotent_mutation_result(
                connection,
                session_id=session["id"],
                scope=scope,
                key_hash=key_hash,
                request_sha256=request_sha256,
            )
            if repeated is not None:
                return repeated
            current = connection.execute(
                """SELECT message_id FROM public_session_messages
                    WHERE session_id = ? AND project_id = ? AND message_id = ?
                      AND expires_at > ?""",
                (session["id"], project_id, message_id, now),
            ).fetchone()
            if current is None:
                raise HTTPException(status_code=404, detail="message_not_found")
            connection.execute(
                """UPDATE public_session_messages
                      SET deleted_at = ?, updated_at = ?
                    WHERE session_id = ? AND project_id = ? AND message_id = ?""",
                (
                    now if deleted else None,
                    now,
                    session["id"],
                    project_id,
                    message_id,
                ),
            )
            connection.execute(
                """UPDATE public_session_projects SET updated_at = ?
                    WHERE session_id = ? AND project_id = ?""",
                (now, session["id"], project_id),
            )
            row = connection.execute(
                """SELECT * FROM public_session_messages
                    WHERE session_id = ? AND project_id = ? AND message_id = ?""",
                (session["id"], project_id, message_id),
            ).fetchone()
            assert row is not None
            result = self._message_payload(row)
            self._record_mutation(
                connection,
                session=session,
                scope=scope,
                key_hash=key_hash,
                request_sha256=request_sha256,
                result=result,
                now=now,
            )
            return result

    def expire_session_for_test(self, session_id: str) -> None:
        with self._lock, closing_sqlite_transaction(self.connect) as connection:
            connection.execute(
                "UPDATE public_response_sessions SET expires_at = 0 WHERE session_id = ?",
                (session_id,),
            )


_STORE = PublicResponseStore(DB_PATH)


def configure_public_response_store(path: str | Path) -> PublicResponseStore:
    global _STORE
    _STORE = PublicResponseStore(path)
    return _STORE


PublicExecutor = Callable[..., Awaitable[dict[str, Any]]]
_EXECUTOR: PublicExecutor | None = None


def configure_public_response_executor(executor: PublicExecutor | None) -> None:
    global _EXECUTOR
    _EXECUTOR = executor


async def _call_public_executor(**kwargs: Any) -> dict[str, Any]:
    """Call the executor with additive streaming/cancellation compatibility."""

    if _EXECUTOR is None:
        raise RuntimeError("public_response_executor_not_configured")
    optional = dict(kwargs)
    while True:
        try:
            return await _EXECUTOR(**optional)
        except TypeError as exc:
            match = re.search(
                r"got an unexpected keyword argument ['\"]"
                r"(requested_tools|reasoning|timeout_seconds|stream_callback|cancel_event)['\"]$",
                str(exc),
            )
            unsupported = match.group(1) if match else None
            if unsupported not in optional:
                raise
            optional.pop(unsupported)


def _owner_principal(request: Request) -> str | None:
    if request.headers.get("Authorization", "").strip():
        return require_execution_auth(request)
    return None


def _session_cookie_candidates(request: Request) -> list[str]:
    """Return bounded duplicate cookie values in wire order.

    Browsers may retain an older cookie with the same name on ``Path=/`` while
    the current session uses ``Path=/v1``. Starlette's cookie mapping collapses
    duplicate names, so a stale shorter-path value can shadow the valid token.
    Trying each bounded opaque candidate recovers the valid session without
    exposing, logging or weakening validation of either token.
    """

    candidates: list[str] = []
    seen: set[str] = set()
    for raw_name, raw_value in request.scope.get("headers", []):
        if raw_name.lower() != b"cookie":
            continue
        header = raw_value.decode("latin-1", errors="ignore")[:4096]
        for item in header.split(";"):
            name, separator, value = item.partition("=")
            token = value.strip()
            if (
                separator
                and name.strip() == COOKIE_NAME
                and token not in seen
                and _PUBLIC_SESSION_TOKEN.fullmatch(token)
            ):
                seen.add(token)
                candidates.append(token)
                if len(candidates) >= MAX_SESSION_COOKIE_CANDIDATES:
                    return candidates
    parsed = request.cookies.get(COOKIE_NAME, "")
    if parsed not in seen and _PUBLIC_SESSION_TOKEN.fullmatch(parsed):
        candidates.append(parsed)
    return candidates


def _require_session(request: Request, *, mutating: bool) -> dict[str, Any]:
    session = None
    for token in _session_cookie_candidates(request):
        session = _STORE.resolve(token)
        if session is not None:
            break
    if session is None:
        # An expired session is an authentication state transition, never a
        # cacheable API result.  This also prevents a retired browser cache or
        # intermediary from replaying the marker after the Shell has issued a
        # fresh cookie and retried the idempotent request.
        raise HTTPException(
            status_code=401,
            detail="public_session_required_or_expired",
            headers={"Cache-Control": "no-store"},
        )
    _validate_session_origin(request, session, required=mutating)
    return session


def _optional_session(request: Request, *, mutating: bool) -> dict[str, Any] | None:
    for token in _session_cookie_candidates(request):
        session = _STORE.resolve(token)
        if session is not None:
            _validate_session_origin(request, session, required=mutating)
            return session
    return None


def _session_payload(session: dict[str, Any]) -> dict[str, Any]:
    project = _STORE.get_project(session["id"], session["project_id"], include_deleted=True)
    project_title = project.get("title") if isinstance(project, dict) else "New project"
    return {
        "id": session["id"],
        "object": "public.session",
        "active": True,
        "expires_at": int(session["expires_at"]),
        "project": {
            "id": session["project_id"],
            "object": "project.ephemeral",
            "title": project_title,
            "durable": False,
        },
        "model": "kolibri",
    }


def _require_owned_project(
    session: dict[str, Any],
    project_id: str,
    *,
    allow_deleted: bool = False,
) -> dict[str, Any]:
    project = _STORE.get_project(
        session["id"],
        project_id,
        include_deleted=True,
    )
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    if project.get("status") == "deleted" and not allow_deleted:
        raise HTTPException(status_code=409, detail="project_is_deleted")
    return project


def _require_owned_response(
    session: dict[str, Any],
    project_id: str,
    response_id: str | None,
) -> None:
    if response_id is None:
        return
    record = _STORE.get_response(session["id"], response_id)
    if record is None or record[0].get("project_id") != project_id:
        raise HTTPException(status_code=404, detail="response_not_found")


def require_public_response_session(request: Request, *, mutating: bool = False) -> dict[str, Any]:
    """Shared session boundary for same-origin public V1 extensions."""

    return _require_session(request, mutating=mutating)


def _input_messages(input_value: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages = [{"role": "user", "content": input_value}] if isinstance(input_value, str) else input_value
    if not messages or len(messages) > MAX_MESSAGES:
        raise HTTPException(status_code=422, detail="input must contain between 1 and 100 messages")
    normalized: list[dict[str, Any]] = []
    for item in messages:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant", "system", "developer"}:
            raise HTTPException(status_code=422, detail="input contains an invalid message")
        if "content" not in item:
            raise HTTPException(status_code=422, detail="input message content is required")
        normalized.append({"role": item["role"], "content": item["content"]})
    if len(json.dumps(normalized, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="response input exceeds 1 MiB")
    return normalized


def _latest_user_text(input_value: str | list[dict[str, Any]]) -> str:
    if isinstance(input_value, str):
        return input_value.strip()
    for item in reversed(input_value):
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text = "".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict)
            ).strip()
            if text:
                return text
    return ""


def _response_shell(
    response_id: str,
    body: ResponseCreate,
    project_id: str,
    *,
    status: str,
    public_tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    task = body.task.model_dump(mode="json") if body.task is not None else None
    work_summary = build_work_summary(
        response_status=status,
        task=task,
        requested_tools=public_tools,
    )
    return {
        "id": response_id,
        "object": "response",
        "created_at": int(_now()),
        "status": status,
        "completed_at": None,
        "error": None,
        "incomplete_details": None,
        "instructions": body.instructions,
        "max_output_tokens": None,
        "model": "kolibri",
        "output": [],
        "parallel_tool_calls": True,
        "previous_response_id": body.previous_response_id,
        "background": body.background,
        "reasoning": body.reasoning.model_dump(mode="json"),
        "store": True,
        "temperature": None,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": list(public_tools or []),
        "top_p": None,
        "truncation": "disabled",
        "usage": None,
        "metadata": summary_metadata(
            sanitize_learning_value(body.metadata),
            work_summary,
        ),
        "project_id": project_id,
        "execution_mode": body.execution_mode,
    }


def _provider_reasoning_output_item(
    response_id: str,
    body: ResponseCreate,
    deltas: list[str],
) -> dict[str, Any] | None:
    """Build a reasoning item only from a real provider summary stream."""

    if body.reasoning.summary is None or not deltas:
        return None
    text = "".join(deltas).strip()
    if not text:
        return None
    digest = hashlib.sha256(f"{response_id}:provider-summary".encode("utf-8")).hexdigest()[:32]
    return {
        "id": f"rs_{digest}",
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": text}],
    }


def _replace_reasoning_output(
    payload: dict[str, Any],
    *,
    response_id: str,
    body: ResponseCreate,
    deltas: list[str],
) -> None:
    output = [
        item for item in payload.get("output", [])
        if not (isinstance(item, dict) and item.get("type") == "reasoning")
    ]
    reasoning = _provider_reasoning_output_item(response_id, body, deltas)
    if reasoning is not None:
        output.append(reasoning)
    payload["output"] = output


def _decorate_response_work_summary(payload: dict[str, Any]) -> dict[str, Any]:
    """Add the public summary to owner responses without exposing technical data."""

    response = dict(payload)
    technical = response.get("technical")
    routing = (
        technical.get("provider_routing")
        if isinstance(technical, dict) and isinstance(technical.get("provider_routing"), dict)
        else {}
    )
    verification = response.get("verification")
    if not isinstance(verification, dict):
        candidate = routing.get("verifier_evidence")
        verification = candidate if isinstance(candidate, dict) else None
    task = response.get("task") if isinstance(response.get("task"), dict) else None
    requested_tools = response.get("tools") if isinstance(response.get("tools"), list) else []
    tool_calls = routing.get("tool_calls") if isinstance(routing.get("tool_calls"), list) else []
    citations = response.get("citations") if isinstance(response.get("citations"), list) else []
    work_summary = build_work_summary(
        response_status=str(response.get("status") or "in_progress"),
        task=task,
        requested_tools=requested_tools,
        tool_calls=tool_calls,
        citations=citations,
        verification=verification,
    )
    response["metadata"] = summary_metadata(
        response.get("metadata") if isinstance(response.get("metadata"), dict) else {},
        work_summary,
    )
    output = list(response.get("output") or [])
    if response.get("id") and not any(
        isinstance(item, dict) and item.get("type") == "reasoning" for item in output
    ):
        output.append(reasoning_output_item(str(response["id"]), work_summary))
    response["output"] = output
    return response


def _public_tool_identifier(item: dict[str, Any]) -> str:
    request_type = str(item.get("type") or "").strip().lower()
    if request_type in {"function", "skill", "tool"}:
        # Public sessions never invoke user-defined functions, skills, or a
        # generic tool envelope. Only the built-in scoped search declaration
        # is accepted.
        return ""
    return str(item.get("id") or item.get("name") or request_type).strip().lower()


def _validate_public_tools(
    raw_tools: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not raw_tools:
        return [], []
    if len(raw_tools) != 1 or not isinstance(raw_tools[0], dict):
        raise HTTPException(status_code=422, detail="public_session_tool_not_allowed")
    raw = raw_tools[0]
    identifier = _public_tool_identifier(raw)
    if identifier not in PUBLIC_TOOL_ALIASES:
        raise HTTPException(status_code=422, detail="public_session_tool_not_allowed")
    context_size = str(raw.get("search_context_size") or "medium").strip().lower()
    if context_size not in {"low", "medium", "high"}:
        raise HTTPException(status_code=422, detail="web_search_context_size_invalid")
    try:
        bindings = get_capability_gateway().validate_requested_tools(raw_tools)
    except CapabilityRequestError as exc:
        raise HTTPException(status_code=422, detail=exc.public_detail()) from exc
    if len(bindings) != 1 or bindings[0].get("id") != WEB_SEARCH_TOOL_ID:
        raise HTTPException(status_code=422, detail="public_session_tool_not_allowed")
    declaration = {"type": "web_search", "search_context_size": context_size}
    return bindings, [declaration]


def _request_key(body: ResponseCreate, request: Request) -> str:
    value = body.idempotency_key or request.headers.get("Idempotency-Key", "")
    if not value or len(value) > 300 or not value.strip():
        raise HTTPException(status_code=422, detail="idempotency_key_required_for_public_session")
    return value.strip()


def _mutation_key(request: Request, body: dict[str, Any] | None = None) -> str:
    body_value = body.get("idempotency_key") if isinstance(body, dict) else None
    header_value = request.headers.get("Idempotency-Key", "")
    if body_value is not None and not isinstance(body_value, str):
        raise HTTPException(status_code=422, detail="idempotency_key_invalid")
    if body_value and header_value and body_value.strip() != header_value.strip():
        raise HTTPException(status_code=409, detail="idempotency_key_header_body_mismatch")
    value = str(body_value or header_value).strip()
    if not value or len(value) > 300:
        raise HTTPException(
            status_code=422,
            detail="idempotency_key_required_for_public_session",
        )
    return value


def _bounded_text(
    value: Any,
    *,
    field: str,
    maximum: int,
    required: bool,
) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail=f"{field}_invalid")
    text = value.replace("\x00", "").strip()
    if (required and not text) or len(text) > maximum:
        raise HTTPException(status_code=422, detail=f"{field}_invalid")
    return text


def _public_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="metadata_invalid")
    sanitized = sanitize_learning_value(value)
    if len(json.dumps(sanitized, ensure_ascii=False).encode("utf-8")) > 64 * 1024:
        raise HTTPException(status_code=413, detail="metadata_too_large")
    return sanitized


def _project_create_semantics(body: dict[str, Any]) -> dict[str, Any]:
    unknown = set(body) - {"idempotency_key", "title", "name", "metadata"}
    if unknown:
        raise HTTPException(status_code=422, detail="project_fields_invalid")
    if body.get("title") is not None and body.get("name") is not None:
        if str(body["title"]).strip() != str(body["name"]).strip():
            raise HTTPException(status_code=422, detail="project_title_conflict")
    title = _bounded_text(
        body.get("title", body.get("name", "New project")),
        field="project_title",
        maximum=200,
        required=True,
    )
    assert title is not None
    return {"title": title, "metadata": _public_metadata(body.get("metadata"))}


def _project_update_semantics(body: dict[str, Any]) -> dict[str, Any]:
    unknown = set(body) - {"idempotency_key", "title", "name", "metadata"}
    if unknown:
        raise HTTPException(status_code=422, detail="project_fields_invalid")
    supplied_title = "title" in body or "name" in body
    if body.get("title") is not None and body.get("name") is not None:
        if str(body["title"]).strip() != str(body["name"]).strip():
            raise HTTPException(status_code=422, detail="project_title_conflict")
    title = (
        _bounded_text(
            body.get("title", body.get("name")),
            field="project_title",
            maximum=200,
            required=True,
        )
        if supplied_title
        else None
    )
    metadata = _public_metadata(body.get("metadata")) if "metadata" in body else None
    if title is None and metadata is None:
        raise HTTPException(status_code=422, detail="project_update_empty")
    return {"title": title, "metadata": metadata}


_PUBLIC_MESSAGE_ROLES = frozenset({"user", "assistant"})
_PUBLIC_MESSAGE_STATUSES = frozenset({
    "pending", "running", "completed", "failed", "incomplete", "cancelled",
})


def _message_semantics(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    unknown = set(body) - {
        "idempotency_key", "role", "content", "text", "status", "response_id", "metadata",
    }
    if unknown:
        raise HTTPException(status_code=422, detail="message_fields_invalid")
    if body.get("content") is not None and body.get("text") is not None:
        if str(body["content"]) != str(body["text"]):
            raise HTTPException(status_code=422, detail="message_content_conflict")
    content_supplied = "content" in body or "text" in body
    content = (
        _bounded_text(
            body.get("content", body.get("text")),
            field="message_content",
            maximum=100_000,
            required=True,
        )
        if content_supplied or not partial
        else None
    )
    role = body.get("role")
    if partial and "role" in body:
        raise HTTPException(status_code=422, detail="message_role_immutable")
    if not partial or role is not None:
        if role not in _PUBLIC_MESSAGE_ROLES:
            raise HTTPException(status_code=422, detail="message_role_invalid")
    status = body.get("status", "completed" if not partial else None)
    if status is not None and status not in _PUBLIC_MESSAGE_STATUSES:
        raise HTTPException(status_code=422, detail="message_status_invalid")
    response_id_supplied = "response_id" in body
    response_id = body.get("response_id")
    if response_id is not None:
        response_id = _bounded_text(
            response_id,
            field="response_id",
            maximum=200,
            required=True,
        )
    metadata = _public_metadata(body.get("metadata")) if "metadata" in body else (None if partial else {})
    if partial and all(
        value is None
        for value in (content, status, metadata)
    ) and not response_id_supplied:
        raise HTTPException(status_code=422, detail="message_update_empty")
    return {
        "role": role,
        "content": content,
        "status": status,
        "response_id": response_id,
        "response_id_supplied": response_id_supplied,
        "metadata": metadata,
    }


def _request_semantics(body: ResponseCreate) -> dict[str, Any]:
    return body.model_dump(mode="json", exclude={"idempotency_key", "stream"})


def _provider_failure_reason(routing: dict[str, Any]) -> str:
    """Return a bounded non-secret reason for deterministic fallback proof."""

    value = str(routing.get("error_type") or "").strip().lower()
    if not value:
        attempts = routing.get("attempts") if isinstance(routing.get("attempts"), list) else []
        failed = [
            str(item.get("error_type") or "").strip().lower()
            for item in attempts
            if isinstance(item, dict) and item.get("status") in {"failed", "skipped"}
        ]
        value = failed[-1] if failed else "provider_unavailable"
    return value if re.fullmatch(r"[a-z0-9_]{1,80}", value) else "provider_unavailable"


def _public_chat_timeout_seconds() -> float | None:
    """Return an explicit operator deadline, never an implicit UI deadline.

    Public Responses are durable and resumable.  A client disconnect or a
    long, healthy provider run must not terminate the response.  Individual
    provider attempts still have stall/lease fencing inside the gateway.  This
    legacy environment variable is therefore opt-in instead of defaulting to
    a 30-second whole-response wall clock.
    """

    raw = os.environ.get("KOLIBRI_PUBLIC_RESPONSE_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return None
    try:
        configured = float(raw)
    except ValueError:
        return None
    return max(5.0, min(configured, 3_600.0))


def _estimate_repair_classification(task: dict[str, Any]) -> dict[str, Any] | None:
    execution = task.get("execution") if isinstance(task.get("execution"), dict) else {}
    raw = (
        execution.get("proposal_validation")
        if isinstance(execution.get("proposal_validation"), dict)
        else {}
    )
    code = str(raw.get("code") or "")
    if code not in _ESTIMATE_REPAIRABLE_VALIDATION_CODES:
        return None
    fields = [
        value
        for value in raw.get("fields", [])
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", value)
    ][:8]
    error_types = [
        value
        for value in raw.get("error_types", [])
        if isinstance(value, str) and re.fullmatch(r"[a-z0-9_.]{1,80}", value)
    ][:8]
    return {
        "code": code,
        **({"fields": fields} if fields else {}),
        **({"error_types": error_types} if error_types else {}),
    }


def _estimate_repair_messages(
    context: list[dict[str, Any]], classification: dict[str, Any],
) -> list[dict[str, Any]]:
    safe_classification = json.dumps(
        classification, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    repair_instruction = (
        "Estimate contract repair: regenerate the requested estimate from the original typed "
        "request. The rejected draft is intentionally not included. Safe validation "
        f"classification: {safe_classification}. Follow the proposal_contract already present "
        "in system context exactly. Return one compact JSON object only. Never invent a source, "
        "URL, price, normative document or project input. If real sources are unavailable, "
        "return exactly the proposal_contract decline object."
    )
    return [{"role": "system", "content": repair_instruction}, *context]


def _complete_deterministic_estimate_fallback(
    *,
    session: dict[str, Any],
    body: ResponseCreate,
    response_id: str,
    base: dict[str, Any],
    context: list[dict[str, Any]],
    provider_routing: dict[str, Any],
    tool_execution: ResponseToolExecution,
    public_tools: list[dict[str, Any]],
    message_id: str | None = None,
) -> tuple[dict[str, Any], int] | None:
    """Complete a narrow estimate with a truthfully bound local engine.

    The caller invokes this after provider-route or source-tool exhaustion.
    This fallback contains no price template.  A failed current-source lookup
    therefore still produces the input editor and PDF checklist, while keeping
    all money absent until source evidence is supplied.
    """

    if body.task is None:
        return None
    task_payload = build_deterministic_estimate_fallback(
        body.task,
        reason=_provider_failure_reason(provider_routing),
    )
    if task_payload is None:
        return None
    try:
        task_payload = materialize_public_estimate_task(
            session=session,
            response_id=response_id,
            task=task_payload,
            request_metadata=body.metadata,
        )
    except EstimateArtifactError:
        # The editable calculation remains verified.  Artifact delivery stays
        # incomplete, and no PDF claim is made without persisted bytes.
        pass
    verification = deterministic_estimate_fallback_verification(task_payload)
    text = deterministic_estimate_fallback_text(task_payload)
    estimate_outcome = estimate_product_outcome(task_payload)
    verification = {**verification, "output_sha256": _sha256(text)}
    work_summary = build_work_summary(
        response_status="completed",
        task=task_payload,
        requested_tools=public_tools,
        tool_calls=tool_execution.tool_calls,
        citations=tool_execution.citations,
        verification=verification,
    )
    payload = {
        **base,
        "status": "completed",
        "completed_at": int(_now()),
        "output": [{
            "id": message_id or _opaque_id("msg"),
            "type": "message",
            "status": "completed",
            "role": "assistant",
            "content": [{
                "type": "output_text",
                "text": text,
                "annotations": [],
            }],
        }],
        "output_text": text,
        "verification": verification,
        "citations": tool_execution.citations,
        "tool_calls": tool_execution.tool_calls,
        "task": task_payload,
        **({"estimate_outcome": estimate_outcome} if estimate_outcome is not None else {}),
        "metadata": summary_metadata(base.get("metadata"), work_summary),
    }
    # Deterministic readiness/estimate fallbacks have no model-authored
    # reasoning summary.  Keep the verified work summary in metadata instead
    # of manufacturing a fake reasoning item.
    payload["learning_tap"] = _record_public_learning_tap(
        session=session,
        body=body,
        response_id=response_id,
        response_status="completed",
        response_text=text,
        verification=verification,
        provider_routing=provider_routing,
        tool_execution=tool_execution,
        task=task_payload,
    )
    payload = _STORE.finish_response(
        session["id"], response_id, payload, context, http_status=200,
    )
    return payload, 200


async def _complete_public_response(
    session: dict[str, Any],
    body: ResponseCreate,
    response_id: str,
    current_context: list[dict[str, Any]],
    requested_tools: list[dict[str, Any]],
    public_tools: list[dict[str, Any]],
    *,
    stream_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    message_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    context = list(current_context)
    if body.previous_response_id:
        previous = _STORE.get_response(session["id"], body.previous_response_id)
        if previous is None:
            raise HTTPException(status_code=404, detail="previous_response_not_found_in_session")
        _, previous_context, _ = previous
        context = [*previous_context, *context]
    if body.instructions:
        context.insert(0, {"role": "system", "content": body.instructions})
    calculation = None
    if body.task is not None:
        task_instructions, calculation = prepare_vertical_task(body.task)
        context.insert(0, {"role": "system", "content": task_instructions})
    if len(json.dumps(context, ensure_ascii=False).encode("utf-8")) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="response context exceeds 1 MiB")

    base = _response_shell(
        response_id,
        body,
        session["project_id"],
        status="in_progress",
        public_tools=public_tools,
    )
    provider_routing: dict[str, Any] = {}
    bounded_estimate = (
        isinstance(body.task, EstimateVerticalTask) and body.task.spec is None
    )
    estimate_deadline = (
        time.monotonic() + ESTIMATE_PROVIDER_TOTAL_BUDGET_SECONDS
        if bounded_estimate
        else None
    )
    tool_execution = ResponseToolExecution(
        provider_tools=requested_tools,
        provider_instructions=None,
        tool_calls=[],
        evidence=[],
        citations=[],
        attempts=[],
        formulalm_taps=[],
    )
    provider_reasoning_deltas: list[str] = []

    def provider_stream_callback(value: dict[str, Any]) -> None:
        safe = _safe_provider_stream_event(
            value,
            allow_text=False,
            allow_reasoning=body.reasoning.summary is not None,
        )
        if safe is not None and safe.get("type") == "reasoning_summary_delta":
            current_bytes = sum(len(item.encode("utf-8")) for item in provider_reasoning_deltas)
            delta = safe["delta"]
            if current_bytes + len(delta.encode("utf-8")) <= 65_536:
                provider_reasoning_deltas.append(delta)
        if stream_callback is not None:
            stream_callback(value)

    try:
        if requested_tools:
            tool_execution = await run_in_threadpool(partial(
                execute_response_tools,
                input_value=body.input,
                instructions=None,
                response_id=response_id,
                principal=f"public-session:{_sha256(session['id'])}",
                requested_tools=requested_tools,
                raw_tools=body.tools,
                project_id=session["project_id"],
                session_id=session["id"],
                estimate_task=(
                    body.task.model_dump(mode="json")
                    if isinstance(body.task, EstimateVerticalTask) else None
                ),
                cancel_event=cancel_event,
            ))
        if tool_execution.provider_tools and not bounded_estimate:
            raise WebSearchPolicyError("public_session_tool_not_allowed")
        execution_context = list(context)
        if tool_execution.provider_instructions:
            execution_context.insert(0, {
                "role": "system",
                "content": tool_execution.provider_instructions,
            })
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError
        initial_timeout = (
            min(
                ESTIMATE_PROVIDER_INITIAL_BUDGET_SECONDS,
                max(0.01, estimate_deadline - time.monotonic()),
            )
            if estimate_deadline is not None
            else _public_chat_timeout_seconds() if body.task is None else None
        )
        if isinstance(body.task, ImageVerticalTask):
            gateway = get_provider_gateway()
            generate_image = getattr(gateway, "generate_image", None)
            if not callable(generate_image):
                raise ProviderGatewayError({"error_type": "image_generation_unavailable"})
            completion = await run_in_threadpool(partial(
                generate_image,
                body.task.brief,
                response_id,
                event_callback=provider_stream_callback,
                cancel_event=cancel_event,
            ))
            if completion.status != "completed" or not completion.content:
                raise ProviderGatewayError(completion.technical)
            artifact, materialization = get_public_image_artifact_store().persist(
                session=session,
                response_id=response_id,
                content=completion.content,
                factory_binding_sha256=completion.factory_binding_sha256,
            )
            result = _image_factory_provider_result(
                completion=completion,
                artifact=artifact,
                materialization=materialization,
            )
        else:
            result = await _call_public_executor(
                messages=execution_context,
                model="kolibri",
                execution_mode=body.execution_mode,
                response_id=response_id,
                reasoning=body.reasoning.model_dump(mode="json"),
                **({"requested_tools": tool_execution.provider_tools} if tool_execution.provider_tools else {}),
                **({"timeout_seconds": initial_timeout} if initial_timeout is not None else {}),
                **({"stream_callback": provider_stream_callback} if (
                    stream_callback is not None or body.reasoning.summary is not None
                ) else {}),
                **({"cancel_event": cancel_event} if cancel_event is not None else {}),
            )
        if cancel_event is not None and cancel_event.is_set():
            raise asyncio.CancelledError
        provider_routing = _provider_routing(result)
        if body.task is not None:
            estimate_source_contract = (
                _estimate_source_contract(
                    routing=provider_routing,
                    tool_execution=tool_execution,
                )
                if bounded_estimate else {}
            )
            task_payload = build_vertical_result(
                body.task,
                result,
                calculation,
                **estimate_source_contract,
            )
            repair_classification = _estimate_repair_classification(task_payload)
            remaining = (
                estimate_deadline - time.monotonic()
                if estimate_deadline is not None
                else 0.0
            )
            if repair_classification is not None and remaining > 0.25:
                repair_timeout = min(ESTIMATE_PROVIDER_REPAIR_BUDGET_SECONDS, remaining)
                try:
                    repair_result = await _call_public_executor(
                        messages=_estimate_repair_messages(
                            execution_context, repair_classification,
                        ),
                        model="kolibri",
                        execution_mode=body.execution_mode,
                        response_id=f"{response_id}-repair",
                        reasoning=body.reasoning.model_dump(mode="json"),
                        timeout_seconds=repair_timeout,
                        **({"requested_tools": tool_execution.provider_tools} if tool_execution.provider_tools else {}),
                        **({"stream_callback": provider_stream_callback} if (
                            stream_callback is not None or body.reasoning.summary is not None
                        ) else {}),
                        **({"cancel_event": cancel_event} if cancel_event is not None else {}),
                    )
                except ProviderGatewayError:
                    # The first verified but invalid draft still provides a
                    # content-bound, truthful readiness result. A timed-out
                    # repair must not turn that bounded result into HTTP 503.
                    pass
                else:
                    repair_routing = _provider_routing(repair_result)
                    repair_source_contract = (
                        _estimate_source_contract(
                            routing=repair_routing,
                            tool_execution=tool_execution,
                        )
                        if bounded_estimate else {}
                    )
                    repair_task = build_vertical_result(
                        body.task,
                        repair_result,
                        calculation,
                        **repair_source_contract,
                    )
                    result = repair_result
                    task_payload = repair_task
                    provider_routing = repair_routing
            asserted_citations = _provider_asserted_public_citations(task_payload)
            if tool_execution.provider_tools:
                native_tool_calls = [
                    dict(item) for item in provider_routing.get("tool_calls", [])
                    if isinstance(item, dict)
                ]
                tool_execution = ResponseToolExecution(
                    provider_tools=tool_execution.provider_tools,
                    provider_instructions=tool_execution.provider_instructions,
                    tool_calls=[*tool_execution.tool_calls, *native_tool_calls],
                    evidence=[
                        *tool_execution.evidence,
                        *(
                            [dict(provider_routing["verifier_evidence"])]
                            if isinstance(provider_routing.get("verifier_evidence"), dict) else []
                        ),
                    ],
                    citations=asserted_citations,
                    attempts=[
                        *tool_execution.attempts,
                        *(
                            dict(item) for item in provider_routing.get("attempts", [])
                            if isinstance(item, dict)
                        ),
                    ],
                    formulalm_taps=tool_execution.formulalm_taps,
                )
            try:
                task_payload = materialize_public_estimate_task(
                    session=session,
                    response_id=response_id,
                    task=task_payload,
                    request_metadata=body.metadata,
                )
            except EstimateArtifactError:
                # The typed result may remain usable, but no artifact or saved
                # revision is claimed unless content-bound materialization
                # actually succeeded.
                pass
            result = {**result, "task": task_payload}
        public = verified_public_payload(result)
        public_task = public.get("task") if isinstance(public.get("task"), dict) else None
        readiness_result = (
            public_task.get("result")
            if isinstance(public_task, dict) and isinstance(public_task.get("result"), dict)
            else None
        )
        if isinstance(readiness_result, dict) and readiness_result.get("type") == "estimate_readiness":
            # The verified provider proposal remains hash-bound inside the task
            # proof, but its untrusted prices must never become public answer
            # text.  Present only the deterministic non-monetary gate summary.
            provider_output_verification = dict(public["verification"])
            text = deterministic_estimate_fallback_text(public_task)
            public["verification"] = {
                **deterministic_estimate_fallback_verification(public_task),
                "output_sha256": _sha256(text),
                "provider_output_sha256": provider_output_verification["output_sha256"],
                "provider_verifier_binding_sha256": provider_output_verification["binding_sha256"],
            }
        elif isinstance(readiness_result, dict) and readiness_result.get("type") == "deterministic_estimate":
            provider_output_verification = dict(public["verification"])
            text = deterministic_estimate_result_text(public_task)
            public["verification"] = {
                **deterministic_estimate_result_verification(public_task),
                "output_sha256": _sha256(text),
                "provider_output_sha256": provider_output_verification["output_sha256"],
                "provider_verifier_binding_sha256": provider_output_verification["binding_sha256"],
            }
        else:
            text = str(public["response"])
        message_id = message_id or _opaque_id("msg")
        payload = {
            **base,
            "status": "completed",
            "completed_at": int(_now()),
            "output": [{
                "id": message_id,
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [{
                    "type": "output_text",
                    "text": text,
                    "annotations": [],
                }],
            }],
            "output_text": text,
            "verification": public["verification"],
            "citations": tool_execution.citations,
            "tool_calls": tool_execution.tool_calls,
        }
        if isinstance(public.get("task"), dict):
            payload["task"] = public["task"]
            estimate_outcome = estimate_product_outcome(public["task"])
            if estimate_outcome is not None:
                payload["estimate_outcome"] = estimate_outcome
        work_summary = build_work_summary(
            response_status="completed",
            task=payload.get("task") or (
                body.task.model_dump(mode="json") if body.task is not None else None
            ),
            requested_tools=public_tools,
            tool_calls=tool_execution.tool_calls,
            citations=tool_execution.citations,
            verification=public["verification"],
        )
        payload["metadata"] = summary_metadata(base.get("metadata"), work_summary)
        _replace_reasoning_output(
            payload,
            response_id=response_id,
            body=body,
            deltas=provider_reasoning_deltas,
        )
        payload["learning_tap"] = _record_public_learning_tap(
            session=session,
            body=body,
            response_id=response_id,
            response_status="completed",
            response_text=text,
            verification=public["verification"],
            provider_routing=provider_routing,
            tool_execution=tool_execution,
            task=payload.get("task"),
        )
        payload = _STORE.finish_response(
            session["id"], response_id, payload, context, http_status=200,
        )
        return payload, 200
    except HTTPException:
        raise
    except WebSearchError as exc:
        http_status = 422 if isinstance(exc, WebSearchPolicyError) else 503
        if isinstance(exc, WebSearchError):
            tool_execution = ResponseToolExecution(
                provider_tools=[],
                provider_instructions=None,
                tool_calls=[],
                evidence=[],
                citations=[],
                attempts=list(getattr(exc, "attempts", []) or []),
                formulalm_taps=[],
            )
        fallback = _complete_deterministic_estimate_fallback(
            session=session,
            body=body,
            response_id=response_id,
            base=base,
            context=context,
            provider_routing={
                "error_type": exc.code,
                "attempts": tool_execution.attempts,
            },
            tool_execution=tool_execution,
            public_tools=public_tools,
            message_id=message_id,
        )
        if fallback is not None:
            return fallback
        payload = {
            **base,
            "status": "failed",
            "completed_at": int(_now()),
            "error": {
                "type": "tool_error",
                "code": exc.code,
                "message": "Kolibri web search could not produce verified evidence",
            },
            "citations": [],
            "tool_calls": [],
        }
        if body.task is not None:
            payload["task"] = failed_vertical_result(body.task, exc.code)
        work_summary = build_work_summary(
            response_status="failed",
            task=payload.get("task") or (
                body.task.model_dump(mode="json") if body.task is not None else None
            ),
            requested_tools=public_tools,
            tool_calls=[],
            citations=[],
            verification=None,
        )
        payload["metadata"] = summary_metadata(base.get("metadata"), work_summary)
        payload["output"] = []
        _replace_reasoning_output(
            payload,
            response_id=response_id,
            body=body,
            deltas=provider_reasoning_deltas,
        )
        payload["learning_tap"] = _record_public_learning_tap(
            session=session,
            body=body,
            response_id=response_id,
            response_status="failed",
            response_text="",
            verification=None,
            provider_routing=provider_routing,
            tool_execution=tool_execution,
            task=payload.get("task"),
        )
        payload = _STORE.finish_response(
            session["id"], response_id, payload, context, http_status=http_status,
        )
        return payload, http_status
    except Exception as exc:
        provider_routing = provider_routing or _provider_routing(
            getattr(exc, "technical", None)
        )
        if isinstance(exc, ProviderGatewayError):
            fallback = _complete_deterministic_estimate_fallback(
                session=session,
                body=body,
                response_id=response_id,
                base=base,
                context=context,
                provider_routing=provider_routing,
                tool_execution=tool_execution,
                public_tools=public_tools,
                message_id=message_id,
            )
            if fallback is not None:
                return fallback
        if isinstance(exc, PublicChatStreamError):
            failure = public_verification_failure()
        elif isinstance(exc, ProviderGatewayError):
            failure = public_provider_failure(
                provider_routing or getattr(exc, "technical", None)
            )
        else:
            failure = public_execution_failure()
        payload = {
            **base,
            "status": "failed",
            "completed_at": int(_now()),
            "error": failure,
            "citations": [],
            "tool_calls": [],
        }
        if body.task is not None:
            payload["task"] = failed_vertical_result(body.task, failure["code"])
        work_summary = build_work_summary(
            response_status="failed",
            task=payload.get("task") or (
                body.task.model_dump(mode="json") if body.task is not None else None
            ),
            requested_tools=public_tools,
            tool_calls=[],
            citations=[],
            verification=None,
        )
        payload["metadata"] = summary_metadata(base.get("metadata"), work_summary)
        payload["output"] = []
        _replace_reasoning_output(
            payload,
            response_id=response_id,
            body=body,
            deltas=provider_reasoning_deltas,
        )
        payload["learning_tap"] = _record_public_learning_tap(
            session=session,
            body=body,
            response_id=response_id,
            response_status="failed",
            response_text="",
            verification=None,
            provider_routing=provider_routing,
            tool_execution=tool_execution,
            task=payload.get("task"),
        )
        payload = _STORE.finish_response(
            session["id"], response_id, payload, context, http_status=503,
        )
        return payload, 503


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    sequence = payload.get("sequence_number")
    identifier = f"id: {int(sequence)}\n" if isinstance(sequence, int) else ""
    return (
        f"{identifier}event: {event_type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


_STREAM_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "incomplete"})
_STREAM_SAFE_STAGES = frozenset({
    "routing", "fallback", "queued", "leased", "running", "verifying",
})
_STREAM_SECRET_MARKER = re.compile(
    r"(?:bearer\s+[a-z0-9._~+/=-]{10,}|(?:sk|ghp|github_pat|xox[baprs])[-_][a-z0-9_-]{10,})",
    re.IGNORECASE,
)
_STREAM_PRIVATE_TOPOLOGY = re.compile(
    r"(?:\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|\b192\.168\.\d{1,3}\.\d{1,3}\b|"
    r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b|/home/|/users/)",
    re.IGNORECASE,
)


def _safe_provider_stream_event(
    value: Any,
    *,
    allow_text: bool,
    allow_reasoning: bool = False,
) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    event_type = str(value.get("type") or "").strip().lower()
    if event_type == "text_delta" and allow_text:
        delta = value.get("delta")
        if not isinstance(delta, str) or not delta or len(delta) > 65_536:
            return None
        delta = delta.replace("\x00", "")
        if not delta or _STREAM_SECRET_MARKER.search(delta) or _STREAM_PRIVATE_TOPOLOGY.search(delta):
            return None
        return {"type": "text_delta", "delta": delta}
    if event_type == "reasoning_summary_delta" and allow_reasoning:
        delta = value.get("delta")
        if not isinstance(delta, str) or not delta or len(delta) > 16_384:
            return None
        delta = delta.replace("\x00", "")
        if not delta or _STREAM_SECRET_MARKER.search(delta) or _STREAM_PRIVATE_TOPOLOGY.search(delta):
            return None
        return {"type": "reasoning_summary_delta", "delta": delta}
    if event_type == "status":
        stage = str(value.get("stage") or "").strip().lower()
        if stage in _STREAM_SAFE_STAGES:
            return {"type": "status", "stage": stage}
    if event_type == "tool":
        status = str(value.get("status") or "").strip().lower()
        if status in {"started", "completed"}:
            return {"type": "tool", "status": status}
    return None


@dataclass
class _PublicResponseRuntime:
    store: PublicResponseStore
    session_id: str
    response_id: str
    initial: dict[str, Any]
    message_id: str
    allow_text: bool
    allow_reasoning: bool
    queue_size: int = 256
    cancel_event: threading.Event = field(default_factory=threading.Event)
    streamed_text: str = ""
    reasoning_text: str = ""
    reasoning_started: bool = False
    task: asyncio.Task[Any] | None = None
    _consumer_task: asyncio.Task[Any] | None = None
    _queue: asyncio.Queue[dict[str, str] | None] = field(init=False)
    _loop: asyncio.AbstractEventLoop = field(init=False)
    _loop_thread_id: int = field(init=False)

    def __post_init__(self) -> None:
        self._queue = asyncio.Queue(maxsize=self.queue_size)
        self._loop = asyncio.get_running_loop()
        self._loop_thread_id = threading.get_ident()

    def publish(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.append_response_event(
            self.session_id,
            self.response_id,
            event_type,
            payload,
        )

    async def initialize(self) -> None:
        self._consumer_task = asyncio.create_task(self._consume_provider_events())
        created = {**self.initial, "status": "in_progress", "output": [], "error": None}
        self.publish("response.created", {
            "type": "response.created",
            "response": created,
        })
        self.publish("response.in_progress", {
            "type": "response.in_progress",
            "response": created,
        })
        # One real lifecycle event replaces the old burst of five synthetic
        # "plan/tool/source/check/verdict" cards.
        self.publish("response.status.updated", {
            "type": "response.status.updated",
            "response_id": self.response_id,
            "status": "in_progress",
            "stage": "routing",
        })
        self.publish("response.output_item.added", {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {
                "id": self.message_id,
                "type": "message",
                "status": "in_progress",
                "role": "assistant",
                "content": [],
            },
        })
        self.publish("response.content_part.added", {
            "type": "response.content_part.added",
            "item_id": self.message_id,
            "output_index": 0,
            "content_index": 0,
            "part": {"type": "output_text", "text": "", "annotations": []},
        })

    def provider_callback(self, value: dict[str, Any]) -> None:
        safe = _safe_provider_stream_event(
            value,
            allow_text=self.allow_text,
            allow_reasoning=self.allow_reasoning,
        )
        if safe is None or self.cancel_event.is_set():
            return
        if threading.get_ident() == self._loop_thread_id:
            try:
                self._queue.put_nowait(safe)
            except asyncio.QueueFull:
                # The provider remains authoritative.  The final done event
                # repairs delivery without inventing token fragments.
                return
            return
        future = asyncio.run_coroutine_threadsafe(self._queue.put(safe), self._loop)
        try:
            future.result(timeout=2.0)
        except Exception:
            future.cancel()

    async def _consume_provider_events(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                if event is None:
                    return
                if self.cancel_event.is_set():
                    continue
                if event["type"] == "text_delta":
                    delta = event["delta"]
                    self.streamed_text += delta
                    self.publish("response.output_text.delta", {
                        "type": "response.output_text.delta",
                        "item_id": self.message_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": delta,
                    })
                elif event["type"] == "status":
                    self.publish("response.status.updated", {
                        "type": "response.status.updated",
                        "response_id": self.response_id,
                        "status": "in_progress",
                        "stage": event["stage"],
                    })
                elif event["type"] == "reasoning_summary_delta":
                    if not self.reasoning_started:
                        self.reasoning_started = True
                        self.publish("response.output_item.added", {
                            "type": "response.output_item.added",
                            "output_index": 1,
                            "item": {
                                "id": f"rs_{self.response_id.rsplit('_', 1)[-1][:32]}",
                                "type": "reasoning",
                                "summary": [],
                            },
                        })
                        self.publish("response.reasoning_summary_part.added", {
                            "type": "response.reasoning_summary_part.added",
                            "item_id": f"rs_{self.response_id.rsplit('_', 1)[-1][:32]}",
                            "output_index": 1,
                            "summary_index": 0,
                            "part": {"type": "summary_text", "text": ""},
                        })
                    delta = event["delta"]
                    self.reasoning_text += delta
                    self.publish("response.reasoning_summary_text.delta", {
                        "type": "response.reasoning_summary_text.delta",
                        "item_id": f"rs_{self.response_id.rsplit('_', 1)[-1][:32]}",
                        "output_index": 1,
                        "summary_index": 0,
                        "delta": delta,
                    })
                elif event["type"] == "tool":
                    status = event["status"]
                    self.publish(f"response.tool.{status}", {
                        "type": f"response.tool.{status}",
                        "response_id": self.response_id,
                        "status": status,
                    })
            finally:
                self._queue.task_done()

    async def drain_provider_events(self) -> None:
        await self._queue.join()

    async def close(self) -> None:
        if self._consumer_task is None:
            return
        await self._queue.put(None)
        await self._consumer_task

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.task is not None and not self.task.done():
            self._loop.call_soon_threadsafe(self.task.cancel)

    def publish_terminal(self, final: dict[str, Any]) -> None:
        status = str(final.get("status") or "failed")
        if status == "cancelled":
            return
        final_summary = summary_from_metadata(final.get("metadata"))
        if final_summary is not None:
            self.publish("response.kolibri_work_summary.updated", {
                "type": "response.kolibri_work_summary.updated",
                "response_id": self.response_id,
                "active_kind": "verdict",
                "summary": final_summary,
            })
        if status != "completed":
            self.publish("response.failed", {
                "type": "response.failed",
                "response": final,
            })
            return

        message_index, message = next(
            (index, item)
            for index, item in enumerate(final.get("output") or [])
            if isinstance(item, dict) and item.get("type") == "message"
        )
        part = message["content"][0]
        final_text = str(part.get("text") or "")
        if final_text.startswith(self.streamed_text):
            suffix = final_text[len(self.streamed_text):]
            if suffix:
                self.streamed_text += suffix
                self.publish("response.output_text.delta", {
                    "type": "response.output_text.delta",
                    "item_id": self.message_id,
                    "output_index": message_index,
                    "content_index": 0,
                    "delta": suffix,
                })
        self.publish("response.output_text.done", {
            "type": "response.output_text.done",
            "item_id": self.message_id,
            "output_index": message_index,
            "content_index": 0,
            "text": final_text,
        })
        self.publish("response.content_part.done", {
            "type": "response.content_part.done",
            "item_id": self.message_id,
            "output_index": message_index,
            "content_index": 0,
            "part": part,
        })
        self.publish("response.output_item.done", {
            "type": "response.output_item.done",
            "output_index": message_index,
            "item": message,
        })
        reasoning = next((
            (index, item)
            for index, item in enumerate(final.get("output") or [])
            if isinstance(item, dict) and item.get("type") == "reasoning"
        ), None)
        if self.reasoning_started:
            reasoning_item = {
                "id": f"rs_{self.response_id.rsplit('_', 1)[-1][:32]}",
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": self.reasoning_text}],
            }
            output = [
                item for item in (final.get("output") or [])
                if not (isinstance(item, dict) and item.get("type") == "reasoning")
            ]
            output.append(reasoning_item)
            final = {**final, "output": output}
            reasoning_index = len(output) - 1
            self.publish("response.reasoning_summary_text.done", {
                "type": "response.reasoning_summary_text.done",
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": 0,
                "text": self.reasoning_text,
            })
            self.publish("response.reasoning_summary_part.done", {
                "type": "response.reasoning_summary_part.done",
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": 0,
                "part": reasoning_item["summary"][0],
            })
            self.publish("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": reasoning_index,
                "item": reasoning_item,
            })
        elif reasoning is not None:
            reasoning_index, reasoning_item = reasoning
            self.publish("response.output_item.added", {
                "type": "response.output_item.added",
                "output_index": reasoning_index,
                "item": {**reasoning_item, "summary": []},
            })
            for summary_index, summary_part in enumerate(reasoning_item.get("summary", [])):
                self.publish("response.reasoning_summary_part.added", {
                    "type": "response.reasoning_summary_part.added",
                    "item_id": reasoning_item["id"],
                    "output_index": reasoning_index,
                    "summary_index": summary_index,
                    "part": {"type": "summary_text", "text": ""},
                })
                self.publish("response.reasoning_summary_text.delta", {
                    "type": "response.reasoning_summary_text.delta",
                    "item_id": reasoning_item["id"],
                    "output_index": reasoning_index,
                    "summary_index": summary_index,
                    "delta": summary_part["text"],
                })
                self.publish("response.reasoning_summary_text.done", {
                    "type": "response.reasoning_summary_text.done",
                    "item_id": reasoning_item["id"],
                    "output_index": reasoning_index,
                    "summary_index": summary_index,
                    "text": summary_part["text"],
                })
                self.publish("response.reasoning_summary_part.done", {
                    "type": "response.reasoning_summary_part.done",
                    "item_id": reasoning_item["id"],
                    "output_index": reasoning_index,
                    "summary_index": summary_index,
                    "part": summary_part,
                })
            self.publish("response.output_item.done", {
                "type": "response.output_item.done",
                "output_index": reasoning_index,
                "item": reasoning_item,
            })
        task = final.get("task") if isinstance(final.get("task"), dict) else {}
        for artifact in task.get("artifacts", []) if isinstance(task.get("artifacts"), list) else []:
            if isinstance(artifact, dict) and artifact.get("status") == "materialized":
                self.publish("response.artifact.ready", {
                    "type": "response.artifact.ready",
                    "response_id": self.response_id,
                    "artifact": artifact,
                })
        self.publish("response.completed", {
            "type": "response.completed",
            "response": final,
        })


_ACTIVE_RESPONSE_RUNTIMES: dict[tuple[str, str], _PublicResponseRuntime] = {}
_ACTIVE_RESPONSE_RUNTIMES_LOCK = threading.RLock()


def _register_response_runtime(runtime: _PublicResponseRuntime) -> None:
    with _ACTIVE_RESPONSE_RUNTIMES_LOCK:
        _ACTIVE_RESPONSE_RUNTIMES[(runtime.session_id, runtime.response_id)] = runtime


def _response_runtime(session_id: str, response_id: str) -> _PublicResponseRuntime | None:
    with _ACTIVE_RESPONSE_RUNTIMES_LOCK:
        return _ACTIVE_RESPONSE_RUNTIMES.get((session_id, response_id))


def _unregister_response_runtime(runtime: _PublicResponseRuntime) -> None:
    with _ACTIVE_RESPONSE_RUNTIMES_LOCK:
        key = (runtime.session_id, runtime.response_id)
        if _ACTIVE_RESPONSE_RUNTIMES.get(key) is runtime:
            _ACTIVE_RESPONSE_RUNTIMES.pop(key, None)


async def _stored_response_sse(
    *,
    session_id: str,
    response_id: str,
    after_sequence: int,
):
    cursor = after_sequence
    keepalive_at = time.monotonic()
    while True:
        events = _STORE.list_response_events(
            session_id,
            response_id,
            after_sequence=cursor,
        )
        for event_type, payload in events:
            sequence = int(payload["sequence_number"])
            if sequence <= cursor:
                continue
            cursor = sequence
            yield _sse(event_type, payload)
        record = _STORE.get_response(session_id, response_id)
        if record is None:
            return
        terminal = str(record[0].get("status") or "") in _STREAM_TERMINAL_STATUSES
        runtime = _response_runtime(session_id, response_id)
        if terminal and runtime is None and not events:
            return
        now = time.monotonic()
        if now - keepalive_at >= 10.0:
            keepalive_at = now
            yield ": keep-alive\n\n"
        await asyncio.sleep(0.02)


def _last_event_sequence(request: Request, starting_after: Any = None) -> int:
    header = request.headers.get("Last-Event-ID")
    query = starting_after
    if query is None:
        query = request.query_params.get("starting_after")
    raw = header if header is not None and header.strip() else query
    if raw is None or not str(raw).strip():
        return -1
    try:
        value = int(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="last_event_id_invalid") from exc
    if value < -1:
        raise HTTPException(status_code=422, detail="last_event_id_invalid")
    if header is not None and header.strip() and query is not None:
        try:
            if int(header) != int(query):
                raise HTTPException(status_code=409, detail="event_cursor_conflict")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="last_event_id_invalid") from exc
    return value


async def _resumable_response_sse(
    initial: dict[str, Any],
    execute: Callable[[], Awaitable[tuple[dict[str, Any], int]]] | None,
    *,
    after_sequence: int,
):
    async for frame in _response_sse(initial, execute):
        first_line = frame.partition("\n")[0]
        if first_line.startswith("id: "):
            try:
                sequence = int(first_line.removeprefix("id: "))
            except ValueError:
                sequence = -1
            if sequence <= after_sequence:
                continue
        yield frame


async def _response_sse(
    initial: dict[str, Any],
    execute: Callable[[], Awaitable[tuple[dict[str, Any], int]]] | None,
):
    created = {**initial, "status": "in_progress", "output": [], "error": None}
    sequence = 0
    yield _sse("response.created", {
        "type": "response.created", "sequence_number": sequence, "response": created,
    })
    sequence += 1
    yield _sse("response.in_progress", {
        "type": "response.in_progress", "sequence_number": sequence, "response": created,
    })
    initial_summary = summary_from_metadata(created.get("metadata"))
    if execute is not None and initial_summary is not None:
        for item in initial_summary["items"]:
            sequence += 1
            yield _sse("response.kolibri_work_summary.updated", {
                "type": "response.kolibri_work_summary.updated",
                "sequence_number": sequence,
                "response_id": created["id"],
                "active_kind": item["kind"],
                "summary": initial_summary,
            })
    final, _ = await execute() if execute is not None else (initial, 200 if initial.get("status") == "completed" else 503)
    final_summary = summary_from_metadata(final.get("metadata"))
    if final_summary is not None:
        for item in final_summary["items"]:
            sequence += 1
            yield _sse("response.kolibri_work_summary.updated", {
                "type": "response.kolibri_work_summary.updated",
                "sequence_number": sequence,
                "response_id": final["id"],
                "active_kind": item["kind"],
                "summary": final_summary,
            })
    if final.get("status") != "completed":
        sequence += 1
        yield _sse("response.failed", {
            "type": "response.failed", "sequence_number": sequence, "response": final,
        })
        return

    message_index, item = next(
        (index, item)
        for index, item in enumerate(final["output"])
        if isinstance(item, dict) and item.get("type") == "message"
    )
    part = item["content"][0]
    sequence += 1
    yield _sse("response.output_item.added", {
        "type": "response.output_item.added", "sequence_number": sequence,
        "output_index": message_index, "item": {**item, "status": "in_progress", "content": []},
    })
    sequence += 1
    yield _sse("response.content_part.added", {
        "type": "response.content_part.added", "sequence_number": sequence,
        "item_id": item["id"], "output_index": message_index, "content_index": 0,
        "part": {"type": "output_text", "text": "", "annotations": []},
    })
    sequence += 1
    yield _sse("response.output_text.delta", {
        "type": "response.output_text.delta", "sequence_number": sequence,
        "item_id": item["id"], "output_index": message_index, "content_index": 0,
        "delta": part["text"],
    })
    sequence += 1
    yield _sse("response.output_text.done", {
        "type": "response.output_text.done", "sequence_number": sequence,
        "item_id": item["id"], "output_index": message_index, "content_index": 0,
        "text": part["text"],
    })
    sequence += 1
    yield _sse("response.content_part.done", {
        "type": "response.content_part.done", "sequence_number": sequence,
        "item_id": item["id"], "output_index": message_index, "content_index": 0, "part": part,
    })
    sequence += 1
    yield _sse("response.output_item.done", {
        "type": "response.output_item.done", "sequence_number": sequence,
        "output_index": message_index, "item": item,
    })

    reasoning = next((
        (index, output_item)
        for index, output_item in enumerate(final["output"])
        if isinstance(output_item, dict) and output_item.get("type") == "reasoning"
    ), None)
    if reasoning is not None:
        reasoning_index, reasoning_item = reasoning
        sequence += 1
        yield _sse("response.output_item.added", {
            "type": "response.output_item.added", "sequence_number": sequence,
            "output_index": reasoning_index,
            "item": {**reasoning_item, "summary": []},
        })
        for summary_index, summary_part in enumerate(reasoning_item.get("summary", [])):
            sequence += 1
            yield _sse("response.reasoning_summary_part.added", {
                "type": "response.reasoning_summary_part.added",
                "sequence_number": sequence,
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": summary_index,
                "part": {"type": "summary_text", "text": ""},
            })
            sequence += 1
            yield _sse("response.reasoning_summary_text.delta", {
                "type": "response.reasoning_summary_text.delta",
                "sequence_number": sequence,
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": summary_index,
                "delta": summary_part["text"],
            })
            sequence += 1
            yield _sse("response.reasoning_summary_text.done", {
                "type": "response.reasoning_summary_text.done",
                "sequence_number": sequence,
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": summary_index,
                "text": summary_part["text"],
            })
            sequence += 1
            yield _sse("response.reasoning_summary_part.done", {
                "type": "response.reasoning_summary_part.done",
                "sequence_number": sequence,
                "item_id": reasoning_item["id"],
                "output_index": reasoning_index,
                "summary_index": summary_index,
                "part": summary_part,
            })
        sequence += 1
        yield _sse("response.output_item.done", {
            "type": "response.output_item.done", "sequence_number": sequence,
            "output_index": reasoning_index, "item": reasoning_item,
        })
    task = final.get("task") if isinstance(final.get("task"), dict) else {}
    for artifact in task.get("artifacts", []) if isinstance(task.get("artifacts"), list) else []:
        if isinstance(artifact, dict) and artifact.get("status") == "materialized":
            sequence += 1
            yield _sse("response.artifact.ready", {
                "type": "response.artifact.ready",
                "sequence_number": sequence,
                "response_id": final["id"],
                "artifact": artifact,
            })
    sequence += 1
    yield _sse("response.completed", {
        "type": "response.completed", "sequence_number": sequence, "response": final,
    })


async def _run_public_response_runtime(
    runtime: _PublicResponseRuntime,
    *,
    session: dict[str, Any],
    body: ResponseCreate,
    messages: list[dict[str, Any]],
    requested_tools: list[dict[str, Any]],
    public_tools: list[dict[str, Any]],
) -> None:
    try:
        try:
            await _complete_public_response(
                session,
                body,
                runtime.response_id,
                messages,
                requested_tools,
                public_tools,
                stream_callback=runtime.provider_callback,
                cancel_event=runtime.cancel_event,
                message_id=runtime.message_id,
            )
        except asyncio.CancelledError:
            runtime.cancel_event.set()
            return
        except Exception:
            current = runtime.store.get_response(runtime.session_id, runtime.response_id)
            if current is not None and str(current[0].get("status") or "") not in _STREAM_TERMINAL_STATUSES:
                failure = public_execution_failure()
                failed = {
                    **runtime.initial,
                    "status": "failed",
                    "completed_at": int(_now()),
                    "error": failure,
                    "output": [],
                }
                runtime.store.finish_response(
                    runtime.session_id,
                    runtime.response_id,
                    failed,
                    messages,
                    http_status=503,
                )
        await runtime.drain_provider_events()
        authoritative = runtime.store.get_response(runtime.session_id, runtime.response_id)
        if authoritative is not None:
            runtime.publish_terminal(authoritative[0])
    finally:
        await runtime.close()
        _unregister_response_runtime(runtime)


async def _start_public_response_runtime(
    *,
    session: dict[str, Any],
    initial: dict[str, Any],
    body: ResponseCreate,
    messages: list[dict[str, Any]],
    requested_tools: list[dict[str, Any]],
    public_tools: list[dict[str, Any]],
) -> _PublicResponseRuntime:
    runtime = _PublicResponseRuntime(
        store=_STORE,
        session_id=session["id"],
        response_id=initial["id"],
        initial=initial,
        message_id=_opaque_id("msg"),
        # Typed tasks may transform a provider JSON proposal into a different
        # deterministic customer-facing result. Their provider text therefore
        # remains internal while safe execution stages still stream.
        allow_text=body.task is None,
        allow_reasoning=body.reasoning.summary is not None,
    )
    _register_response_runtime(runtime)
    try:
        await runtime.initialize()
        runtime.task = asyncio.create_task(_run_public_response_runtime(
            runtime,
            session=session,
            body=body,
            messages=messages,
            requested_tools=requested_tools,
            public_tools=public_tools,
        ))
    except Exception:
        _unregister_response_runtime(runtime)
        await runtime.close()
        raise
    return runtime


router = APIRouter(tags=["Kolibri Public Responses V1"])


@router.post("/v1/public/session")
def create_public_session(request: Request):
    origin = _required_origin(request)
    current = _optional_session(request, mutating=True)
    if current is not None:
        return JSONResponse(
            _session_payload(current),
            headers={"Cache-Control": "no-store"},
        )
    client = request.client.host if request.client else "unknown"
    if not _STORE.consume_rate(f"issue:{origin}:{client}", limit=20):
        raise HTTPException(status_code=429, detail="public_session_rate_limit_exceeded")
    ttl = _session_ttl_seconds()
    session, token = _STORE.issue(origin, ttl_seconds=ttl)
    payload = _session_payload(session)
    response = JSONResponse(payload, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=ttl,
        secure=origin.startswith("https://"),
        httponly=True,
        samesite="strict",
        path="/v1",
    )
    return response


@router.get("/v1/public/session")
def get_public_session(request: Request):
    # A cold browser start is discovery, not an authentication failure. Return
    # a non-cacheable inactive marker when no cookie was presented so the
    # Shell can issue its first session without producing a noisy expected 401
    # in DevTools. A syntactically valid but expired/revoked cookie still goes
    # through _require_session and remains a real 401 state transition.
    if not _session_cookie_candidates(request):
        return JSONResponse(
            {"object": "public.session", "active": False, "model": "kolibri"},
            headers={"Cache-Control": "no-store"},
        )
    session = _require_session(request, mutating=False)
    payload = _session_payload(session)
    # This response is bound to an opaque browser cookie.  It must never be
    # reused from a browser/proxy cache after the backing session has expired
    # or after an immutable backend release has replaced the session store.
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


def _public_session_for_mutation(request: Request) -> dict[str, Any]:
    _reject_owner_token_on_public_project_alias(request)
    if _owner_principal(request) is not None:
        raise HTTPException(status_code=405, detail="owner_project_mutation_not_supported")
    return _require_session(request, mutating=True)


def _reject_owner_token_on_public_project_alias(request: Request) -> None:
    """Keep `/v1/public/projects` strictly cookie/session scoped.

    The compatibility `/v1/projects` surface still delegates authenticated
    owner operations to the durable execution API.  Its explicit public
    namespace must never reinterpret an owner bearer token as a browser
    project operation, even when a public-session cookie is also present.
    """

    if (
        request.url.path.startswith("/v1/public/projects")
        and request.headers.get("Authorization", "").strip()
    ):
        raise HTTPException(
            status_code=403,
            detail="owner_authorization_not_allowed_on_public_route",
        )


@router.post("/v1/public/projects", status_code=201)
@router.post("/v1/projects", status_code=201)
def create_public_or_owner_project(body: dict[str, Any], request: Request):
    _reject_owner_token_on_public_project_alias(request)
    if _owner_principal(request) is not None:
        try:
            owner_body = ProjectCreate.model_validate(body)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from exc
        return create_owner_project(owner_body)
    session = _require_session(request, mutating=True)
    semantics = _project_create_semantics(body)
    key = _mutation_key(request, body)
    project, created = _STORE.create_project(
        session,
        project_id=_opaque_id("project_ephemeral"),
        idempotency_key=key,
        request_sha256=_json_hash(semantics),
        title=semantics["title"],
        metadata=semantics["metadata"],
    )
    return JSONResponse(
        project,
        status_code=201 if created else 200,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/v1/public/projects")
@router.get("/v1/projects")
def list_public_or_owner_projects(
    request: Request,
    include_deleted: bool = False,
):
    _reject_owner_token_on_public_project_alias(request)
    if _owner_principal(request) is not None:
        return list_owner_projects()
    session = _require_session(request, mutating=False)
    return JSONResponse(
        {
            "object": "list",
            "data": _STORE.list_projects(
                session["id"],
                include_deleted=include_deleted,
            ),
            "has_more": False,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/v1/public/projects/{project_id}")
@router.get("/v1/projects/{project_id}")
def get_public_or_owner_project(
    project_id: str,
    request: Request,
    include_deleted: bool = False,
):
    _reject_owner_token_on_public_project_alias(request)
    if _owner_principal(request) is not None:
        return get_owner_project(project_id)
    session = _require_session(request, mutating=False)
    project = _STORE.get_project(
        session["id"],
        project_id,
        include_deleted=include_deleted,
    )
    if project is None:
        raise HTTPException(status_code=404, detail="project_not_found")
    return JSONResponse(project, headers={"Cache-Control": "no-store"})


@router.patch("/v1/public/projects/{project_id}")
@router.post("/v1/public/projects/{project_id}")
@router.patch("/v1/projects/{project_id}")
@router.post("/v1/projects/{project_id}")
def update_public_project(project_id: str, body: dict[str, Any], request: Request):
    session = _public_session_for_mutation(request)
    _require_owned_project(session, project_id)
    semantics = _project_update_semantics(body)
    result = _STORE.update_project(
        session,
        project_id,
        idempotency_key=_mutation_key(request, body),
        request_sha256=_json_hash(semantics),
        title=semantics["title"],
        metadata=semantics["metadata"],
    )
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


def _set_public_project_deleted(
    project_id: str,
    request: Request,
    *,
    deleted: bool,
):
    session = _public_session_for_mutation(request)
    _require_owned_project(session, project_id, allow_deleted=True)
    operation = "delete" if deleted else "restore"
    result = _STORE.set_project_deleted(
        session,
        project_id,
        deleted=deleted,
        idempotency_key=_mutation_key(request),
        request_sha256=_json_hash({"project_id": project_id, "operation": operation}),
    )
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.delete("/v1/public/projects/{project_id}")
@router.post("/v1/public/projects/{project_id}/delete")
@router.delete("/v1/projects/{project_id}")
@router.post("/v1/projects/{project_id}/delete")
def delete_public_project(project_id: str, request: Request):
    return _set_public_project_deleted(project_id, request, deleted=True)


@router.post("/v1/public/projects/{project_id}/restore")
@router.post("/v1/projects/{project_id}/restore")
def restore_public_project(project_id: str, request: Request):
    return _set_public_project_deleted(project_id, request, deleted=False)


@router.get("/v1/public/projects/{project_id}/messages")
@router.get("/v1/projects/{project_id}/messages")
def list_public_project_messages(
    project_id: str,
    request: Request,
    include_deleted: bool = False,
):
    _reject_owner_token_on_public_project_alias(request)
    if _owner_principal(request) is not None:
        raise HTTPException(status_code=405, detail="owner_project_messages_not_supported")
    session = _require_session(request, mutating=False)
    _require_owned_project(session, project_id, allow_deleted=include_deleted)
    return JSONResponse(
        {
            "object": "list",
            "data": _STORE.list_messages(
                session["id"],
                project_id,
                include_deleted=include_deleted,
            ),
            "has_more": False,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/v1/public/projects/{project_id}/messages", status_code=201)
@router.post("/v1/projects/{project_id}/messages", status_code=201)
def create_public_project_message(
    project_id: str,
    body: dict[str, Any],
    request: Request,
):
    session = _public_session_for_mutation(request)
    _require_owned_project(session, project_id)
    semantics = _message_semantics(body, partial=False)
    _require_owned_response(session, project_id, semantics["response_id"])
    message, created = _STORE.create_message(
        session,
        project_id,
        message_id=_opaque_id("message"),
        idempotency_key=_mutation_key(request, body),
        request_sha256=_json_hash({
            key: value
            for key, value in semantics.items()
            if key != "response_id_supplied"
        }),
        role=semantics["role"],
        content=semantics["content"],
        status=semantics["status"],
        response_id=semantics["response_id"],
        metadata=semantics["metadata"],
    )
    return JSONResponse(
        message,
        status_code=201 if created else 200,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/v1/public/projects/{project_id}/messages/{message_id}")
@router.get("/v1/projects/{project_id}/messages/{message_id}")
def get_public_project_message(
    project_id: str,
    message_id: str,
    request: Request,
    include_deleted: bool = False,
):
    _reject_owner_token_on_public_project_alias(request)
    if _owner_principal(request) is not None:
        raise HTTPException(status_code=405, detail="owner_project_messages_not_supported")
    session = _require_session(request, mutating=False)
    _require_owned_project(session, project_id, allow_deleted=include_deleted)
    message = _STORE.get_message(
        session["id"],
        project_id,
        message_id,
        include_deleted=include_deleted,
    )
    if message is None:
        raise HTTPException(status_code=404, detail="message_not_found")
    return JSONResponse(message, headers={"Cache-Control": "no-store"})


@router.patch("/v1/public/projects/{project_id}/messages/{message_id}")
@router.post("/v1/public/projects/{project_id}/messages/{message_id}")
@router.patch("/v1/projects/{project_id}/messages/{message_id}")
@router.post("/v1/projects/{project_id}/messages/{message_id}")
def update_public_project_message(
    project_id: str,
    message_id: str,
    body: dict[str, Any],
    request: Request,
):
    session = _public_session_for_mutation(request)
    _require_owned_project(session, project_id)
    if _STORE.get_message(session["id"], project_id, message_id) is None:
        raise HTTPException(status_code=404, detail="message_not_found")
    semantics = _message_semantics(body, partial=True)
    if semantics["response_id_supplied"]:
        _require_owned_response(session, project_id, semantics["response_id"])
    result = _STORE.update_message(
        session,
        project_id,
        message_id,
        idempotency_key=_mutation_key(request, body),
        request_sha256=_json_hash({
            key: value
            for key, value in semantics.items()
            if key not in {"role", "response_id_supplied"}
        }),
        content=semantics["content"],
        status=semantics["status"],
        response_id=semantics["response_id"],
        response_id_supplied=semantics["response_id_supplied"],
        metadata=semantics["metadata"],
    )
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


def _set_public_message_deleted(
    project_id: str,
    message_id: str,
    request: Request,
    *,
    deleted: bool,
):
    session = _public_session_for_mutation(request)
    _require_owned_project(session, project_id, allow_deleted=True)
    if _STORE.get_message(
        session["id"], project_id, message_id, include_deleted=True,
    ) is None:
        raise HTTPException(status_code=404, detail="message_not_found")
    operation = "delete" if deleted else "restore"
    result = _STORE.set_message_deleted(
        session,
        project_id,
        message_id,
        deleted=deleted,
        idempotency_key=_mutation_key(request),
        request_sha256=_json_hash({
            "project_id": project_id,
            "message_id": message_id,
            "operation": operation,
        }),
    )
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.delete("/v1/public/projects/{project_id}/messages/{message_id}")
@router.post("/v1/public/projects/{project_id}/messages/{message_id}/delete")
@router.delete("/v1/projects/{project_id}/messages/{message_id}")
@router.post("/v1/projects/{project_id}/messages/{message_id}/delete")
def delete_public_project_message(
    project_id: str,
    message_id: str,
    request: Request,
):
    return _set_public_message_deleted(
        project_id, message_id, request, deleted=True,
    )


@router.post("/v1/public/projects/{project_id}/messages/{message_id}/restore")
@router.post("/v1/projects/{project_id}/messages/{message_id}/restore")
def restore_public_project_message(
    project_id: str,
    message_id: str,
    request: Request,
):
    return _set_public_message_deleted(
        project_id, message_id, request, deleted=False,
    )


@router.post("/v1/responses")
async def create_public_or_owner_response(body: ResponseCreate, request: Request):
    after_sequence = _last_event_sequence(request) if body.stream else -1
    owner = _owner_principal(request)
    if owner is not None:
        owner_body = body.model_copy(update={"stream": False})
        response = _decorate_response_work_summary(
            await run_in_threadpool(create_owner_response, owner_body, request)
        )
        if not body.stream:
            return response
        return StreamingResponse(
            _resumable_response_sse(
                response, None, after_sequence=after_sequence,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )

    session = _require_session(request, mutating=True)
    if body.workstream_id:
        raise HTTPException(status_code=403, detail="public_session_durable_scope_forbidden")
    if body.project_id and not body.project_id.startswith("project_ephemeral_"):
        raise HTTPException(status_code=403, detail="public_session_durable_scope_forbidden")
    selected_project_id = body.project_id or session["project_id"]
    _require_owned_project(session, selected_project_id)
    response_session = {**session, "project_id": selected_project_id}
    requested_materialized = (
        "image"
        if isinstance(body.task, ImageVerticalTask)
        else requested_materialized_capability(body.input)
    )
    if requested_materialized == "image":
        if body.task is None:
            prompt = _latest_user_text(body.input)
            if not prompt:
                raise HTTPException(status_code=422, detail="image_prompt_required")
            body = body.model_copy(update={
                "task": ImageVerticalTask(intent="image", brief=prompt),
            })
        elif not isinstance(body.task, ImageVerticalTask):
            raise HTTPException(status_code=422, detail="materialized_task_intent_mismatch")
    blocked_materialized: str | None = None
    if requested_materialized is not None:
        provider_gateway = get_provider_gateway()
        product_matrix = build_product_capability_matrix(
            routes=request.app.routes,
            capability_envelope=get_capability_gateway().envelope(),
            provider_health=verified_provider_health(provider_gateway),
            built_in_tools={
                "tool:image_generation": callable(
                    getattr(provider_gateway, "generate_image", None),
                ),
            },
        )
        product_record = next((
            item for item in product_matrix["data"]
            if item.get("id") == requested_materialized
        ), None)
        if not isinstance(product_record, dict) or product_record.get("available") is not True:
            # Image generation has a safe bootstrap path: a fresh dynamic
            # Home worker may run the first fenced canary even before the
            # public menu is promoted.  Completion still requires validated
            # bytes and a persisted artifact.  No other materialized route is
            # allowed to bypass its release capability matrix.
            image_invocable = getattr(provider_gateway, "image_route_invocable", None)
            if not (
                requested_materialized == "image"
                and callable(image_invocable)
                and await run_in_threadpool(image_invocable)
            ):
                blocked_materialized = requested_materialized
    requested_tools, public_tools = _validate_public_tools(body.tools)
    if (
        isinstance(body.task, EstimateVerticalTask)
        and body.task.spec is None
        and not requested_tools
    ):
        # A price-bearing construction estimate must research current sources
        # even when the Shell did not expose a manual web-search toggle.  The
        # same capability gateway still has to authorize the built-in tool; if
        # it is unavailable the later typed estimate gate remains money-free.
        try:
            requested_tools, public_tools = _validate_public_tools([{
                "type": "web_search",
                "search_context_size": "high",
            }])
        except HTTPException:
            requested_tools, public_tools = [], []
    if not _STORE.consume_rate(f"response:{session['id']}", limit=_response_rate_limit()):
        raise HTTPException(status_code=429, detail="public_session_rate_limit_exceeded")

    messages = _input_messages(body.input)
    if body.previous_response_id:
        previous = _STORE.get_response(session["id"], body.previous_response_id)
        if previous is None:
            raise HTTPException(status_code=404, detail="previous_response_not_found_in_session")
        if previous[0].get("project_id") != selected_project_id:
            raise HTTPException(
                status_code=409,
                detail="previous_response_belongs_to_another_project",
            )
    idempotency_key = _request_key(body, request)
    response_id = _opaque_id("resp")
    initial = _response_shell(
        response_id,
        body,
        selected_project_id,
        status="in_progress",
        public_tools=public_tools,
    )
    existing, created, existing_status = _STORE.begin_response(
        response_session,
        response_id=response_id,
        idempotency_key=idempotency_key,
        request_sha256=_json_hash(_request_semantics(body)),
        payload=initial,
        context=messages,
    )
    if not created:
        if existing.get("status") == "in_progress" and not body.stream:
            raise HTTPException(status_code=409, detail="idempotent_response_still_in_progress")
        if body.stream:
            stored_events = _STORE.list_response_events(
                session["id"], existing["id"], after_sequence=-1,
            )
            return StreamingResponse(
                _stored_response_sse(
                    session_id=session["id"],
                    response_id=existing["id"],
                    after_sequence=after_sequence,
                ) if stored_events or existing.get("status") == "in_progress" else
                _resumable_response_sse(existing, None, after_sequence=after_sequence),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
            )
        return JSONResponse(existing, status_code=existing_status, headers={"Cache-Control": "no-store"})

    if blocked_materialized is not None:
        # Text that says an image/file was created is not a deliverable.  Fail
        # before invoking a text provider, so no provider prose can become a
        # false terminal success while the typed artifact route is unavailable.
        failed = {
            **initial,
            "status": "failed",
            "completed_at": int(_now()),
            "output": [],
            "error": {
                "type": "capability_error",
                "code": "capability_unavailable",
                "message": "Запрошенный материализованный результат сейчас недоступен.",
            },
        }
        failed["metadata"] = summary_metadata(
            initial.get("metadata"),
            build_work_summary(
                response_status="failed",
                requested_tools=public_tools,
            ),
        )
        failed = _STORE.finish_response(
            session["id"], response_id, failed, messages, http_status=503,
        )
        if body.stream:
            return StreamingResponse(
                _resumable_response_sse(
                    failed, None, after_sequence=after_sequence,
                ),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
            )
        return JSONResponse(failed, status_code=503, headers={"Cache-Control": "no-store"})

    async def execute() -> tuple[dict[str, Any], int]:
        return await _complete_public_response(
            response_session,
            body,
            response_id,
            messages,
            requested_tools,
            public_tools,
        )

    if body.stream or body.background:
        await _start_public_response_runtime(
            session=response_session,
            initial=initial,
            body=body,
            messages=messages,
            requested_tools=requested_tools,
            public_tools=public_tools,
        )
    if body.stream:
        return StreamingResponse(
            _stored_response_sse(
                session_id=session["id"],
                response_id=response_id,
                after_sequence=after_sequence,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )
    if body.background:
        return JSONResponse(initial, status_code=200, headers={"Cache-Control": "no-store"})
    payload, http_status = await execute()
    return JSONResponse(payload, status_code=http_status, headers={"Cache-Control": "no-store"})


@router.get("/v1/responses")
def list_public_or_owner_responses(request: Request, project_id: str | None = None):
    if _owner_principal(request) is not None:
        result = list_owner_responses()
        return {
            **result,
            "data": [
                _decorate_response_work_summary(item)
                for item in result.get("data", [])
                if isinstance(item, dict)
            ],
        }
    session = _require_session(request, mutating=False)
    if project_id is not None:
        _require_owned_project(session, project_id)
    return {
        "object": "list",
        "data": _STORE.list_responses(session["id"], project_id=project_id),
        "has_more": False,
    }


@router.get("/v1/responses/{response_id}")
def get_public_or_owner_response(
    response_id: str,
    request: Request,
    stream: bool = Query(default=False),
    starting_after: int | None = Query(default=None, ge=-1),
):
    if _owner_principal(request) is not None:
        payload = _decorate_response_work_summary(get_owner_response(response_id))
        if not stream:
            return payload
        return StreamingResponse(
            _resumable_response_sse(
                payload,
                None,
                after_sequence=_last_event_sequence(request, starting_after),
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )
    session = _require_session(request, mutating=False)
    record = _STORE.get_response(session["id"], response_id)
    if record is None:
        raise HTTPException(status_code=404, detail="response_not_found")
    if stream:
        after_sequence = _last_event_sequence(request, starting_after)
        stored_events = _STORE.list_response_events(
            session["id"], response_id, after_sequence=-1,
        )
        return StreamingResponse(
            _stored_response_sse(
                session_id=session["id"],
                response_id=response_id,
                after_sequence=after_sequence,
            ) if stored_events or record[0].get("status") == "in_progress" else
            _resumable_response_sse(record[0], None, after_sequence=after_sequence),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
        )
    return record[0]


@router.get("/v1/responses/{response_id}/events")
async def list_public_or_owner_response_events(response_id: str, request: Request):
    if _owner_principal(request) is not None:
        return list_owner_response_events(response_id, request)
    session = _require_session(request, mutating=False)
    record = _STORE.get_response(session["id"], response_id)
    if record is None:
        raise HTTPException(status_code=404, detail="response_not_found")
    payload, _, _ = record
    after_sequence = _last_event_sequence(request)
    all_stored_events = _STORE.list_response_events(
        session["id"], response_id, after_sequence=-1,
    )
    stored_events = _STORE.list_response_events(
        session["id"], response_id, after_sequence=after_sequence,
    )
    if "text/event-stream" in request.headers.get("Accept", ""):
        return StreamingResponse(
            _stored_response_sse(
                session_id=session["id"],
                response_id=response_id,
                after_sequence=after_sequence,
            ) if all_stored_events or payload.get("status") == "in_progress" else
            _resumable_response_sse(payload, None, after_sequence=after_sequence),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store, no-transform",
                "X-Accel-Buffering": "no",
            },
        )
    if all_stored_events:
        return JSONResponse(
            {"object": "list", "data": [item for _, item in stored_events], "has_more": False},
            headers={"Cache-Control": "no-store"},
        )
    events: list[dict[str, Any]] = []
    async for frame in _resumable_response_sse(
        payload,
        None,
        after_sequence=after_sequence,
    ):
        data_line = next(
            (line for line in frame.splitlines() if line.startswith("data: ")),
            None,
        )
        if data_line is not None:
            events.append(json.loads(data_line.removeprefix("data: ")))
    return JSONResponse(
        {"object": "list", "data": events, "has_more": False},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/v1/responses/{response_id}/input_items")
def list_public_or_owner_response_input_items(
    response_id: str,
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    order: Literal["asc", "desc"] = "desc",
    after: str | None = None,
    include: list[str] | None = Query(default=None),
):
    if _owner_principal(request) is not None:
        return list_owner_response_input_items(
            response_id=response_id,
            limit=limit,
            order=order,
            after=after,
            include=include,
        )
    session = _require_session(request, mutating=False)
    input_items = _STORE.get_response_input(session["id"], response_id)
    payload = response_input_item_list(
        response_id,
        input_items,
        limit=limit,
        order=order,
        after=after,
    )
    return JSONResponse(payload, headers={"Cache-Control": "no-store"})


@router.post("/v1/responses/{response_id}/cancel")
def cancel_public_or_owner_response(response_id: str, request: Request):
    if _owner_principal(request) is not None:
        return _decorate_response_work_summary(cancel_owner_response(response_id))
    session = _require_session(request, mutating=True)
    cancelled = _STORE.cancel_response(session["id"], response_id)
    runtime = _response_runtime(session["id"], response_id)
    if runtime is not None and cancelled.get("status") == "cancelled":
        runtime.cancel()
    return cancelled
