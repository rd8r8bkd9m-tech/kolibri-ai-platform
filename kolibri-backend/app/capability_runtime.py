"""Canonical runtime composition for Kolibri backend capabilities.

``capability_registry`` contains the fail-closed evaluation rules.  This
module connects those rules to the backend's real providers, renderers and
tool invocations.  A route being imported or a credential being present is
configuration evidence only; it does not promote a capability to
``available`` until a successful bounded invocation has been recorded.

The invocation ledger deliberately contains no prompts, document bytes,
credentials or upstream error text.  It is safe to share between backend
processes and survives process restarts.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows desktop wrapper fallback.
    fcntl = None

from app.capability_registry import (
    CapabilityEvidence,
    CapabilityRegistry,
    CapabilitySpec,
    CredentialEvidence,
    InvocationProbe,
    PolicyEvidence,
    ProbeState,
    RendererEvidence,
    RouteEvidence,
)


logger = logging.getLogger(__name__)
_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_.-]{1,79}$")
_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_PUBLIC_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_PROBE_LEDGER_SCHEMA = "kolibri.capability-probes.v2"
_DEFAULT_PROBE_TTL_SECONDS = 7 * 60 * 60
_MIN_PROBE_TTL_SECONDS = 60
_MAX_PROBE_TTL_SECONDS = 7 * 24 * 60 * 60
_lock = RLock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _release_id() -> str:
    value = os.getenv("KOLIBRI_RELEASE_ID", "unversioned").strip() or "unversioned"
    if _RELEASE_ID.fullmatch(value):
        return value
    # Fail closed without copying an arbitrary environment value into evidence.
    return f"invalid-{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def capability_release_id() -> str:
    """Return the sanitised release identity that owns runtime probe evidence."""

    return _release_id()


def capability_probe_ttl_seconds(override_env: str | None = None) -> int:
    """Return a bounded runtime proof TTL.

    Production pins the general value above the 60-minute soak and the six-hour
    capability campaign interval.  A route-specific variable may override it,
    but invalid values never crash registry reads or silently shorten the
    release proof window.
    """

    names = tuple(
        name
        for name in (override_env, "KOLIBRI_CAPABILITY_PROBE_TTL_SECONDS")
        if name
    )
    for name in names:
        raw = os.getenv(name, "").strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if _MIN_PROBE_TTL_SECONDS <= value <= _MAX_PROBE_TTL_SECONDS:
            return value
    return _DEFAULT_PROBE_TTL_SECONDS


def _probe_path() -> Path:
    configured = os.getenv("KOLIBRI_CAPABILITY_PROBE_FILE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root = Path(os.getenv("KOLIBRI_ARTIFACT_DIR", "./data/artifacts")).expanduser().resolve()
    # Canary releases may intentionally share an artifact root.  Evidence is
    # release-bound, so its default storage must be release-scoped as well;
    # otherwise the most recent canary overwrites every other release's proof.
    return root / "runtime" / "capability-probes" / f"{_release_id()}.json"


@contextmanager
def _ledger_lock() -> Iterator[None]:
    path = _probe_path()
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o640)
    try:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _read_ledger_unlocked() -> dict[str, dict[str, Any]]:
    path = _probe_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    release_id = _release_id()
    if (
        not isinstance(raw, dict)
        or raw.get("schema_version") != _PROBE_LEDGER_SCHEMA
        or raw.get("release_id") != release_id
    ):
        return {}
    probes = raw.get("probes")
    if not isinstance(probes, dict):
        return {}
    return {
        str(key): dict(value)
        for key, value in probes.items()
        if (
            isinstance(key, str)
            and _CAPABILITY_ID.fullmatch(key)
            and isinstance(value, dict)
            and value.get("release_id") == release_id
        )
    }


def _write_ledger_unlocked(probes: dict[str, dict[str, Any]]) -> None:
    path = _probe_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "schema_version": _PROBE_LEDGER_SCHEMA,
            "release_id": _release_id(),
            "updated_at": _now().isoformat(),
            "probes": probes,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
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
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def record_capability_invocation(
    capability_id: str,
    *,
    succeeded: bool,
    error_code: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    evidence_id: str | None = None,
) -> None:
    """Persist a sanitised invocation verdict for a concrete capability."""

    if not _CAPABILITY_ID.fullmatch(capability_id):
        raise ValueError("invalid capability id")
    safe_error = None if succeeded else re.sub(r"[^a-z0-9_.-]", "_", str(error_code or "invocation_failed").lower())[:80]
    safe_provider = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(provider or ""))[:80] or None
    safe_model = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(model or ""))[:120] or None
    safe_evidence = re.sub(r"[^a-zA-Z0-9_.:-]", "_", str(evidence_id or ""))[:160] or None
    with _ledger_lock():
        probes = _read_ledger_unlocked()
        probes[capability_id] = {
            "release_id": _release_id(),
            "state": "succeeded" if succeeded else "failed",
            "checked_at": _now().isoformat(),
            "error_code": safe_error,
            "provider": safe_provider,
            "model": safe_model,
            "evidence_id": safe_evidence,
        }
        _write_ledger_unlocked(probes)


def try_record_capability_invocation(
    capability_id: str,
    *,
    succeeded: bool,
    error_code: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    evidence_id: str | None = None,
) -> bool:
    """Best-effort wrapper for optional runtime evidence writes."""

    try:
        record_capability_invocation(
            capability_id,
            succeeded=succeeded,
            error_code=error_code,
            provider=provider,
            model=model,
            evidence_id=evidence_id,
        )
    except Exception:
        logger.exception("Capability evidence write failed for %s", capability_id)
        return False
    return True


def capability_invocation_probe(
    capability_id: str,
    *,
    ttl_seconds: int | None = None,
) -> InvocationProbe:
    with _ledger_lock():
        record = _read_ledger_unlocked().get(capability_id, {})
    state_value = str(record.get("state") or "never")
    state = ProbeState(state_value) if state_value in {item.value for item in ProbeState} else ProbeState.NEVER
    checked_at = _parse_time(record.get("checked_at")) if state is not ProbeState.NEVER else None
    if state is not ProbeState.NEVER and checked_at is None:
        state = ProbeState.NEVER
    return InvocationProbe(
        state=state,
        checked_at=checked_at,
        ttl_seconds=(
            capability_probe_ttl_seconds()
            if ttl_seconds is None
            else max(_MIN_PROBE_TTL_SECONDS, min(int(ttl_seconds), _MAX_PROBE_TTL_SECONDS))
        ),
        evidence_id=str(record.get("evidence_id") or "") or None,
        error_code=str(record.get("error_code") or "") or None,
        provider=str(record.get("provider") or "") or None,
        model=str(record.get("model") or "") or None,
    )


def _policy(capability_id: str) -> PolicyEvidence:
    disabled = {
        item.strip()
        for item in os.getenv("KOLIBRI_DISABLED_CAPABILITIES", "").split(",")
        if item.strip()
    }
    permitted = capability_id not in disabled
    return PolicyEvidence(
        evaluated=True,
        permitted=permitted,
        decision_id="backend-capability-policy-v1",
        checked_at=_now(),
        reason_code=None if permitted else "capability_disabled",
    )


def _renderer(capability_id: str, renderer_id: str | None, *, required: bool) -> RendererEvidence | None:
    if not required:
        return None
    probe = capability_invocation_probe(capability_id)
    registered = renderer_id is not None
    healthy = True if registered and probe.state is ProbeState.SUCCEEDED else None
    return RendererEvidence(
        renderer_id=renderer_id,
        registered=registered,
        healthy=healthy,
        checked_at=probe.checked_at,
        evidence_id=probe.evidence_id,
    )


def _internal_evidence(
    capability_id: str,
    *,
    configured: bool,
    renderer_id: str | None,
    renderer_required: bool = True,
    credential_required: bool = False,
    credential_present: bool = True,
    route_id: str = "kolibri-backend",
) -> CapabilityEvidence:
    checked = _now()
    return CapabilityEvidence(
        policy=_policy(capability_id),
        renderer=_renderer(capability_id, renderer_id, required=renderer_required),
        routes=(
            RouteEvidence(
                route_id=route_id,
                configured=configured,
                permitted=True,
                credential=CredentialEvidence(
                    required=credential_required,
                    present=credential_present,
                    source="server_runtime" if credential_required else "not_required",
                    checked_at=checked,
                    reason_code=None if credential_present else "credential_missing",
                ),
                probe=capability_invocation_probe(capability_id),
            ),
        ),
    )


def _text_provider_evidence(capability_id: str) -> CapabilityEvidence:
    from app.ai_provider import PROVIDERS, provider_route_snapshot

    routes: list[RouteEvidence] = []
    for provider in PROVIDERS.values():
        snapshot = provider_route_snapshot(provider)
        status = str(snapshot.get("status") or "unavailable")
        checked_at = _parse_time(snapshot.get("verified_at"))
        if status == "live" and checked_at:
            probe_state = ProbeState.SUCCEEDED
        elif status == "blocked" and checked_at:
            probe_state = ProbeState.FAILED
        else:
            probe_state = ProbeState.NEVER
            checked_at = None
        configured = bool(snapshot.get("configured"))
        routes.append(
            RouteEvidence(
                route_id=str(snapshot.get("id") or "provider"),
                configured=configured,
                permitted=bool(provider.get("routable", True)),
                credential=CredentialEvidence(
                    required=True,
                    present=configured,
                    source=str(snapshot.get("credential_source") or "unknown"),
                    checked_at=_now(),
                    reason_code=None if configured else "credential_or_route_missing",
                ),
                probe=InvocationProbe(
                    state=probe_state,
                    checked_at=checked_at,
                    ttl_seconds=capability_probe_ttl_seconds("KOLIBRI_TEXT_PROBE_TTL_SECONDS"),
                    error_code=str(snapshot.get("failure_kind") or "") or None,
                    provider=str(snapshot.get("id") or "") or None,
                    model=str(snapshot.get("model") or "") or None,
                ),
            )
        )
    if capability_id in {"developer.responses", "developer.chat_completions"}:
        # Provider health proves that an inference route exists, but it does
        # not prove that a particular public HTTP contract accepted, executed
        # and returned a valid response. Developer endpoints therefore expose
        # only their own persisted end-to-end probe. This prevents one
        # successful Responses request from silently advertising Chat
        # Completions (or vice versa).
        endpoint_configured = any(
            route.configured
            and route.permitted
            and route.credential.source_permitted
            and (not route.credential.required or route.credential.present)
            for route in routes
        )
        return CapabilityEvidence(
            policy=_policy(capability_id),
            renderer=None,
            routes=(
                RouteEvidence(
                    route_id=f"kolibri-public-{capability_id}",
                    configured=endpoint_configured,
                    permitted=True,
                    credential=CredentialEvidence(
                        required=False,
                        present=True,
                        source="not_required",
                        checked_at=_now(),
                    ),
                    probe=capability_invocation_probe(capability_id),
                ),
            ),
        )
    # The public endpoint itself is a concrete route.  Its persisted probe is
    # updated only after a terminal successful response, so a process restart
    # does not erase valid evidence and a configured provider alone still does
    # not prove the public contract.
    routes.append(
        RouteEvidence(
            route_id="kolibri-public-response",
            configured=True,
            permitted=True,
            credential=CredentialEvidence(
                required=False,
                present=True,
                source="not_required",
                checked_at=_now(),
            ),
            probe=capability_invocation_probe(capability_id),
        )
    )
    return CapabilityEvidence(policy=_policy(capability_id), renderer=None, routes=tuple(routes))


def _project_builder_evidence(capability_id: str) -> CapabilityEvidence:
    """Bind project builders to configured AI routes and their own live probe.

    A successful chat request is not proof that the provider returned a safe,
    persisted project ZIP.  Every route therefore uses the capability-specific
    probe written only after project JSON validation, CAS persistence and
    artifact re-open succeed.
    """

    provider_evidence = _text_provider_evidence(capability_id)
    project_probe = capability_invocation_probe(capability_id)
    routes = tuple(
        RouteEvidence(
            route_id=route.route_id,
            configured=route.configured,
            permitted=route.permitted,
            credential=route.credential,
            probe=project_probe,
        )
        for route in provider_evidence.routes
        if route.route_id != "kolibri-public-response"
    )
    renderer = RendererEvidence(
        renderer_id="project_preview",
        registered=True,
        healthy=True if project_probe.state is ProbeState.SUCCEEDED else None,
        checked_at=project_probe.checked_at,
        evidence_id=project_probe.evidence_id,
    )
    return CapabilityEvidence(
        policy=_policy(capability_id),
        renderer=renderer,
        routes=routes,
    )


def _image_evidence(capability_id: str = "image.generate") -> CapabilityEvidence:
    from app.image_artifacts import image_capability

    if capability_id == "image.edit":
        # Editing shares the configured image execution route, but it has a
        # distinct end-to-end proof.  A successful generation must never
        # advertise editing until source bytes were opened, edited, persisted
        # as a new immutable revision, and reopened successfully.
        legacy = image_capability()
        route = legacy.get("route") if isinstance(legacy.get("route"), dict) else {}
        probe = capability_invocation_probe(capability_id)
        renderer = RendererEvidence(
            renderer_id="image",
            registered=True,
            healthy=True if probe.state is ProbeState.SUCCEEDED else None,
            checked_at=probe.checked_at,
            evidence_id=probe.evidence_id,
        )
        return CapabilityEvidence(
            policy=_policy(capability_id),
            renderer=renderer,
            routes=(
                RouteEvidence(
                    route_id=str(route.get("provider") or "image-provider"),
                    configured=bool(route.get("configured")),
                    permitted=bool(legacy.get("permitted", True)),
                    credential=CredentialEvidence(
                        required=True,
                        present=bool(route.get("configured")),
                        source=str(route.get("provider") or "none"),
                        checked_at=_now(),
                    ),
                    probe=probe,
                ),
            ),
        )

    legacy = image_capability()
    route = legacy.get("route") if isinstance(legacy.get("route"), dict) else {}
    checked_at = _parse_time(route.get("verified_at"))
    status = str(route.get("status") or "unavailable")
    if status == "live" and checked_at:
        probe_state = ProbeState.SUCCEEDED
    elif route.get("last_failure_at"):
        probe_state = ProbeState.FAILED
        checked_at = _parse_time(route.get("last_failure_at")) or _now()
    else:
        probe_state = ProbeState.NEVER
        checked_at = None
    return CapabilityEvidence(
        policy=_policy("image.generate"),
        renderer=RendererEvidence(
            renderer_id="image",
            registered=True,
            healthy=True if probe_state is ProbeState.SUCCEEDED else None,
            checked_at=checked_at,
            evidence_id=str(route.get("verified_at") or "") or None,
        ),
        routes=(
            RouteEvidence(
                route_id=str(route.get("provider") or "image-provider"),
                configured=bool(route.get("configured")),
                permitted=bool(legacy.get("permitted", True)),
                credential=CredentialEvidence(
                    required=True,
                    present=bool(route.get("configured")),
                    source=str(route.get("provider") or "none"),
                    checked_at=_now(),
                ),
                probe=InvocationProbe(
                    state=probe_state,
                    checked_at=checked_at,
                    ttl_seconds=capability_probe_ttl_seconds("OPENAI_IMAGE_PROBE_TTL_SECONDS"),
                    provider=str(route.get("provider") or "") or None,
                    model=str(route.get("model") or "") or None,
                ),
            ),
        ),
    )


def _admin_key_configured() -> bool:
    digest = os.getenv("KOLIBRI_OWNER_API_ADMIN_TOKEN_SHA256", "").strip().lower()
    return bool(re.fullmatch(r"[0-9a-f]{64}", digest))


_SPECS: tuple[tuple[CapabilitySpec, str | None, bool], ...] = (
    (CapabilitySpec("chat.responses", "Диалог", "Ответы через проверенный AI-маршрут.", "conversation", renderer_required=False), None, True),
    (CapabilitySpec("chat.streaming", "Потоковый ответ", "SSE-поток ответа и безопасных стадий работы.", "conversation", renderer_required=False), None, True),
    (CapabilitySpec("response.cancel", "Отмена задачи", "Идемпотентная отмена фонового ответа.", "conversation", renderer_required=False), None, False),
    (CapabilitySpec("response.retry", "Повтор задачи", "Повтор исполнения с новым attempt и тем же контекстом.", "conversation", renderer_required=False), None, False),
    (CapabilitySpec("project.history", "История проектов", "Сохранение и восстановление диалогов проекта.", "project", renderer_required=False), None, False),
    (CapabilitySpec("estimate.create", "Сметы", "Создание серверной сметы с детерминированным пересчётом и редактором.", "vertical"), "estimate_editor", False),
    (CapabilitySpec("document.editor", "Документы", "Создание и сохранение документа в редакторе проекта.", "vertical"), "document_editor", False),
    (CapabilitySpec("web.search", "Поиск в интернете", "Поиск с проверяемыми HTTP(S)-источниками.", "research"), "sources", False),
    (CapabilitySpec("file.upload", "Загрузка файлов", "Сохранение реальных байтов файла с MIME и SHA-256.", "file"), "file", False),
    (CapabilitySpec("file.analyze", "Анализ файлов", "Извлечение проверяемого содержимого поддержанных форматов.", "file"), "file_analysis", False),
    (CapabilitySpec("file.search", "Поиск по файлам", "Поиск по сохранённым файлам текущего проекта.", "file"), "file_search", False),
    (CapabilitySpec("document.pdf", "PDF", "Создание и сохранение проверенного PDF.", "document"), "pdf", False),
    (CapabilitySpec("document.docx", "DOCX", "Создание и сохранение проверенного DOCX.", "document"), "document", False),
    (CapabilitySpec("document.xlsx", "XLSX", "Создание и сохранение проверенного XLSX.", "document"), "spreadsheet", False),
    (CapabilitySpec("document.pptx", "PPTX", "Создание и сохранение проверенного PPTX.", "document"), "presentation", False),
    (CapabilitySpec("image.generate", "Генерация изображений", "Создание проверенного растрового артефакта.", "media"), "image", False),
    (CapabilitySpec("image.edit", "Редактирование изображений", "Редактирование существующего изображения с проверенными байтами.", "media"), "image", False),
    (CapabilitySpec("site.create", "Создание сайтов", "Файлы сайта, sandbox-preview и скачивание.", "builder"), "project_preview", False),
    (CapabilitySpec("app.create", "Создание приложений", "Файлы самодостаточного браузерного приложения, sandbox-preview и скачивание.", "builder"), "project_preview", False),
    (CapabilitySpec("developer.api_keys", "API-ключи", "Создание, одноразовый показ, использование и отзыв ключей.", "developer", renderer_required=False), None, False),
    (CapabilitySpec("developer.responses", "Responses API", "OpenAI-compatible Responses API и возобновляемый SSE.", "developer", renderer_required=False), None, True),
    (CapabilitySpec("developer.chat_completions", "Chat Completions API", "OpenAI-compatible Chat Completions API.", "developer", renderer_required=False), None, True),
    (CapabilitySpec("developer.structured_json", "Структурированный JSON", "Responses/Chat ответ по строгой JSON-схеме.", "developer", renderer_required=False), None, False),
    (CapabilitySpec("integration.connect", "Интеграции", "Подключение внешней системы после авторизации владельца.", "automation", renderer_required=False), None, False),
    (CapabilitySpec("automation.run", "Автоматизации", "Запуск разрешённого workflow с журналом событий.", "automation", renderer_required=False), None, False),
)


_IMPLEMENTED_INTERNAL = {
    "response.cancel",
    "response.retry",
    "project.history",
    "estimate.create",
    "document.editor",
    "web.search",
    "file.upload",
    "file.analyze",
    "file.search",
    "document.pdf",
    "document.docx",
    "document.xlsx",
    "document.pptx",
    "developer.structured_json",
}


def canonical_registry() -> CapabilityRegistry:
    """Build a registry whose providers read current runtime evidence."""

    registry = CapabilityRegistry()
    for spec, renderer_id, provider_backed in _SPECS:
        capability_id = spec.id
        if capability_id in {"image.generate", "image.edit"}:
            evidence_provider = lambda cid=capability_id: _image_evidence(cid)
        elif capability_id in {"site.create", "app.create"}:
            evidence_provider = lambda cid=capability_id: _project_builder_evidence(cid)
        elif provider_backed:
            evidence_provider = lambda cid=capability_id: _text_provider_evidence(cid)
        elif capability_id == "developer.api_keys":
            evidence_provider = lambda cid=capability_id, rid=renderer_id: _internal_evidence(
                cid,
                configured=_admin_key_configured(),
                renderer_id=rid,
                renderer_required=False,
                credential_required=True,
                credential_present=_admin_key_configured(),
                route_id="developer-api-key-routes",
            )
        else:
            configured = capability_id in _IMPLEMENTED_INTERNAL
            evidence_provider = lambda cid=capability_id, rid=renderer_id, configured=configured, required=spec.renderer_required: _internal_evidence(
                cid,
                configured=configured,
                renderer_id=rid,
                renderer_required=required,
            )
        registry.register(spec, evidence_provider)
    return registry


def capability_snapshot() -> dict[str, Any]:
    snapshot = canonical_registry().snapshot()
    snapshot["release_id"] = _release_id()
    snapshot["probe_ttl_seconds"] = capability_probe_ttl_seconds()
    return snapshot


def public_capability_snapshot() -> dict[str, Any]:
    """Return the public capability catalog without provider topology.

    The protected control plane keeps the full runtime evidence. Browser
    clients receive only product labels, the derived availability verdict,
    renderer state and a bounded technical reason.
    """

    snapshot = capability_snapshot()
    capabilities: list[dict[str, Any]] = []
    for value in snapshot.get("capabilities", []):
        if not isinstance(value, dict):
            continue
        reason = value.get("reason")
        renderer = value.get("renderer")
        policy = value.get("policy")
        public: dict[str, Any] = {
            key: value.get(key)
            for key in (
                "id",
                "name",
                "description",
                "kind",
                "catalog_listed",
                "status",
                "invocable",
                "verified_at",
            )
        }
        public["permitted"] = (
            policy.get("permitted") is True
            if isinstance(policy, dict)
            else False
        )
        public["route"] = {
            "healthy": (
                value.get("status") == "available"
                and value.get("invocable") is True
            ),
            "status": value.get("status"),
        }
        selected_route_alias, public_routes = _public_route_proofs(value)
        public["selected_route_id"] = selected_route_alias
        public["routes"] = public_routes
        public["source"] = _public_source(value, selected_route_alias, public_routes)
        public["reason"] = {
            "code": str(reason.get("code") or "unavailable"),
            "message": str(reason.get("message") or "Возможность недоступна."),
        } if isinstance(reason, dict) else {
            "code": "unavailable",
            "message": "Возможность недоступна.",
        }
        public["renderer"] = {
            "required": renderer.get("required") is True,
            "id": renderer.get("id"),
            "registered": renderer.get("registered") is True,
            "healthy": renderer.get("healthy"),
        } if isinstance(renderer, dict) else {
            "required": False,
            "id": None,
            "registered": False,
            "healthy": None,
        }
        capabilities.append(public)
    return {
        key: snapshot.get(key)
        for key in (
            "schema_version",
            "status",
            "as_of",
            "counts",
            "release_id",
            "probe_ttl_seconds",
        )
        if key in snapshot
    } | {"capabilities": capabilities}


def _public_route_alias(capability_id: str) -> str:
    safe_capability = (
        capability_id
        if _CAPABILITY_ID.fullmatch(capability_id)
        else f"capability-{hashlib.sha256(capability_id.encode('utf-8')).hexdigest()[:16]}"
    )
    return f"{safe_capability}.route.primary"


def _public_source(
    capability: dict[str, Any],
    selected_route_id: str | None,
    routes: list[dict[str, Any]],
) -> dict[str, str]:
    if capability.get("status") != "available" or capability.get("invocable") is not True:
        return {"type": "runtime_evidence"}
    for route in routes:
        if route.get("id") != selected_route_id:
            continue
        probe = route.get("probe")
        if (
            isinstance(probe, dict)
            and probe.get("state") == ProbeState.SUCCEEDED.value
            and probe.get("fresh") is True
        ):
            return {"type": "live_invocation"}
    return {"type": "runtime_evidence"}


def _public_evidence(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if _PUBLIC_SAFE_ID.fullmatch(text):
        return text
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _public_error_code(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"[^a-z0-9_.-]+", "_", str(value).lower()).strip("_")
    return text[:80] or None


def _public_probe(probe: Any) -> dict[str, Any]:
    raw = probe if isinstance(probe, dict) else {}
    state = str(raw.get("state") or "never")
    if state not in {item.value for item in ProbeState}:
        state = ProbeState.NEVER.value
    try:
        ttl_seconds = int(raw.get("ttl_seconds") or 0)
    except (TypeError, ValueError):
        ttl_seconds = 0
    if ttl_seconds <= 0:
        ttl_seconds = capability_probe_ttl_seconds()
    checked_at = _parse_time(raw.get("checked_at"))
    evidence_id = _public_evidence(raw.get("evidence_id"))
    error_code = _public_error_code(raw.get("error_code"))
    fresh = (
        state == ProbeState.SUCCEEDED.value
        and checked_at is not None
        and raw.get("fresh") is True
    )
    return {
        "state": state,
        "fresh": fresh,
        "checked_at": checked_at.isoformat() if checked_at else None,
        "ttl_seconds": ttl_seconds,
        "evidence_id": evidence_id,
        "error_code": error_code,
    }


def _public_route_proofs(capability: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]]]:
    routes = [route for route in capability.get("routes", []) if isinstance(route, dict)]
    if not routes:
        return None, []

    selected_internal = str(capability.get("selected_route_id") or "")
    selected_route = next(
        (route for route in routes if str(route.get("id") or "") == selected_internal),
        None,
    )
    proof_route = selected_route
    if proof_route is None:
        proof_route = next(
            (
                route
                for route in routes
                if isinstance(route.get("probe"), dict)
                and route["probe"].get("state") != ProbeState.NEVER.value
            ),
            routes[0],
        )

    alias = _public_route_alias(str(capability.get("id") or "capability"))
    public_route = {
        "id": alias,
        "configured": proof_route.get("configured") is True,
        "permitted": proof_route.get("permitted") is True,
        "probe": _public_probe(proof_route.get("probe")),
    }
    selected_alias = alias if selected_route is proof_route else None
    return selected_alias, [public_route]


def capability_by_id(capability_id: str) -> dict[str, Any] | None:
    for item in capability_snapshot()["capabilities"]:
        if item.get("id") == capability_id:
            return item
    return None


def require_available(capability_id: str) -> dict[str, Any]:
    capability = capability_by_id(capability_id)
    if capability is None or capability.get("status") != "available" or capability.get("invocable") is not True:
        reason = capability.get("reason") if isinstance(capability, dict) else None
        code = reason.get("code") if isinstance(reason, dict) else "capability_not_registered"
        raise CapabilityUnavailable(capability_id, str(code))
    return capability


class CapabilityUnavailable(RuntimeError):
    def __init__(self, capability_id: str, reason_code: str):
        self.capability_id = capability_id
        self.reason_code = reason_code
        super().__init__(f"{capability_id}: {reason_code}")


__all__ = [
    "CapabilityUnavailable",
    "canonical_registry",
    "capability_by_id",
    "capability_invocation_probe",
    "capability_probe_ttl_seconds",
    "capability_release_id",
    "capability_snapshot",
    "public_capability_snapshot",
    "record_capability_invocation",
    "require_available",
]
