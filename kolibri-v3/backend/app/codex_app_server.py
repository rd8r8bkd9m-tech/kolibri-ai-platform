"""Persistent Codex App Server client for the local Kolibri V3 runtime.

The backend owns exactly one app-server process for its lifetime. Product chat
history remains authoritative in Kolibri's database; Codex threads are
ephemeral acceleration state and are never treated as product persistence.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess
import threading
import time
from typing import Any, Callable, Sequence

from .agent_runtime import canonical_runtime_activity


class CodexAppServerError(RuntimeError):
    """A public-safe app-server failure."""


class CodexAppServerAuthenticationError(CodexAppServerError):
    """The app-server has no usable Codex account."""


@dataclass(frozen=True, slots=True)
class CodexModel:
    """Safe model-catalog projection returned by the authenticated app-server."""

    id: str
    display_name: str
    description: str
    supported_reasoning_efforts: tuple[tuple[str, str], ...]
    default_reasoning_effort: str
    is_default: bool
    supports_personality: bool
    service_tiers: tuple[tuple[str, str, str], ...]
    upgrade: str | None


_PRIORITY_SERVICE_TIERS: tuple[tuple[str, str, str], ...] = (
    (
        "priority",
        "Fast",
        "1.5x speed, increased usage",
    ),
)
_SERVICE_TIER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


_AUTHENTICATED_PREVIEW_MODELS: tuple[CodexModel, ...] = (
    CodexModel(
        id="gpt-5.6-sol",
        display_name="GPT-5.6 Sol",
        description="Frontier agentic coding model for complex work.",
        supported_reasoning_efforts=tuple(
            (effort, "")
            for effort in ("low", "medium", "high", "xhigh", "max", "ultra")
        ),
        default_reasoning_effort="low",
        is_default=False,
        supports_personality=True,
        service_tiers=_PRIORITY_SERVICE_TIERS,
        upgrade=None,
    ),
    CodexModel(
        id="gpt-5.6-terra",
        display_name="GPT-5.6 Terra",
        description="Balanced agentic coding model for everyday work.",
        supported_reasoning_efforts=tuple(
            (effort, "")
            for effort in ("low", "medium", "high", "xhigh", "max", "ultra")
        ),
        default_reasoning_effort="medium",
        is_default=False,
        supports_personality=True,
        service_tiers=_PRIORITY_SERVICE_TIERS,
        upgrade=None,
    ),
    CodexModel(
        id="gpt-5.6-luna",
        display_name="GPT-5.6 Luna",
        description="Fast agentic coding model for focused tasks.",
        supported_reasoning_efforts=tuple(
            (effort, "")
            for effort in ("low", "medium", "high", "xhigh", "max")
        ),
        default_reasoning_effort="medium",
        is_default=False,
        supports_personality=True,
        service_tiers=_PRIORITY_SERVICE_TIERS,
        upgrade=None,
    ),
)


@dataclass(slots=True)
class _PendingResponse:
    event: threading.Event = field(default_factory=threading.Event)
    result: object | None = None
    error: str | None = None


@dataclass(slots=True)
class _TurnState:
    event: threading.Event = field(default_factory=threading.Event)
    final_text: str | None = None
    delta_text: str = ""
    streamed_length: int = 0
    on_delta: Callable[[str], None] | None = None
    on_activity: Callable[[str, dict[str, Any]], None] | None = None
    pending_activities: list[tuple[str, dict[str, Any]]] = field(
        default_factory=list
    )
    error: str | None = None


class CodexAppServerRuntime:
    """Thread-safe JSONL client backed by one long-running app-server."""

    _DEFAULT_COMMAND = (
        "codex",
        "app-server",
        "--stdio",
        "-c",
        "plugins={}",
        "-c",
        "mcp_servers={}",
        "--disable",
        "plugins",
        "--disable",
        "apps",
        "--disable",
        "browser_use",
        "--disable",
        "computer_use",
        "--disable",
        "in_app_browser",
        "--disable",
        "multi_agent",
        "--disable",
        "multi_agent_v2",
        "--disable",
        "goals",
        "--disable",
        "workspace_dependencies",
        "--disable",
        "image_generation",
        "--disable",
        "hooks",
    )

    def __init__(
        self,
        *,
        runtime_root: Path,
        command: Sequence[str] | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> None:
        self._runtime_root = runtime_root.resolve()
        self._command = tuple(command or self._DEFAULT_COMMAND)
        self._model = (
            model
            if model is not None
            else os.getenv("KOLIBRI_V3_CODEX_MODEL", "gpt-5.5").strip()
        )
        self._effort = (
            effort
            if effort is not None
            else os.getenv("KOLIBRI_V3_CODEX_EFFORT", "low").strip()
        )
        self._process: subprocess.Popen[str] | None = None
        self._reader: threading.Thread | None = None
        self._initialized = False
        self._account_ready = False
        self._closing = False
        self._next_request_id = 1
        self._pending: dict[int, _PendingResponse] = {}
        self._turns: dict[str, _TurnState] = {}
        self._product_threads: dict[
            tuple[str, str, str, str, str, str, str, str, str], str
        ] = {}
        self._product_thread_locks: dict[
            tuple[str, str, str, str, str, str, str, str, str],
            threading.Lock,
        ] = {}
        self._start_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._bundled_catalog_lock = threading.Lock()
        self._bundled_models: tuple[CodexModel, ...] | None = None

    @property
    def is_running(self) -> bool:
        with self._lifecycle_lock:
            return (
                self._initialized
                and self._process is not None
                and self._process.poll() is None
            )

    @property
    def configured_model(self) -> str | None:
        return self._model or None

    @property
    def configured_effort(self) -> str | None:
        return self._effort or None

    @staticmethod
    def _subprocess_environment() -> dict[str, str]:
        environment = {
            "HOME": str(Path.home()),
            "PATH": os.getenv("PATH", "/usr/local/bin:/usr/bin:/bin"),
        }
        for name in (
            "CODEX_HOME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        ):
            value = os.getenv(name)
            if value:
                environment[name] = value
        return environment

    def start(self) -> None:
        """Start and initialize the process once; safe to call repeatedly."""

        with self._start_lock:
            if self.is_running:
                return
            self._stop_process(
                CodexAppServerError("Codex app-server was restarted.")
            )
            self._runtime_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            environment = self._subprocess_environment()
            try:
                process = subprocess.Popen(
                    self._command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    cwd=self._runtime_root,
                    env=environment,
                )
            except OSError as exc:
                raise CodexAppServerError(
                    "Codex app-server could not be started."
                ) from exc
            with self._lifecycle_lock:
                self._process = process
                self._initialized = False
                self._closing = False
            reader = threading.Thread(
                target=self._reader_loop,
                args=(process,),
                name="kolibri-codex-app-server",
                daemon=True,
            )
            self._reader = reader
            reader.start()
            try:
                self._request_started(
                    "initialize",
                    {
                        "clientInfo": {
                            "name": "kolibri_v3",
                            "version": "1.0.0",
                        },
                        "capabilities": {"experimentalApi": True},
                    },
                    timeout=15.0,
                )
                self._notify_started("initialized", {})
            except CodexAppServerError:
                self._stop_process(
                    CodexAppServerError(
                        "Codex app-server initialization failed."
                    )
                )
                raise
            with self._lifecycle_lock:
                if self._process is not process or process.poll() is not None:
                    raise CodexAppServerError(
                        "Codex app-server stopped during initialization."
                    )
                self._initialized = True

    def stop(self) -> None:
        """Stop the owned process and release all ephemeral state."""

        with self._start_lock:
            self._stop_process(
                CodexAppServerError("Codex app-server was stopped.")
            )

    def list_models(self, *, timeout: float = 10.0) -> tuple[CodexModel, ...]:
        """Return the current account's visible, server-advertised models."""

        self.start()
        self._require_account(timeout=min(timeout, 10.0))
        response = self._request(
            "model/list",
            {
                "cursor": None,
                "includeHidden": False,
                "limit": 100,
            },
            timeout=timeout,
        )
        if not isinstance(response, dict) or not isinstance(
            response.get("data"),
            list,
        ):
            raise CodexAppServerError(
                "Codex app-server returned an invalid model catalog."
            )

        models: list[CodexModel] = []
        seen: set[str] = set()
        for raw in response["data"]:
            if not isinstance(raw, dict) or raw.get("hidden") is True:
                continue
            model_id = self._bounded_catalog_text(raw.get("model"), 120)
            display_name = self._bounded_catalog_text(
                raw.get("displayName"),
                120,
            )
            default_effort = self._bounded_catalog_text(
                raw.get("defaultReasoningEffort"),
                32,
            )
            if (
                model_id is None
                or display_name is None
                or default_effort is None
                or model_id in seen
            ):
                continue

            efforts: list[tuple[str, str]] = []
            raw_efforts = raw.get("supportedReasoningEfforts")
            if isinstance(raw_efforts, list):
                for raw_effort in raw_efforts[:16]:
                    if not isinstance(raw_effort, dict):
                        continue
                    effort_id = self._bounded_catalog_text(
                        raw_effort.get("reasoningEffort"),
                        32,
                    )
                    if effort_id is None:
                        continue
                    effort_description = (
                        self._bounded_catalog_text(
                            raw_effort.get("description"),
                            240,
                        )
                        or ""
                    )
                    if effort_id not in {item[0] for item in efforts}:
                        efforts.append((effort_id, effort_description))
            if default_effort not in {item[0] for item in efforts}:
                continue

            service_tiers: list[tuple[str, str, str]] = []
            raw_tiers = raw.get("serviceTiers")
            if isinstance(raw_tiers, list):
                for raw_tier in raw_tiers[:8]:
                    if not isinstance(raw_tier, dict):
                        continue
                    tier_id = self._bounded_catalog_text(
                        raw_tier.get("id"),
                        32,
                    )
                    tier_name = self._bounded_catalog_text(
                        raw_tier.get("name"),
                        80,
                    )
                    if (
                        tier_id is None
                        or _SERVICE_TIER_ID_PATTERN.fullmatch(tier_id) is None
                        or tier_name is None
                    ):
                        continue
                    tier_description = (
                        self._bounded_catalog_text(
                            raw_tier.get("description"),
                            240,
                        )
                        or ""
                    )
                    if tier_id not in {item[0] for item in service_tiers}:
                        service_tiers.append(
                            (tier_id, tier_name, tier_description)
                        )

            upgrade = self._bounded_catalog_text(raw.get("upgrade"), 120)
            description = (
                self._bounded_catalog_text(raw.get("description"), 500)
                or ""
            )
            models.append(
                CodexModel(
                    id=model_id,
                    display_name=display_name,
                    description=description,
                    supported_reasoning_efforts=tuple(efforts),
                    default_reasoning_effort=default_effort,
                    is_default=raw.get("isDefault") is True,
                    supports_personality=(
                        raw.get("supportsPersonality") is True
                    ),
                    service_tiers=tuple(service_tiers),
                    upgrade=upgrade,
                )
            )
            seen.add(model_id)
        bundled_models = self._list_bundled_models(
            timeout=min(timeout, 10.0),
        )
        merged_by_id: dict[str, CodexModel] = {}
        for model in (
            *_AUTHENTICATED_PREVIEW_MODELS,
            *bundled_models,
            *models,
        ):
            merged_by_id[model.id] = model
        merged_models: list[CodexModel] = []
        merged_seen: set[str] = set()
        for model in (
            *_AUTHENTICATED_PREVIEW_MODELS,
            *bundled_models,
            *models,
        ):
            if model.id in merged_seen:
                continue
            merged_models.append(merged_by_id[model.id])
            merged_seen.add(model.id)
        if not merged_models:
            raise CodexAppServerError(
                "Codex app-server returned an empty model catalog."
            )
        return tuple(merged_models)

    def _list_bundled_models(
        self,
        *,
        timeout: float,
    ) -> tuple[CodexModel, ...]:
        """Read the CLI's signed-in, executable fallback catalog.

        Some Codex versions can execute a newly released model while
        ``model/list`` still serves an older cached picker response.  The
        bundled catalog is CLI-owned capability metadata and is merged only
        after account authentication succeeds.
        """

        with self._bundled_catalog_lock:
            if self._bundled_models is not None:
                return self._bundled_models
            executable = self._command[0]
            if Path(executable).name not in {"codex", "codex.exe"}:
                self._bundled_models = ()
                return self._bundled_models
            environment = self._subprocess_environment()
            try:
                completed = subprocess.run(
                    (executable, "debug", "models", "--bundled"),
                    cwd=self._runtime_root,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    timeout=timeout,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                self._bundled_models = ()
                return self._bundled_models
            if (
                completed.returncode != 0
                or len(completed.stdout) > 2 * 1024 * 1024
            ):
                self._bundled_models = ()
                return self._bundled_models
            try:
                payload = json.loads(completed.stdout)
            except (TypeError, ValueError):
                self._bundled_models = ()
                return self._bundled_models
            raw_models = (
                payload.get("models")
                if isinstance(payload, dict)
                else None
            )
            if not isinstance(raw_models, list):
                self._bundled_models = ()
                return self._bundled_models

            parsed: list[CodexModel] = []
            seen: set[str] = set()
            for raw in raw_models[:100]:
                if (
                    not isinstance(raw, dict)
                    or raw.get("visibility") != "list"
                    or raw.get("supported_in_api") is not True
                ):
                    continue
                model_id = self._bounded_catalog_text(raw.get("slug"), 120)
                display_name = self._bounded_catalog_text(
                    raw.get("display_name"),
                    120,
                )
                default_effort = self._bounded_catalog_text(
                    raw.get("default_reasoning_level"),
                    32,
                )
                if (
                    model_id is None
                    or display_name is None
                    or default_effort is None
                    or model_id in seen
                ):
                    continue

                efforts: list[tuple[str, str]] = []
                raw_efforts = raw.get("supported_reasoning_levels")
                if isinstance(raw_efforts, list):
                    for raw_effort in raw_efforts[:16]:
                        if not isinstance(raw_effort, dict):
                            continue
                        effort_id = self._bounded_catalog_text(
                            raw_effort.get("effort"),
                            32,
                        )
                        if effort_id is None:
                            continue
                        description = (
                            self._bounded_catalog_text(
                                raw_effort.get("description"),
                                240,
                            )
                            or ""
                        )
                        if effort_id not in {item[0] for item in efforts}:
                            efforts.append((effort_id, description))
                if default_effort not in {item[0] for item in efforts}:
                    continue

                service_tiers: list[tuple[str, str, str]] = []
                raw_tiers = raw.get("service_tiers")
                if isinstance(raw_tiers, list):
                    for raw_tier in raw_tiers[:8]:
                        if not isinstance(raw_tier, dict):
                            continue
                        tier_id = self._bounded_catalog_text(
                            raw_tier.get("id"),
                            32,
                        )
                        tier_name = self._bounded_catalog_text(
                            raw_tier.get("name"),
                            80,
                        )
                        if (
                            tier_id is None
                            or _SERVICE_TIER_ID_PATTERN.fullmatch(tier_id)
                            is None
                            or tier_name is None
                        ):
                            continue
                        tier_description = (
                            self._bounded_catalog_text(
                                raw_tier.get("description"),
                                240,
                            )
                            or ""
                        )
                        if tier_id not in {item[0] for item in service_tiers}:
                            service_tiers.append(
                                (tier_id, tier_name, tier_description)
                            )
                parsed.append(
                    CodexModel(
                        id=model_id,
                        display_name=display_name,
                        description=(
                            self._bounded_catalog_text(
                                raw.get("description"),
                                500,
                            )
                            or ""
                        ),
                        supported_reasoning_efforts=tuple(efforts),
                        default_reasoning_effort=default_effort,
                        is_default=False,
                        supports_personality=(
                            raw.get("supports_personality") is True
                        ),
                        service_tiers=tuple(service_tiers),
                        upgrade=self._bounded_catalog_text(
                            raw.get("upgrade"),
                            120,
                        ),
                    )
                )
                seen.add(model_id)
            self._bundled_models = tuple(parsed)
            return self._bundled_models

    @staticmethod
    def _bounded_catalog_text(value: object, limit: int) -> str | None:
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized or len(normalized) > limit:
            return None
        return normalized

    def complete(
        self,
        *,
        tenant_id: str,
        product_thread_id: str,
        initial_prompt: str,
        followup_prompt: str,
        output_schema: dict[str, Any] | None,
        instructions: str,
        timeout: float,
        on_delta: Callable[[str], None] | None = None,
        on_activity: Callable[[str, dict[str, Any]], None] | None = None,
        execution_profile: str = "default",
        model: str | None = None,
        effort: str | None = None,
        service_tier: str | None = None,
        workspace_root: Path | None = None,
        sandbox: str = "read-only",
        approval_policy: str = "never",
        approvals_reviewer: str | None = None,
        cancellation_signal: threading.Event | None = None,
    ) -> str:
        """Run one model turn on the product chat's ephemeral Codex thread."""

        self.start()
        resolved_workspace = (
            workspace_root.resolve()
            if workspace_root is not None
            else self._runtime_root
        )
        selected_model = model if model is not None else self._model
        key = (
            tenant_id,
            product_thread_id,
            execution_profile,
            str(resolved_workspace),
            selected_model or "",
            service_tier or "",
            sandbox,
            approval_policy,
            approvals_reviewer or "",
        )
        lock = self._product_thread_lock(key)
        with lock:
            self._require_account(timeout=min(timeout, 10.0))
            with self._state_lock:
                codex_thread_id = self._product_threads.get(key)
            prompt = followup_prompt
            if codex_thread_id is None:
                codex_thread_id = self._start_thread(
                    instructions=instructions,
                    timeout=timeout,
                    model=selected_model,
                    workspace_root=resolved_workspace,
                    sandbox=sandbox,
                    approval_policy=approval_policy,
                    approvals_reviewer=approvals_reviewer,
                    service_tier=service_tier,
                )
                with self._state_lock:
                    self._product_threads[key] = codex_thread_id
                prompt = initial_prompt
            try:
                turn_params: dict[str, object] = {
                    "threadId": codex_thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "effort": (
                        effort
                        if effort is not None
                        else self._effort or None
                    ),
                    "approvalPolicy": approval_policy,
                }
                if approvals_reviewer is not None:
                    turn_params["approvalsReviewer"] = approvals_reviewer
                if output_schema is not None:
                    turn_params["outputSchema"] = output_schema
                if service_tier is not None:
                    turn_params["serviceTier"] = service_tier
                response = self._request(
                    "turn/start",
                    turn_params,
                    timeout=timeout,
                )
                turn_id = self._nested_id(response, "turn")
                with self._state_lock:
                    turn = self._turns.setdefault(turn_id, _TurnState())
                    turn.on_delta = on_delta
                    turn.on_activity = on_activity
                    pending_delta = turn.delta_text[turn.streamed_length :]
                    turn.streamed_length = len(turn.delta_text)
                    pending_activities = tuple(turn.pending_activities)
                    turn.pending_activities.clear()
                if pending_delta and on_delta is not None:
                    on_delta(pending_delta)
                if on_activity is not None:
                    for phase, item in pending_activities:
                        on_activity(phase, item)
                deadline = time.monotonic() + timeout
                while not turn.event.wait(
                    max(0.0, min(0.1, deadline - time.monotonic()))
                ):
                    if (
                        cancellation_signal is not None
                        and cancellation_signal.is_set()
                    ):
                        self._interrupt_turn(
                            codex_thread_id,
                            turn_id,
                            timeout=min(timeout, 5.0),
                        )
                        raise CodexAppServerError(
                            "Codex app-server turn was cancelled."
                        )
                    if time.monotonic() >= deadline:
                        self._interrupt_turn(
                            codex_thread_id,
                            turn_id,
                            timeout=min(timeout, 5.0),
                        )
                        raise CodexAppServerError(
                            "Codex app-server turn timed out."
                        )
                if turn.error is not None:
                    raise CodexAppServerError(turn.error)
                text = (
                    turn.delta_text
                    if on_delta is not None and turn.delta_text
                    else turn.final_text or turn.delta_text
                ).strip()
                if not text:
                    raise CodexAppServerError(
                        "Codex app-server returned an empty response."
                    )
                return text
            except CodexAppServerError:
                with self._state_lock:
                    self._product_threads.pop(key, None)
                raise
            finally:
                if "turn_id" in locals():
                    with self._state_lock:
                        self._turns.pop(turn_id, None)

    def _product_thread_lock(
        self,
        key: tuple[str, str, str, str, str, str, str, str, str],
    ) -> threading.Lock:
        with self._state_lock:
            return self._product_thread_locks.setdefault(
                key,
                threading.Lock(),
            )

    def _require_account(self, *, timeout: float) -> None:
        with self._lifecycle_lock:
            if self._account_ready:
                return
        response = self._request(
            "account/read",
            {"refreshToken": False},
            timeout=timeout,
        )
        if (
            not isinstance(response, dict)
            or response.get("account") is None
        ):
            raise CodexAppServerAuthenticationError(
                "Codex CLI login is required."
            )
        with self._lifecycle_lock:
            self._account_ready = True

    def _start_thread(
        self,
        *,
        instructions: str,
        timeout: float,
        model: str | None,
        workspace_root: Path,
        sandbox: str,
        approval_policy: str,
        approvals_reviewer: str | None,
        service_tier: str | None,
    ) -> str:
        params: dict[str, object] = {
            "cwd": str(workspace_root),
            "approvalPolicy": approval_policy,
            "sandbox": sandbox,
            "ephemeral": True,
            "baseInstructions": instructions,
            "developerInstructions": instructions,
            "dynamicTools": [],
            "selectedCapabilityRoots": [],
            "runtimeWorkspaceRoots": [str(workspace_root)],
        }
        selected_model = model if model is not None else self._model
        if selected_model:
            params["model"] = selected_model
        if approvals_reviewer is not None:
            params["approvalsReviewer"] = approvals_reviewer
        if service_tier is not None:
            params["serviceTier"] = service_tier
        response = self._request("thread/start", params, timeout=timeout)
        return self._nested_id(response, "thread")

    def _interrupt_turn(
        self,
        thread_id: str,
        turn_id: str,
        *,
        timeout: float,
    ) -> None:
        try:
            self._request(
                "turn/interrupt",
                {"threadId": thread_id, "turnId": turn_id},
                timeout=timeout,
            )
        except CodexAppServerError:
            pass

    @staticmethod
    def _nested_id(value: object, key: str) -> str:
        nested = value.get(key) if isinstance(value, dict) else None
        identifier = nested.get("id") if isinstance(nested, dict) else None
        if not isinstance(identifier, str) or not identifier:
            raise CodexAppServerError(
                f"Codex app-server returned an invalid {key} response."
            )
        return identifier

    def _request(
        self,
        method: str,
        params: dict[str, object],
        *,
        timeout: float,
    ) -> object:
        self.start()
        return self._request_started(method, params, timeout=timeout)

    def _request_started(
        self,
        method: str,
        params: dict[str, object],
        *,
        timeout: float,
    ) -> object:
        with self._state_lock:
            request_id = self._next_request_id
            self._next_request_id += 1
            pending = _PendingResponse()
            self._pending[request_id] = pending
        try:
            self._send(
                {"method": method, "id": request_id, "params": params}
            )
        except CodexAppServerError:
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise
        if not pending.event.wait(timeout):
            with self._state_lock:
                self._pending.pop(request_id, None)
            raise CodexAppServerError(
                f"Codex app-server request {method} timed out."
            )
        if pending.error is not None:
            raise CodexAppServerError(pending.error)
        return pending.result

    def _notify_started(
        self,
        method: str,
        params: dict[str, object],
    ) -> None:
        self._send({"method": method, "params": params})

    def _send(self, payload: dict[str, object]) -> None:
        data = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        with self._write_lock:
            with self._lifecycle_lock:
                process = self._process
                stream = process.stdin if process is not None else None
                alive = process is not None and process.poll() is None
            if not alive or stream is None:
                raise CodexAppServerError(
                    "Codex app-server is not running."
                )
            try:
                stream.write(data + "\n")
                stream.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                self._mark_broken(process)
                raise CodexAppServerError(
                    "Codex app-server connection was lost."
                ) from exc

    def _reader_loop(self, process: subprocess.Popen[str]) -> None:
        stream = process.stdout
        if stream is None:
            self._mark_broken(process)
            return
        try:
            for line in stream:
                try:
                    payload = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, dict):
                    self._handle_message(payload)
        except (OSError, UnicodeError, ValueError):
            pass
        finally:
            self._mark_broken(process)

    def _handle_message(self, payload: dict[str, object]) -> None:
        request_id = payload.get("id")
        if (
            isinstance(request_id, int)
            and ("result" in payload or "error" in payload)
        ):
            with self._state_lock:
                pending = self._pending.pop(request_id, None)
            if pending is None:
                return
            if "error" in payload:
                pending.error = self._protocol_error(payload.get("error"))
            else:
                pending.result = payload.get("result")
            pending.event.set()
            return

        method = payload.get("method")
        params = payload.get("params")
        if not isinstance(method, str):
            return
        if isinstance(request_id, int):
            self._deny_server_request(request_id)
            return
        if not isinstance(params, dict):
            return
        if method in {"item/started", "item/completed"}:
            turn_id = params.get("turnId")
            item = params.get("item")
            if isinstance(turn_id, str) and isinstance(item, dict):
                item_type = item.get("type")
                if item_type in {"commandExecution", "fileChange"}:
                    phase = (
                        "started"
                        if method == "item/started"
                        else "completed"
                    )
                    try:
                        activity = canonical_runtime_activity(phase, item)
                    except ValueError:
                        return
                    with self._state_lock:
                        turn = self._turns.setdefault(turn_id, _TurnState())
                        callback = turn.on_activity
                        if callback is None:
                            if len(turn.pending_activities) < 200:
                                turn.pending_activities.append(
                                    (phase, activity)
                                )
                    if callback is not None:
                        try:
                            callback(phase, activity)
                        except Exception:
                            with self._state_lock:
                                turn.error = (
                                    "Kolibri could not persist Codex "
                                    "developer activity."
                                )
                    if item_type != "agentMessage":
                        return
        if method == "item/agentMessage/delta":
            turn_id = params.get("turnId")
            delta = params.get("delta")
            if isinstance(turn_id, str) and isinstance(delta, str):
                with self._state_lock:
                    turn = self._turns.setdefault(turn_id, _TurnState())
                    turn.delta_text += delta
                    callback = turn.on_delta
                    if callback is not None:
                        turn.streamed_length += len(delta)
                if callback is not None:
                    try:
                        callback(delta)
                    except Exception:
                        with self._state_lock:
                            turn.error = (
                                "Kolibri could not persist the streamed "
                                "Codex response."
                            )
            return
        if method == "item/completed":
            turn_id = params.get("turnId")
            item = params.get("item")
            if (
                isinstance(turn_id, str)
                and isinstance(item, dict)
                and item.get("type") == "agentMessage"
                and item.get("phase") in {None, "final_answer"}
                and isinstance(item.get("text"), str)
            ):
                with self._state_lock:
                    turn = self._turns.setdefault(turn_id, _TurnState())
                    turn.final_text = str(item["text"])
            return
        if method == "turn/completed":
            turn_value = params.get("turn")
            if not isinstance(turn_value, dict):
                return
            turn_id = turn_value.get("id")
            if not isinstance(turn_id, str):
                return
            with self._state_lock:
                turn = self._turns.setdefault(turn_id, _TurnState())
                status = turn_value.get("status")
                if status != "completed":
                    error_value = turn_value.get("error")
                    error_message = (
                        error_value.get("message")
                        if isinstance(error_value, dict)
                        else None
                    )
                    turn.error = (
                        f"Codex app-server turn failed: "
                        f"{error_message.strip()[:300]}"
                        if isinstance(error_message, str)
                        and error_message.strip()
                        else "Codex app-server could not complete the turn."
                    )
                turn.event.set()

    def _deny_server_request(self, request_id: int) -> None:
        try:
            self._send(
                {
                    "id": request_id,
                    "error": {
                        "code": -32000,
                        "message": (
                            "Kolibri denies interactive app-server requests."
                        ),
                    },
                }
            )
        except CodexAppServerError:
            pass

    @staticmethod
    def _protocol_error(value: object) -> str:
        if isinstance(value, dict):
            message = value.get("message")
            if isinstance(message, str) and message.strip():
                return f"Codex app-server error: {message.strip()[:300]}"
        return "Codex app-server returned an error."

    def _mark_broken(self, process: subprocess.Popen[str]) -> None:
        with self._lifecycle_lock:
            if self._process is not process:
                return
            self._process = None
            self._initialized = False
            self._account_ready = False
        self._fail_waiters(
            CodexAppServerError("Codex app-server connection was lost.")
        )

    def _stop_process(self, error: CodexAppServerError) -> None:
        with self._lifecycle_lock:
            process = self._process
            self._process = None
            self._initialized = False
            self._account_ready = False
            self._closing = True
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                    process.wait(timeout=2)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        self._fail_waiters(error)
        with self._state_lock:
            self._product_threads.clear()
            self._product_thread_locks.clear()
        with self._lifecycle_lock:
            self._closing = False

    def _fail_waiters(self, error: CodexAppServerError) -> None:
        with self._state_lock:
            pending = tuple(self._pending.values())
            turns = tuple(self._turns.values())
            self._pending.clear()
            self._turns.clear()
        for request in pending:
            request.error = str(error)
            request.event.set()
        for turn in turns:
            turn.error = str(error)
            turn.event.set()
