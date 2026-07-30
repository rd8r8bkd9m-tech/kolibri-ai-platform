"""Home-only Codex provider broker for the Kolibri Factory.

This process is designed to run on Home as the owner user.  It does not copy
Codex credentials to worker nodes.  It advertises an agent slot on the single
logical Home node, leases only explicitly Codex-bound tasks, keeps the lease
alive during execution, persists a content-addressed result, and rechecks the
attempt binding immediately before completion.

Production activation remains a separate signed release action.  Importing the
module has no network or process side effects.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol

import httpx

from app.codex_cli_provider import CodexCLIError, get_codex_cli_provider
from app.home_factory_contract import (
    HOME_CODEX_CAPABILITIES,
    HOME_CODEX_SLOT_ID,
    HOME_NODE_ID,
    HomeFactoryContractError,
    home_broker_heartbeat,
    validate_home_control_plane_url,
)


_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
_SAFE_ERROR_TYPE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,99}$")
_LOG = logging.getLogger("kolibri.home_codex_broker")


class HomeFactoryRuntimeError(RuntimeError):
    """Sanitised broker error suitable for a task failure classification."""


class CodexProvider(Protocol):
    async def probe_health(self) -> dict[str, Any]: ...

    async def invoke(
        self,
        messages: list[dict[str, str]],
        *,
        policy: Mapping[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class HomeBrokerSettings:
    control_plane_url: str
    artifact_root: Path
    request_timeout_seconds: float = 10.0
    lease_heartbeat_seconds: float = 10.0
    idle_poll_seconds: float = 2.0
    health_refresh_seconds: float = 15.0
    retry_backoff_initial_seconds: float = 1.0
    retry_backoff_max_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> "HomeBrokerSettings":
        retry_initial = _bounded_float(
            "KOLIBRI_HOME_CODEX_BROKER_RETRY_INITIAL_SECONDS", 1.0, 0.1, 30.0
        )
        retry_maximum = _bounded_float(
            "KOLIBRI_HOME_CODEX_BROKER_RETRY_MAX_SECONDS", 30.0, 1.0, 300.0
        )
        return cls(
            control_plane_url=validate_home_control_plane_url(
                os.getenv("KOLIBRI_CONTROL_PLANE_URL")
            ),
            artifact_root=Path(
                os.getenv(
                    "KOLIBRI_HOME_CODEX_BROKER_ARTIFACT_ROOT",
                    "/var/lib/kolibri/home-codex-broker/artifacts",
                )
            ).expanduser(),
            request_timeout_seconds=_bounded_float(
                "KOLIBRI_HOME_CODEX_BROKER_HTTP_TIMEOUT_SECONDS", 10.0, 1.0, 60.0
            ),
            lease_heartbeat_seconds=_bounded_float(
                "KOLIBRI_HOME_CODEX_BROKER_HEARTBEAT_SECONDS", 10.0, 2.0, 30.0
            ),
            idle_poll_seconds=_bounded_float(
                "KOLIBRI_HOME_CODEX_BROKER_IDLE_SECONDS", 2.0, 0.2, 30.0
            ),
            health_refresh_seconds=_bounded_float(
                "KOLIBRI_HOME_CODEX_BROKER_HEALTH_REFRESH_SECONDS",
                15.0,
                5.0,
                60.0,
            ),
            retry_backoff_initial_seconds=retry_initial,
            retry_backoff_max_seconds=max(retry_initial, retry_maximum),
        )


def _bounded_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _safe_identifier(value: Any, field: str) -> str:
    text = str(value or "")
    if not _SAFE_ID.fullmatch(text):
        raise HomeFactoryRuntimeError(f"invalid_{field}")
    return text


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_error_type(exc: BaseException) -> str:
    value = str(getattr(exc, "failure_kind", None) or str(exc) or "")
    return value if _SAFE_ERROR_TYPE.fullmatch(value) else "broker_transient_error"


def _blocked_probe(error_type: str) -> dict[str, Any]:
    """Create a secret-free health result when the provider probe itself fails."""

    return {
        "provider": "codex_cli",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "credential_source": "home_codex_cli_login",
        "secret_exposed": False,
        "model": "account-default",
        "status": "unavailable",
        "entitlement": "unverified",
        "error_code": error_type,
        "tests": {
            "binary": {"ok": None, "availability": "unknown"},
            "cwd": {"ok": None, "availability": "unknown"},
            "login": {"ok": None, "availability": "unknown"},
        },
    }


class HomeControlPlaneClient:
    def __init__(
        self,
        settings: HomeBrokerSettings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self._transport = transport

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        allow_empty: bool = False,
    ) -> dict[str, Any] | None:
        timeout = httpx.Timeout(self.settings.request_timeout_seconds)
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.control_plane_url,
                timeout=timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.request(method, path, json=json_body)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise HomeFactoryRuntimeError("home_control_plane_unreachable") from exc
        if allow_empty and response.status_code == 204:
            return None
        if response.status_code < 200 or response.status_code >= 300:
            raise HomeFactoryRuntimeError(
                f"home_control_plane_http_{response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise HomeFactoryRuntimeError("home_control_plane_invalid_json") from exc
        if not isinstance(payload, dict):
            raise HomeFactoryRuntimeError("home_control_plane_invalid_contract")
        return payload

    async def home_node(self) -> dict[str, Any]:
        payload = await self._request("GET", f"/v1/nodes/{HOME_NODE_ID}")
        assert payload is not None
        return payload

    async def advertise(self, body: Mapping[str, Any]) -> dict[str, Any]:
        payload = await self._request(
            "POST", f"/v1/nodes/{HOME_NODE_ID}/heartbeat", json_body=body
        )
        assert payload is not None
        return payload

    async def lease(self, body: Mapping[str, Any]) -> dict[str, Any] | None:
        return await self._request(
            "POST", "/v1/tasks/lease", json_body=body, allow_empty=True
        )

    async def task(self, task_id: str) -> dict[str, Any]:
        payload = await self._request("GET", f"/v1/tasks/{task_id}")
        assert payload is not None
        return payload

    async def heartbeat_task(
        self,
        task_id: str,
        attempt_id: str,
        fencing_token: int,
    ) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            f"/v1/tasks/{task_id}/heartbeat",
            json_body={
                "state": "running",
                "node_id": HOME_NODE_ID,
                "agent_id": HOME_CODEX_SLOT_ID,
                "slot_id": HOME_CODEX_SLOT_ID,
                "attempt_id": attempt_id,
                "lease_owner": f"{HOME_NODE_ID}:{HOME_CODEX_SLOT_ID}",
                "fencing_token": fencing_token,
            },
        )
        assert payload is not None
        return payload

    async def complete(
        self,
        task_id: str,
        attempt_id: str,
        fencing_token: int,
        result_reference: str,
        result: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            f"/v1/tasks/{task_id}/complete",
            json_body={
                "node_id": HOME_NODE_ID,
                "agent_id": HOME_CODEX_SLOT_ID,
                "slot_id": HOME_CODEX_SLOT_ID,
                "attempt_id": attempt_id,
                "lease_owner": f"{HOME_NODE_ID}:{HOME_CODEX_SLOT_ID}",
                "fencing_token": fencing_token,
                "result_reference": result_reference,
                "result": result,
            },
        )
        assert payload is not None
        return payload

    async def fail(
        self,
        task_id: str,
        attempt_id: str,
        fencing_token: int,
        error_type: str,
        result: Mapping[str, Any],
        *,
        retry: bool = False,
    ) -> dict[str, Any]:
        payload = await self._request(
            "POST",
            f"/v1/tasks/{task_id}/fail",
            json_body={
                "node_id": HOME_NODE_ID,
                "agent_id": HOME_CODEX_SLOT_ID,
                "slot_id": HOME_CODEX_SLOT_ID,
                "attempt_id": attempt_id,
                "lease_owner": f"{HOME_NODE_ID}:{HOME_CODEX_SLOT_ID}",
                "fencing_token": fencing_token,
                "error_type": error_type,
                "error": error_type,
                "result": result,
                "retry": retry,
            },
        )
        assert payload is not None
        return payload


class HomeCodexBroker:
    def __init__(
        self,
        settings: HomeBrokerSettings,
        provider: CodexProvider,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.settings = settings
        self.provider = provider
        self.control = HomeControlPlaneClient(settings, transport=transport)
        self._advertisement: dict[str, Any] | None = None
        self._last_advertised_monotonic = 0.0

    async def refresh_advertisement(self) -> dict[str, Any]:
        base_node = await self.control.home_node()
        try:
            candidate = await self.provider.probe_health()
            probe = (
                dict(candidate)
                if isinstance(candidate, Mapping)
                else _blocked_probe("codex_cli_probe_invalid_contract")
            )
        except (CodexCLIError, OSError, asyncio.TimeoutError) as exc:
            probe = _blocked_probe(_safe_error_type(exc))
        advertisement = home_broker_heartbeat(base_node, probe)
        await self.control.advertise(advertisement)
        self._advertisement = advertisement
        self._last_advertised_monotonic = time.monotonic()
        return advertisement

    async def current_advertisement(self) -> dict[str, Any]:
        age = time.monotonic() - self._last_advertised_monotonic
        if self._advertisement is None or age >= self.settings.health_refresh_seconds:
            return await self.refresh_advertisement()
        return self._advertisement

    def invalidate_advertisement(self) -> None:
        self._advertisement = None
        self._last_advertised_monotonic = 0.0

    def retry_delay(self, consecutive_failures: int) -> float:
        exponent = max(0, min(int(consecutive_failures) - 1, 20))
        return min(
            self.settings.retry_backoff_max_seconds,
            self.settings.retry_backoff_initial_seconds * (2**exponent),
        )

    @staticmethod
    def _validate_task(task: Mapping[str, Any]) -> tuple[str, str, int, str]:
        task_id = _safe_identifier(task.get("task_id"), "task_id")
        attempt_id = _safe_identifier(task.get("attempt_id"), "attempt_id")
        fencing_token = task.get("fencing_token")
        if isinstance(fencing_token, bool) or not isinstance(fencing_token, int) or fencing_token < 1:
            raise HomeFactoryRuntimeError("fencing_token_required")
        envelope = task.get("envelope") if isinstance(task.get("envelope"), Mapping) else {}
        if str(task.get("kind") or envelope.get("kind") or "") != "owner_remote_task":
            raise HomeFactoryRuntimeError("unsupported_task_kind")
        if str(envelope.get("target_node") or "") != HOME_NODE_ID:
            raise HomeFactoryRuntimeError("target_node_not_home")
        if str(envelope.get("required_capability") or "") != "codex_provider_broker":
            raise HomeFactoryRuntimeError("codex_broker_capability_required")
        if str(envelope.get("runner") or "").lower() != "codex":
            raise HomeFactoryRuntimeError("codex_runner_required")
        objective = str(envelope.get("objective") or "").strip()
        if not objective:
            raise HomeFactoryRuntimeError("objective_required")
        return task_id, attempt_id, fencing_token, objective

    async def _lease_heartbeat(
        self,
        task_id: str,
        attempt_id: str,
        fencing_token: int,
        stop: asyncio.Event,
    ) -> None:
        consecutive_failures = 0
        while not stop.is_set():
            delay = (
                self.settings.lease_heartbeat_seconds
                if consecutive_failures == 0
                else self.retry_delay(consecutive_failures)
            )
            try:
                await asyncio.wait_for(stop.wait(), timeout=delay)
            except asyncio.TimeoutError:
                try:
                    await self.control.heartbeat_task(
                        task_id, attempt_id, fencing_token
                    )
                    consecutive_failures = 0
                except HomeFactoryRuntimeError:
                    # A brief Control Plane outage must not terminate the
                    # provider process.  Completion still revalidates the
                    # attempt/fence, so an expired lease cannot be accepted.
                    consecutive_failures += 1

    def _write_result(
        self,
        task_id: str,
        attempt_id: str,
        fencing_token: int,
        provider_result: Mapping[str, Any],
    ) -> tuple[Path, dict[str, Any]]:
        content = str(provider_result.get("content") or "").strip()
        if not content:
            raise HomeFactoryRuntimeError("codex_empty_response")
        result = {
            "status": "completed",
            "kind": "owner_remote_task",
            "node_id": HOME_NODE_ID,
            "agent_id": HOME_CODEX_SLOT_ID,
            "task_id": task_id,
            "attempt_id": attempt_id,
            "fencing_token": fencing_token,
            "provider": "codex_cli",
            "public_model": "kolibri",
            "model": provider_result.get("model") or "account-default",
            "response": content,
            "result_sha256": _sha256_bytes(content.encode("utf-8")),
            "tool_events": provider_result.get("tool_events") or [],
            "work_summaries": provider_result.get("work_summaries") or [],
            "secret_exposed": False,
        }
        artifact_dir = self.settings.artifact_root / task_id / attempt_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / "result.json"
        encoded = (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
        temporary = artifact_dir / ".result.json.tmp"
        temporary.write_bytes(encoded)
        temporary.replace(path)
        result["artifact"] = {
            "uri": str(path),
            "mime_type": "application/json",
            "bytes": len(encoded),
            "sha256": _sha256_bytes(encoded),
        }
        return path, result

    async def _assert_attempt_binding(
        self,
        task_id: str,
        attempt_id: str,
        fencing_token: int,
    ) -> None:
        current = await self.control.task(task_id)
        if str(current.get("attempt_id") or "") != attempt_id:
            raise HomeFactoryRuntimeError("stale_attempt_id")
        if str(current.get("lease_owner") or "") != f"{HOME_NODE_ID}:{HOME_CODEX_SLOT_ID}":
            raise HomeFactoryRuntimeError("stale_lease_owner")
        if current.get("fencing_token") != fencing_token:
            raise HomeFactoryRuntimeError("stale_fencing_token")
        if str(current.get("state") or "") not in {"leased", "running"}:
            raise HomeFactoryRuntimeError("task_not_active")

    async def run_once(self) -> dict[str, Any] | None:
        advertisement = await self.current_advertisement()
        if advertisement.get("provider_broker_status") != "live":
            return None
        task = await self.control.lease(
            {
                "node_id": HOME_NODE_ID,
                "agent_id": HOME_CODEX_SLOT_ID,
                "capabilities": list(HOME_CODEX_CAPABILITIES),
                "runners": advertisement["runners"],
            }
        )
        if task is None:
            return None

        try:
            task_id, attempt_id, fencing_token, objective = self._validate_task(task)
        except HomeFactoryRuntimeError as exc:
            unsafe_task_id = str(task.get("task_id") or "")
            unsafe_attempt_id = str(task.get("attempt_id") or "")
            unsafe_fencing_token = task.get("fencing_token")
            if (
                _SAFE_ID.fullmatch(unsafe_task_id)
                and _SAFE_ID.fullmatch(unsafe_attempt_id)
                and isinstance(unsafe_fencing_token, int)
                and not isinstance(unsafe_fencing_token, bool)
                and unsafe_fencing_token >= 1
            ):
                await self.control.fail(
                    unsafe_task_id,
                    unsafe_attempt_id,
                    unsafe_fencing_token,
                    str(exc),
                    {
                        "status": "blocked",
                        "node_id": HOME_NODE_ID,
                        "agent_id": HOME_CODEX_SLOT_ID,
                        "error_type": str(exc),
                    },
                    retry=False,
                )
            raise

        stop = asyncio.Event()
        heartbeat = asyncio.create_task(
            self._lease_heartbeat(task_id, attempt_id, fencing_token, stop)
        )
        try:
            provider_result = await self.provider.invoke(
                [{"role": "user", "content": objective}],
                policy={"read_only": True, "public_model": "kolibri"},
                run_id=f"factory_{attempt_id}",
            )
            path, result = self._write_result(
                task_id, attempt_id, fencing_token, provider_result
            )
            await self._assert_attempt_binding(task_id, attempt_id, fencing_token)
            completion = await self.control.complete(
                task_id, attempt_id, fencing_token, str(path), result
            )
            return {"task": task, "result": result, "completion": completion}
        except (CodexCLIError, HomeFactoryRuntimeError) as exc:
            error_type = getattr(exc, "failure_kind", None) or str(exc)
            # Provider failures are retryable within the task's bounded
            # max-attempts policy.  A stale fence must never mutate the newer
            # attempt; its old lease will be rejected by the Control Plane.
            if error_type not in {
                "stale_attempt_id",
                "stale_lease_owner",
                "stale_fencing_token",
                "task_not_active",
            }:
                await self.control.fail(
                    task_id,
                    attempt_id,
                    fencing_token,
                    error_type,
                    {
                        "status": "blocked",
                        "node_id": HOME_NODE_ID,
                        "agent_id": HOME_CODEX_SLOT_ID,
                        "task_id": task_id,
                        "attempt_id": attempt_id,
                        "error_type": error_type,
                        "secret_exposed": False,
                    },
                    retry=isinstance(exc, CodexCLIError)
                    or error_type == "codex_empty_response",
                )
            self.invalidate_advertisement()
            raise
        finally:
            stop.set()
            await heartbeat

    async def run_forever(self) -> None:
        consecutive_failures = 0
        while True:
            try:
                result = await self.run_once()
            except asyncio.CancelledError:
                raise
            except (CodexCLIError, HomeFactoryRuntimeError) as exc:
                consecutive_failures += 1
                self.invalidate_advertisement()
                delay = self.retry_delay(consecutive_failures)
                _LOG.warning(
                    "broker_cycle_retry error_type=%s retry_seconds=%.3f",
                    _safe_error_type(exc),
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            consecutive_failures = 0
            if result is None:
                await asyncio.sleep(self.settings.idle_poll_seconds)


async def _async_main(once: bool) -> None:
    settings = HomeBrokerSettings.from_env()
    broker = HomeCodexBroker(settings, get_codex_cli_provider())
    if once:
        await broker.run_once()
    else:
        await broker.run_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Kolibri Home Codex factory broker")
    parser.add_argument("--once", action="store_true", help="process at most one task")
    args = parser.parse_args()
    try:
        asyncio.run(_async_main(args.once))
    except HomeFactoryContractError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
