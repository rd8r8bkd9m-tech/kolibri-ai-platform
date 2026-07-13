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
from dataclasses import dataclass
from typing import Any, AsyncIterator, Mapping

import httpx

from app.home_factory_contract import validate_home_control_plane_url


_TERMINAL_STATES = {"completed", "failed", "cancelled", "dead_letter"}
_SAFE_RUN_ID = re.compile(r"[^A-Za-z0-9._:-]+")


class HomeFactoryResponseError(RuntimeError):
    """A response could not be proven through the Home task authority."""

    def __init__(self, failure_kind: str):
        super().__init__(failure_kind)
        self.failure_kind = failure_kind


@dataclass(frozen=True)
class HomeFactoryResponseSettings:
    control_plane_url: str
    release_id: str
    timeout_seconds: float = 240.0
    poll_seconds: float = 0.25
    request_timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls) -> "HomeFactoryResponseSettings":
        try:
            timeout = float(os.getenv("KOLIBRI_FACTORY_RESPONSE_TIMEOUT_SECONDS", "240"))
            poll = float(os.getenv("KOLIBRI_FACTORY_RESPONSE_POLL_SECONDS", "0.25"))
            request_timeout = float(
                os.getenv("KOLIBRI_FACTORY_RESPONSE_REQUEST_TIMEOUT_SECONDS", "5")
            )
        except ValueError as exc:
            raise HomeFactoryResponseError("home_factory_timeout_invalid") from exc
        if not 10 <= timeout <= 900 or not 0.05 <= poll <= 5 or not 1 <= request_timeout <= 30:
            raise HomeFactoryResponseError("home_factory_timeout_invalid")
        try:
            control_plane_url = validate_home_control_plane_url(
                os.getenv("KOLIBRI_CONTROL_PLANE_URL")
            )
        except ValueError as exc:
            raise HomeFactoryResponseError("home_factory_not_configured") from exc
        release_id = os.getenv("KOLIBRI_RELEASE_ID", "").strip()
        if not release_id:
            raise HomeFactoryResponseError("home_factory_release_id_missing")
        return cls(
            control_plane_url=control_plane_url,
            release_id=release_id,
            timeout_seconds=timeout,
            poll_seconds=poll,
            request_timeout_seconds=request_timeout,
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
        "Выполни запрос Kolibri как универсальный AI. Соблюдай системные инструкции "
        "в массиве сообщений. Верни только итоговый ответ; если системная инструкция "
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
    content = str(result.get("response") or "").strip()
    checks = verifier.get("checks") if isinstance(verifier.get("checks"), Mapping) else {}
    required_checks = {
        "agent",
        "attempt",
        "binding_sha256",
        "fencing_token",
        "lease_actor",
        "lease_slot",
        "node",
        "result",
        "result_reference",
        "result_sha256",
        "status",
        "task",
    }
    binding = str(evidence.get("binding_sha256") or "")
    result_digest = str(evidence.get("result_sha256") or "")
    valid = bool(
        content
        and str(task.get("lease_owner") or "") == "home:home-codex-provider"
        and str(evidence.get("node_id") or "") == "home"
        and str(evidence.get("agent_id") or "") == "home-codex-provider"
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
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.control_plane_url,
                timeout=httpx.Timeout(self.settings.request_timeout_seconds),
                transport=self.transport,
                follow_redirects=False,
            ) as client:
                response = await client.request(method, path, json=body)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise HomeFactoryResponseError("home_factory_unreachable") from exc
        if not 200 <= response.status_code < 300:
            raise HomeFactoryResponseError(f"home_factory_http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise HomeFactoryResponseError("home_factory_invalid_json") from exc
        if not isinstance(payload, dict):
            raise HomeFactoryResponseError("home_factory_invalid_contract")
        return payload

    async def submit(
        self,
        messages: list[dict[str, str]],
        *,
        run_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        task_id = _task_id(run_id)
        stable_idempotency = idempotency_key or f"response:{task_id}"
        # This is the strict external-provider actor contract accepted by the
        # current Home authority.  Its intentionally closed field set prevents
        # a web request from smuggling development, write or fallback powers
        # into the authenticated Codex actor.
        envelope = {
            "task_id": task_id,
            "idempotency_key": stable_idempotency,
            "kind": "owner_remote_task",
            "target_node": "home",
            "required_capability": "runner:codex",
            "runner": "codex",
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
                "response_id": str(run_id or task_id),
                "identity_contract": "kolibri.public-identity.v1",
                "provider_actor_node_id": "home-codex-provider",
                "provider_slot_id": "home-codex-provider",
            },
        }
        await self._request("POST", "/v1/tasks", body=envelope)
        deadline = time.monotonic() + self.settings.timeout_seconds
        while time.monotonic() < deadline:
            task = await self._request("GET", f"/v1/tasks/{task_id}")
            state = str(task.get("state") or "")
            if state == "completed":
                return _verified_result(task)
            if state in _TERMINAL_STATES:
                raise HomeFactoryResponseError(
                    str(task.get("error_type") or f"home_factory_task_{state}")
                )
            await asyncio.sleep(self.settings.poll_seconds)
        raise HomeFactoryResponseError("home_factory_response_timeout")

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        run_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {
            "work_summary": {
                "stage": "factory_dispatch",
                "summary": "Задача передана единому Home Control Plane",
                "status": "active",
            }
        }
        result = await self.submit(
            messages,
            run_id=run_id,
            idempotency_key=idempotency_key,
        )
        yield {
            "work_summary": {
                "stage": "factory_verified",
                "summary": "Результат проверен независимым контуром Control Plane",
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
