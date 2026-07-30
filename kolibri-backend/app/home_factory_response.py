"""Durable public-response execution through the single Home Control Plane.

This adapter is deliberately small: the browser, Telegram and OpenAI-compatible
routes submit the same fenced ``owner_remote_task`` envelope, then observe the
authoritative task record until the independent Control Plane verifier accepts
the completion.  Provider credentials and direct Codex processes never enter
the web backend.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Mapping

import httpx

from app.home_factory_contract import resolve_home_control_plane_url
from app.control_plane import ControlPlaneUnavailable, _optional_bearer_token


_TERMINAL_STATES = {"completed", "failed", "cancelled", "dead_letter"}
_SAFE_RUN_ID = re.compile(r"[^A-Za-z0-9._:-]+")
_SAFE_ROUTE_ID = re.compile(r"route-[0-9a-f]{32}")
_SAFE_NODE_OR_SLOT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")
_SUPPORTED_FACTORY_RUNNERS = {"codex", "mimo", "local_llm", "api"}
_PUBLIC_PROGRESS_SECRET = re.compile(
    r"(?i)(?:\bauthorization\b\s*:\s*bearer\s+[^\s,;]+|"
    r"\b(?:api[_ -]?key|password|secret|token)\b"
    r"(?:\s*[:=]\s*|\s+)[^\s,;]+)"
)
_PRIVATE_PROGRESS_MARKERS = re.compile(
    r"(?i)(?:chain[ _-]?of[ _-]?thought|reasoning_content|private[ _-]?reasoning|"
    r"внутренн(?:ее|ие|их)\s+рассужд|скрыт(?:ое|ые|ых)\s+рассужд|"
    r"<tool_call>|<function_call>|<read>|<file_path>)"
)
_FORBIDDEN_PROGRESS_KEYS = {
    "chain_of_thought",
    "messages",
    "prompt",
    "reasoning",
    "reasoning_content",
    "stderr",
    "stdout",
}
_MAX_PUBLIC_PROGRESS_CHARS = 320

LifecycleCallback = Callable[[dict[str, Any]], None]


class HomeFactoryResponseError(RuntimeError):
    """A response could not be proven through the Home task authority."""

    def __init__(self, failure_kind: str):
        super().__init__(failure_kind)
        self.failure_kind = failure_kind


@dataclass(frozen=True)
class HomeFactoryResponseSettings:
    control_plane_url: str
    release_id: str
    bearer_token: str = field(repr=False)
    # This is an observer budget, not the task lifetime.  The durable task
    # remains owned by Home after a browser disconnect.  A one-hour default
    # removes the former short user-visible cutoff while retaining a bounded
    # safety ceiling for a single HTTP observer.
    timeout_seconds: float = 3_600.0
    poll_seconds: float = 0.25
    request_timeout_seconds: float = 5.0
    request_attempts: int = 4
    request_retry_seconds: float = 0.2

    @classmethod
    def from_env(cls) -> "HomeFactoryResponseSettings":
        try:
            timeout = float(os.getenv("KOLIBRI_FACTORY_RESPONSE_TIMEOUT_SECONDS", "3600"))
            poll = float(os.getenv("KOLIBRI_FACTORY_RESPONSE_POLL_SECONDS", "0.25"))
            request_timeout = float(
                os.getenv("KOLIBRI_FACTORY_RESPONSE_REQUEST_TIMEOUT_SECONDS", "5")
            )
            request_attempts = int(
                os.getenv("KOLIBRI_FACTORY_RESPONSE_REQUEST_ATTEMPTS", "4")
            )
            request_retry = float(
                os.getenv("KOLIBRI_FACTORY_RESPONSE_REQUEST_RETRY_SECONDS", "0.2")
            )
        except ValueError as exc:
            raise HomeFactoryResponseError("home_factory_timeout_invalid") from exc
        if not 10 <= timeout <= 86_400 or not 0.05 <= poll <= 5 or not 1 <= request_timeout <= 30 or not 1 <= request_attempts <= 5 or not 0 <= request_retry <= 2:
            raise HomeFactoryResponseError("home_factory_timeout_invalid")
        try:
            control_plane_url = resolve_home_control_plane_url()
        except ValueError as exc:
            raise HomeFactoryResponseError("home_factory_not_configured") from exc
        release_id = os.getenv("KOLIBRI_RELEASE_ID", "").strip()
        if not release_id:
            raise HomeFactoryResponseError("home_factory_release_id_missing")
        try:
            bearer_token = _optional_bearer_token(
                os.getenv("KOLIBRI_CONTROL_PLANE_TOKEN_FILE")
            )
        except ControlPlaneUnavailable as exc:
            raise HomeFactoryResponseError("home_factory_token_unavailable") from exc
        if not bearer_token:
            raise HomeFactoryResponseError("home_factory_token_missing")
        return cls(
            control_plane_url=control_plane_url,
            release_id=release_id,
            bearer_token=bearer_token,
            timeout_seconds=timeout,
            poll_seconds=poll,
            request_timeout_seconds=request_timeout,
            request_attempts=request_attempts,
            request_retry_seconds=request_retry,
        )


def factory_responses_enabled() -> bool:
    return os.getenv("KOLIBRI_FACTORY_RESPONSES_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def factory_response_configuration() -> dict[str, Any]:
    if not factory_responses_enabled():
        return {"configured": False, "authority": "home", "reason": "disabled"}
    try:
        settings = HomeFactoryResponseSettings.from_env()
    except HomeFactoryResponseError as exc:
        return {"configured": False, "authority": "home", "reason": exc.failure_kind}
    return {
        "configured": True,
        "authority": "home",
        "release_id": settings.release_id,
        "credential_source": "home_control_plane",
    }


def _task_id(run_id: str | None) -> str:
    safe = _SAFE_RUN_ID.sub("-", str(run_id or "").strip()).strip("-._:")
    if not safe:
        safe = hashlib.sha256(os.urandom(32)).hexdigest()[:20]
    return f"KOL-RESP-{safe}"[:180]


def _objective(messages: list[dict[str, str]]) -> str:
    normalized = [
        {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
        for item in messages
    ]
    return (
        "Обработай массив сообщений ниже как внутренний response-only исполнитель. "
        "Соблюдай обычный приоритет ролей. Не представляйся и не называй внутреннюю модель, "
        "провайдера, агента или маршрут. Верни только итоговый ответ; если системная инструкция "
        "требует JSON-действие, верни это JSON-действие без пояснений.\n\n"
        + json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    )


def _verified_result(task: Mapping[str, Any]) -> dict[str, Any]:
    if str(task.get("state") or "") != "completed":
        raise HomeFactoryResponseError("home_factory_task_not_completed")
    result = task.get("result") if isinstance(task.get("result"), Mapping) else {}
    evidence = (
        task.get("completion_evidence")
        if isinstance(task.get("completion_evidence"), Mapping)
        else {}
    )
    verifier = (
        task.get("completion_verifier")
        if isinstance(task.get("completion_verifier"), Mapping)
        else {}
    )
    envelope = task.get("envelope") if isinstance(task.get("envelope"), Mapping) else {}
    source = envelope.get("source") if isinstance(envelope.get("source"), Mapping) else {}
    route_binding = (
        envelope.get("route_decision")
        if isinstance(envelope.get("route_decision"), Mapping)
        else {}
    )
    content = str(result.get("response") or "").strip()
    checks = verifier.get("checks") if isinstance(verifier.get("checks"), Mapping) else {}
    # Every runner is bound to the concrete lease through the task, evidence
    # and verifier records below.  A dedicated provider slot is an additional
    # Codex-only boundary: ordinary Agent Host runners (for example Mimo) do
    # not have a provider slot and the Control Plane correctly omits the two
    # slot-specific checks for them.
    required_checks = {
        "agent",
        "attempt",
        "binding_sha256",
        "fencing_token",
        "node",
        "result",
        "result_reference",
        "result_sha256",
        "status",
        "task",
    }
    binding = str(evidence.get("binding_sha256") or "")
    result_digest = str(evidence.get("result_sha256") or "")
    lease_node, separator, lease_agent = str(task.get("lease_owner") or "").partition(":")
    runner = str(envelope.get("runner") or result.get("runner") or "").strip().lower()
    result_runner = str(result.get("runner") or "").strip().lower()
    if not result_runner and str(result.get("provider") or "") == "codex_cli":
        result_runner = "codex"
    route_decision_id = str(route_binding.get("decision_id") or "")
    expected_slot = str(source.get("provider_slot_id") or "")
    if expected_slot:
        required_checks.update({"lease_actor", "lease_slot"})
    valid = bool(
        content
        and separator
        and runner in _SUPPORTED_FACTORY_RUNNERS
        and result_runner == runner
        and _SAFE_ROUTE_ID.fullmatch(route_decision_id)
        and str(route_binding.get("principal") or "").startswith("principal:")
        and str(envelope.get("target_node") or "") == lease_node
        and str(evidence.get("node_id") or "") == lease_node
        and str(evidence.get("agent_id") or "") == lease_agent
        and (not expected_slot or expected_slot == lease_agent)
        and str(evidence.get("attempt_id") or "") == str(task.get("attempt_id") or "")
        and evidence.get("fencing_token") == task.get("fencing_token")
        and str(evidence.get("result_reference") or "")
        and re.fullmatch(r"sha256:[0-9a-f]{64}", result_digest)
        and re.fullmatch(r"sha256:[0-9a-f]{64}", binding)
        and verifier.get("verdict") == "passed"
        and verifier.get("independent") is True
        and str(verifier.get("verifier") or "") == "control-plane/home"
        and str(verifier.get("binding_sha256") or "") == binding
        and required_checks.issubset({name for name, passed in checks.items() if passed is True})
    )
    if not valid:
        raise HomeFactoryResponseError("home_factory_completion_unverified")
    return {
        "id": str(task.get("task_id") or ""),
        "content": content,
        "model": str(result.get("model") or "kolibri"),
        "provider": "home_factory",
        "runner": runner,
        "route_decision_id": route_decision_id,
        "task_id": str(task.get("task_id") or ""),
        "attempt_id": str(task.get("attempt_id") or ""),
        "fencing_token": task.get("fencing_token"),
        "executor_node": str(evidence.get("node_id") or ""),
        "verifier_node": str(verifier.get("verifier") or ""),
        "artifact_sha256": result_digest,
        "binding_sha256": binding,
        "result_reference": str(evidence.get("result_reference") or ""),
        "tool_events": result.get("tool_events") or [],
    }


def _completion_verification_pending(task: Mapping[str, Any]) -> bool:
    """Return true only while Control Plane has not published a verdict yet.

    A task result and its independent verifier are persisted by separate
    Control Plane transitions.  The task can therefore be briefly observable
    as ``completed`` before ``completion_verifier`` is attached.  A present
    verdict (including ``failed``) is terminal and must still fail closed.
    """
    verifier = task.get("completion_verifier")
    return not isinstance(verifier, Mapping) or not str(
        verifier.get("verdict") or ""
    )


def _notify_lifecycle(
    callback: LifecycleCallback | None,
    *,
    stage: str,
    summary: str,
    status: str,
    kind: str | None = None,
    step_id: str | None = None,
    summary_id: str | None = None,
) -> None:
    if callback is None:
        return
    work_summary: dict[str, Any] = {
        "stage": stage,
        "summary": summary,
        "status": status,
    }
    for key, value in {
        "kind": kind,
        "step_id": step_id,
        "summary_id": summary_id,
    }.items():
        if value:
            work_summary[key] = value
    callback({"work_summary": work_summary})


def _safe_public_progress_delta(value: object) -> str | None:
    """Accept only the Control Plane's explicit public-summary contract.

    A task result, provider stderr, arbitrary worker fields and private
    reasoning never pass through this helper.  Secret-like fragments and
    serialized tool requests are rejected at the public boundary as a second
    defence in addition to the Agent Host's public-progress contract.
    """

    if not isinstance(value, str) or _PRIVATE_PROGRESS_MARKERS.search(value):
        return None
    cleaned = _PUBLIC_PROGRESS_SECRET.sub("[скрыто]", value)
    cleaned = " ".join(cleaned.split())
    return cleaned[:_MAX_PUBLIC_PROGRESS_CHARS].strip() or None


def _task_state_lifecycle(state: str) -> tuple[str, str, str] | None:
    """Map an observed Home task state to a factual public lifecycle update."""

    return {
        "queued": ("background", "Задача ожидает свободного исполнителя", "active"),
        "leased": ("provider_route", "Исполнитель получил задачу", "completed"),
        "running": ("tool_execution", "Исполнитель обрабатывает запрос", "active"),
        "review": ("verification", "Проверяется результат", "active"),
        "verifying": ("verification", "Проверяется результат", "active"),
    }.get(state)


class HomeFactoryResponseClient:
    def __init__(
        self,
        settings: HomeFactoryResponseSettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings or HomeFactoryResponseSettings.from_env()
        self.transport = transport

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        retryable_statuses = {408, 425, 429, 500, 502, 503, 504}
        for attempt in range(self.settings.request_attempts):
            try:
                async with httpx.AsyncClient(
                    base_url=self.settings.control_plane_url,
                    headers={"Authorization": f"Bearer {self.settings.bearer_token}"},
                    timeout=httpx.Timeout(self.settings.request_timeout_seconds),
                    transport=self.transport,
                    follow_redirects=False,
                ) as client:
                    response = await client.request(method, path, json=body)
            except asyncio.CancelledError:
                # A user cancellation is control flow, not provider failure.
                # Let it escape without converting it into a circuit verdict.
                raise
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                if attempt + 1 >= self.settings.request_attempts:
                    raise HomeFactoryResponseError("home_factory_unreachable") from exc
            else:
                if 200 <= response.status_code < 300:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        raise HomeFactoryResponseError("home_factory_invalid_json") from exc
                    if not isinstance(payload, dict):
                        raise HomeFactoryResponseError("home_factory_invalid_contract")
                    return payload
                if (
                    response.status_code not in retryable_statuses
                    or attempt + 1 >= self.settings.request_attempts
                ):
                    raise HomeFactoryResponseError(
                        f"home_factory_http_{response.status_code}"
                    )
            await asyncio.sleep(
                self.settings.request_retry_seconds * (2**attempt)
            )
        raise HomeFactoryResponseError("home_factory_unreachable")

    async def _select_route(
        self,
        *,
        task_id: str,
        response_id: str,
        idempotency_key: str,
        execution_mode: str = "fast",
    ) -> dict[str, Any]:
        decision = await self._request(
            "POST",
            "/v1/runtime/provider-route-decisions",
            body={
                "idempotency_key": f"provider-route:{idempotency_key}",
                "request_id": response_id,
                "trace_id": task_id,
                "public_model": "kolibri",
                "execution_mode": execution_mode,
                "required_capabilities": ["chat", "responses"],
            },
        )
        selected = (
            decision.get("selected_route")
            if isinstance(decision.get("selected_route"), Mapping)
            else {}
        )
        decision_id = str(decision.get("decision_id") or "")
        runner = str(selected.get("runner") or "").strip().lower()
        node_id = str(selected.get("node_id") or "").strip()
        slot_id = str(selected.get("slot_id") or "").strip()
        if (
            decision.get("schema_version") != "kolibri.provider-route-decision.v1"
            or decision.get("authority") != "control-plane/home"
            or decision.get("status") != "selected"
            or decision.get("public_model") != "kolibri"
            or not _SAFE_ROUTE_ID.fullmatch(decision_id)
            or runner not in _SUPPORTED_FACTORY_RUNNERS
            or not _SAFE_NODE_OR_SLOT.fullmatch(node_id)
            or (slot_id and not _SAFE_NODE_OR_SLOT.fullmatch(slot_id))
        ):
            raise HomeFactoryResponseError("home_factory_route_unavailable")
        return {
            "decision_id": decision_id,
            "runner": runner,
            "node_id": node_id,
            "slot_id": slot_id or None,
        }

    async def _submit_single(
        self,
        messages: list[dict[str, str]],
        *,
        run_id: str | None,
        idempotency_key: str | None,
        execution_mode: str,
        lifecycle: LifecycleCallback | None = None,
    ) -> dict[str, Any]:
        task_id = _task_id(run_id)
        stable_idempotency = idempotency_key or f"response:{task_id}"
        response_id = str(run_id or task_id)
        route = await self._select_route(
            task_id=task_id,
            response_id=response_id,
            idempotency_key=stable_idempotency,
            execution_mode=execution_mode,
        )
        _notify_lifecycle(
            lifecycle,
            stage="provider_route",
            summary="Маршрут выполнения выбран",
            status="completed",
        )
        envelope: dict[str, Any] = {
            "task_id": task_id,
            "idempotency_key": stable_idempotency,
            "kind": "owner_remote_task",
            "target_node": route["node_id"],
            "required_capability": f"runner:{route['runner']}",
            "runner": route["runner"],
            "objective": _objective(messages),
            "write_scope": [],
            "constraints": {
                "read_only": True,
                "max_wall_seconds": min(86_400, max(10, int(self.settings.timeout_seconds))),
                "network": "provider_managed_only",
            },
            "max_attempts": 1,
            "fallback_allowed": False,
            "source": {
                "kind": "kolibri_provider_gateway",
                "control_plane": "home",
                "response_id": response_id,
                "identity_contract": "kolibri.public-identity.v1",
            },
            "route_decision_id": route["decision_id"],
        }
        if route["slot_id"]:
            envelope["source"]["provider_actor_node_id"] = route["slot_id"]
            envelope["source"]["provider_slot_id"] = route["slot_id"]
        accepted = await self._request("POST", "/v1/tasks", body=envelope)
        if str(accepted.get("task_id") or "") != task_id:
            raise HomeFactoryResponseError("home_factory_task_binding_invalid")
        _notify_lifecycle(
            lifecycle,
            stage="accepted",
            summary="Задача принята фабрикой",
            status="completed",
        )
        deadline = time.monotonic() + self.settings.timeout_seconds
        last_state = ""
        last_progress_sequence = 0
        public_progress = ""
        public_progress_raw = ""
        while time.monotonic() < deadline:
            task = await self._request("GET", f"/v1/tasks/{task_id}")
            state = str(task.get("state") or "").strip().lower()
            if state != last_state:
                observed = _task_state_lifecycle(state)
                if observed is not None:
                    stage, summary, status = observed
                    _notify_lifecycle(
                        lifecycle,
                        stage=stage,
                        summary=summary,
                        status=status,
                    )
                last_state = state
            progress = task.get("progress")
            if (
                isinstance(progress, Mapping)
                and not _FORBIDDEN_PROGRESS_KEYS.intersection(progress)
                and progress.get("schema_version") == "kolibri.public-progress.v1"
                and progress.get("type") == "reasoning_summary_delta"
                and type(progress.get("sequence")) is int
                and progress["sequence"] > last_progress_sequence
            ):
                last_progress_sequence = progress["sequence"]
                raw_delta = progress.get("delta")
                safe_delta = _safe_public_progress_delta(raw_delta)
                if safe_delta:
                    public_progress_raw = (
                        public_progress_raw + str(raw_delta)
                    )[:_MAX_PUBLIC_PROGRESS_CHARS]
                    public_progress = (
                        _safe_public_progress_delta(public_progress_raw)
                        or public_progress
                    )
                    digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:24]
                    _notify_lifecycle(
                        lifecycle,
                        stage="reasoning_summary",
                        summary=public_progress,
                        status="active",
                        kind="reasoning_excerpt",
                        step_id=f"step_{digest}",
                        summary_id=f"summary_{digest}",
                    )
            if state == "completed":
                try:
                    result = _verified_result(task)
                except HomeFactoryResponseError as exc:
                    if (
                        exc.failure_kind == "home_factory_completion_unverified"
                        and _completion_verification_pending(task)
                    ):
                        await asyncio.sleep(self.settings.poll_seconds)
                        continue
                    raise
                _notify_lifecycle(
                    lifecycle,
                    stage="verification",
                    summary="Проверка результата завершена",
                    status="completed",
                )
                return result
            if state in _TERMINAL_STATES:
                raise HomeFactoryResponseError(
                    str(task.get("error_type") or f"home_factory_task_{state}")
                )
            await asyncio.sleep(self.settings.poll_seconds)
        raise HomeFactoryResponseError("home_factory_response_timeout")

    async def submit(
        self,
        messages: list[dict[str, str]],
        *,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        execution_mode: str = "fast",
        lifecycle: LifecycleCallback | None = None,
    ) -> dict[str, Any]:
        return await self._submit_single(
            messages,
            run_id=run_id,
            idempotency_key=idempotency_key,
            execution_mode=execution_mode,
            lifecycle=lifecycle,
        )

    async def submit_collaboration(
        self,
        messages: list[dict[str, str]],
        *,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        lifecycle: LifecycleCallback | None = None,
    ) -> dict[str, Any]:
        """Run two independent speakers and one verified reducer.

        FormulaLM remains a hash-only candidate observer.  It never receives
        raw customer text, never speaks into the response path and never
        mutates production weights synchronously.
        """

        base_run_id = str(run_id or _task_id(None))
        stable = str(idempotency_key or f"response:{base_run_id}")
        participant_specs = (("codex", "codex"), ("mimo", "mimo"))

        async def invoke(label: str, mode: str) -> tuple[str, dict[str, Any]]:
            result = await self._submit_single(
                messages,
                run_id=f"{base_run_id}:{label}",
                idempotency_key=f"{stable}:{label}",
                execution_mode=mode,
                lifecycle=lifecycle,
            )
            if result.get("runner") != label:
                raise HomeFactoryResponseError("home_factory_collaboration_route_mismatch")
            return label, result

        attempts = await asyncio.gather(
            *(invoke(label, mode) for label, mode in participant_specs),
            return_exceptions=True,
        )
        successful: list[tuple[str, dict[str, Any]]] = [
            item
            for item in attempts
            if isinstance(item, tuple) and len(item) == 2
        ]
        if not successful:
            raise HomeFactoryResponseError("home_factory_collaboration_unavailable")

        bounded_proposals = [
            {
                "participant": label,
                "content": str(result["content"])[:12_000],
                "task_id": result["task_id"],
                "artifact_sha256": result["artifact_sha256"],
                "binding_sha256": result["binding_sha256"],
            }
            for label, result in successful
        ]
        reducer_messages = [
            {
                "role": "system",
                "content": (
                    "Ты независимый reducer Kolibri. Сопоставь предложения участников, "
                    "исправь противоречия и верни один точный итоговый ответ без описания "
                    "внутреннего процесса. Не придумывай факты, которых нет во входе."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"messages": messages, "verified_proposals": bounded_proposals},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
        ]
        reduced = await self._submit_single(
            reducer_messages,
            run_id=f"{base_run_id}:reducer",
            idempotency_key=f"{stable}:reducer",
            execution_mode="codex",
            lifecycle=lifecycle,
        )
        observer_payload = {
            "schema_version": "kolibri.formulalm-shadow-observer.v1",
            "mode": "candidate_only",
            "raw_content_shared": False,
            "request_path_training": False,
            "automatic_promotion": False,
            "participant_result_sha256": sorted(
                str(result["artifact_sha256"]) for _label, result in successful
            ),
            "reducer_result_sha256": str(reduced["artifact_sha256"]),
        }
        reduced["collaboration"] = {
            "schema_version": "kolibri.verified-collaboration.v1",
            "participants": [
                {
                    "role": label,
                    "task_id": result["task_id"],
                    "route_decision_id": result["route_decision_id"],
                    "artifact_sha256": result["artifact_sha256"],
                    "binding_sha256": result["binding_sha256"],
                    "verified": True,
                }
                for label, result in successful
            ],
            "reducer": {
                "task_id": reduced["task_id"],
                "route_decision_id": reduced["route_decision_id"],
                "artifact_sha256": reduced["artifact_sha256"],
                "binding_sha256": reduced["binding_sha256"],
                "verified": True,
            },
            "formulalm": {
                **observer_payload,
                "observer_sha256": hashlib.sha256(
                    json.dumps(
                        observer_payload,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest(),
            },
        }
        return reduced

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        run_id: str | None = None,
        idempotency_key: str | None = None,
        collaboration: bool = False,
        execution_mode: str = "fast",
    ) -> AsyncIterator[dict[str, Any]]:
        lifecycle_events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def record_lifecycle(event: dict[str, Any]) -> None:
            lifecycle_events.put_nowait(event)

        if collaboration:
            operation = asyncio.create_task(
                self.submit_collaboration(
                    messages,
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    lifecycle=record_lifecycle,
                )
            )
        else:
            operation = asyncio.create_task(
                self.submit(
                    messages,
                    run_id=run_id,
                    idempotency_key=idempotency_key,
                    execution_mode=execution_mode,
                    lifecycle=record_lifecycle,
                )
            )
        try:
            while not operation.done() or not lifecycle_events.empty():
                if not lifecycle_events.empty():
                    yield lifecycle_events.get_nowait()
                    continue
                next_event = asyncio.create_task(lifecycle_events.get())
                done, _pending = await asyncio.wait(
                    {operation, next_event},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if next_event in done:
                    yield next_event.result()
                else:
                    next_event.cancel()
                    await asyncio.gather(next_event, return_exceptions=True)
            result = await operation
        finally:
            if not operation.done():
                operation.cancel()
                await asyncio.gather(operation, return_exceptions=True)
        if collaboration:
            participants = len(result.get("collaboration", {}).get("participants", []))
            yield {
                "work_summary": {
                    "stage": "response_received",
                    "summary": f"Проверены результаты участников: {participants}",
                    "status": "completed",
                }
            }
        content = result["content"]
        # Preserve the OpenAI-compatible delta contract while bounding event
        # count for long responses.  The durable factory result remains the
        # source of truth and is not exposed until verification passes.
        chunk_size = 160
        for offset in range(0, len(content), chunk_size):
            yield {"content": content[offset : offset + chunk_size], "done": False}
        yield {"response_meta": result}


_default_client: HomeFactoryResponseClient | None = None
_default_settings: HomeFactoryResponseSettings | None = None


def get_home_factory_response_client() -> HomeFactoryResponseClient:
    global _default_client, _default_settings
    settings = HomeFactoryResponseSettings.from_env()
    if _default_client is None or _default_settings != settings:
        _default_settings = settings
        _default_client = HomeFactoryResponseClient(settings)
    return _default_client
