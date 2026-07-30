"""Provider-neutral process-lifetime agent runtime contract.

Provider transports are deliberately kept behind :class:`AgentRuntime`.
Product chat and orchestration select an exact registered profile and never
switch providers after a run has been accepted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import threading
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, Protocol, runtime_checkable


AGENT_RUNTIME_SCHEMA_ID = "kolibri.agent-runtime"
AGENT_RUNTIME_SCHEMA_VERSION = "1.0"
AGENT_ACTIVITY_SCHEMA_ID = "kolibri.agent-activity"
AGENT_ACTIVITY_SCHEMA_VERSION = "1.0"
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{1,95}$")

AgentRuntimeMode = Literal["chat", "structured", "developer"]
AgentMessageRole = Literal["user", "assistant", "system"]
AccessMode = Literal["standard", "auto", "full"]
SandboxProfile = Literal["read-only", "workspace-write", "danger-full-access"]
ApprovalPolicy = Literal["never", "on-request"]
RuntimeActivityCallback = Callable[[str, dict[str, Any]], None]
RuntimeDeltaCallback = Callable[[str], None]
RuntimeActivityPhase = Literal["started", "completed"]


def _activity_text(value: object, *, limit: int) -> str:
    return str(value or "").strip()[:limit]


def canonical_runtime_activity(
    phase: RuntimeActivityPhase,
    item: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize every provider driver into Kolibri's single UI protocol."""

    if phase not in {"started", "completed"}:
        raise ValueError("runtime activity phase is invalid")
    item_id = _activity_text(item.get("id"), limit=160)
    item_type = _activity_text(item.get("type"), limit=40)
    if not item_id:
        raise ValueError("runtime activity id is required")
    status = _activity_text(item.get("status"), limit=40) or (
        "inProgress" if phase == "started" else "completed"
    )
    canonical: dict[str, Any] = {
        "schemaId": AGENT_ACTIVITY_SCHEMA_ID,
        "schemaVersion": AGENT_ACTIVITY_SCHEMA_VERSION,
        "id": item_id,
        "type": item_type,
        "status": status,
    }
    if item_type == "commandExecution":
        canonical.update(
            {
                "command": _activity_text(item.get("command"), limit=16_000),
                "cwd": _activity_text(item.get("cwd"), limit=4_096),
            }
        )
        if phase == "completed":
            canonical.update(
                {
                    "exitCode": item.get("exitCode"),
                    "durationMs": item.get("durationMs"),
                    "output": _activity_text(
                        item.get("output"),
                        limit=64_000,
                    ),
                }
            )
        return canonical
    if item_type != "fileChange":
        raise ValueError("runtime activity type is unsupported")

    changes: list[dict[str, str]] = []
    raw_changes = item.get("changes")
    if isinstance(raw_changes, list):
        for raw_change in raw_changes[:40]:
            if not isinstance(raw_change, Mapping):
                continue
            path = _activity_text(raw_change.get("path"), limit=4_096)
            if not path:
                continue
            changes.append(
                {
                    "path": path,
                    "kind": _activity_text(
                        raw_change.get("kind"),
                        limit=40,
                    )
                    or "update",
                    "diff": (
                        _activity_text(
                            raw_change.get("diff"),
                            limit=64_000,
                        )
                        if phase == "completed"
                        else ""
                    ),
                }
            )
    canonical["changes"] = changes
    return canonical


class AgentRuntimeError(RuntimeError):
    """Stable, public-safe runtime error returned by every implementation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        category: Literal[
            "configuration",
            "authentication",
            "unavailable",
            "invalid_output",
            "execution",
        ] = "execution",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.category = category
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class AgentRuntimeCapabilities:
    modes: frozenset[AgentRuntimeMode]
    streaming: bool
    structured_output: bool
    activity_events: bool
    persistent_sessions: bool
    model_catalog: bool = False

    def __post_init__(self) -> None:
        if not self.modes:
            raise ValueError("an agent runtime must support at least one mode")
        if "structured" in self.modes and not self.structured_output:
            raise ValueError("structured mode requires structured_output")
        if "developer" in self.modes and not self.activity_events:
            raise ValueError("developer mode requires activity_events")


@dataclass(frozen=True, slots=True)
class AgentRuntimeDescriptor:
    profile_id: str
    runtime_id: str
    display_name: str
    capabilities: AgentRuntimeCapabilities
    auto_priority: int = 100
    schema_id: str = AGENT_RUNTIME_SCHEMA_ID
    schema_version: str = AGENT_RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.profile_id):
            raise ValueError("profile_id is not a bounded runtime identifier")
        if not _IDENTIFIER.fullmatch(self.runtime_id):
            raise ValueError("runtime_id is not a bounded runtime identifier")
        if not self.display_name.strip() or len(self.display_name) > 120:
            raise ValueError("display_name is invalid")
        if self.schema_id != AGENT_RUNTIME_SCHEMA_ID:
            raise ValueError("unsupported agent runtime schema")
        if self.schema_version != AGENT_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported agent runtime schema version")


@dataclass(frozen=True, slots=True)
class AgentRuntimeMessage:
    role: AgentMessageRole
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip() or len(self.content) > 200_000:
            raise ValueError("runtime message content is invalid")


@dataclass(frozen=True, slots=True)
class AgentModelSelection:
    model_id: str | None = None
    reasoning_effort: str | None = None
    service_tier: str | None = None
    explicit_profile: bool = False

    def __post_init__(self) -> None:
        for name, value in (
            ("model_id", self.model_id),
            ("reasoning_effort", self.reasoning_effort),
            ("service_tier", self.service_tier),
        ):
            if value is not None and (
                not value.strip() or len(value) > 160 or "\x00" in value
            ):
                raise ValueError(f"{name} is invalid")


@dataclass(frozen=True, slots=True)
class AgentAccessPolicy:
    mode: AccessMode
    sandbox: SandboxProfile
    approval_policy: ApprovalPolicy
    approvals_reviewer: str | None = None

    def __post_init__(self) -> None:
        expected = {
            "standard": ("read-only", "never", None),
            "auto": ("workspace-write", "on-request", "auto_review"),
            "full": ("danger-full-access", "never", None),
        }
        actual = (
            self.sandbox,
            self.approval_policy,
            self.approvals_reviewer,
        )
        if actual != expected[self.mode]:
            raise ValueError("agent access policy fields are inconsistent")


@dataclass(frozen=True, slots=True)
class AgentWorkspace:
    reference: Literal["none", "repository"]
    root: Path | None = None

    def __post_init__(self) -> None:
        if self.reference == "none" and self.root is not None:
            raise ValueError("a non-workspace request cannot contain a root")
        if self.reference == "repository":
            if self.root is None or not self.root.is_absolute():
                raise ValueError("repository workspace must be absolute")


@dataclass(frozen=True, slots=True)
class AgentExecutionConfiguration:
    selection: AgentModelSelection = field(default_factory=AgentModelSelection)
    access: AgentAccessPolicy = field(
        default_factory=lambda: AgentAccessPolicy(
            mode="standard",
            sandbox="read-only",
            approval_policy="never",
        )
    )
    workspace: AgentWorkspace = field(
        default_factory=lambda: AgentWorkspace(reference="none")
    )


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    name: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not _IDENTIFIER.fullmatch(self.name):
            raise ValueError("tool name is invalid")
        object.__setattr__(
            self,
            "arguments",
            MappingProxyType(dict(self.arguments)),
        )


@dataclass(frozen=True, slots=True)
class AgentRuntimeRequest:
    tenant_id: str
    thread_id: str
    run_id: str
    credential_tenant_id: str
    mode: AgentRuntimeMode
    execution_profile: str
    messages: tuple[AgentRuntimeMessage, ...]
    initial_prompt: str
    followup_prompt: str
    instructions: str
    timeout_seconds: float
    guidance: str | None = None
    configuration: AgentExecutionConfiguration = field(
        default_factory=AgentExecutionConfiguration
    )
    output_schema: Mapping[str, Any] | None = None
    on_delta: RuntimeDeltaCallback | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    on_activity: RuntimeActivityCallback | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    cancellation_signal: threading.Event | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    schema_id: str = AGENT_RUNTIME_SCHEMA_ID
    schema_version: str = AGENT_RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_id != AGENT_RUNTIME_SCHEMA_ID:
            raise ValueError("unsupported agent runtime request schema")
        if self.schema_version != AGENT_RUNTIME_SCHEMA_VERSION:
            raise ValueError("unsupported agent runtime request version")
        for name, value in (
            ("tenant_id", self.tenant_id),
            ("thread_id", self.thread_id),
            ("run_id", self.run_id),
            ("credential_tenant_id", self.credential_tenant_id),
            ("execution_profile", self.execution_profile),
        ):
            if not value or len(value) > 512 or "\x00" in value:
                raise ValueError(f"{name} is invalid")
        if not self.messages or self.messages[-1].role != "user":
            raise ValueError("runtime request must end with a user message")
        if not self.initial_prompt.strip() or not self.followup_prompt.strip():
            raise ValueError("runtime prompts are required")
        if not self.instructions.strip():
            raise ValueError("runtime instructions are required")
        if self.guidance is not None and len(self.guidance) > 100_000:
            raise ValueError("runtime guidance is invalid")
        if self.timeout_seconds <= 0:
            raise ValueError("runtime timeout must be positive")
        if self.mode == "structured" and self.output_schema is None:
            raise ValueError("structured runtime request requires a schema")
        if self.mode != "structured" and self.output_schema is not None:
            raise ValueError("only structured runtime requests accept a schema")
        if self.output_schema is not None:
            object.__setattr__(
                self,
                "output_schema",
                MappingProxyType(dict(self.output_schema)),
            )


@dataclass(frozen=True, slots=True)
class AgentRuntimeResult:
    text: str | None = None
    tool_call: AgentToolCall | None = None
    session_id: str | None = None
    schema_id: str = AGENT_RUNTIME_SCHEMA_ID
    schema_version: str = AGENT_RUNTIME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (self.text is None) == (self.tool_call is None):
            raise ValueError("runtime result must contain text or one tool call")
        if self.text is not None and (
            not self.text.strip() or len(self.text) > 200_000
        ):
            raise ValueError("runtime result text is invalid")
        if self.session_id is not None and (
            not self.session_id.strip()
            or len(self.session_id) > 256
            or "\x00" in self.session_id
        ):
            raise ValueError("runtime session id is invalid")


@runtime_checkable
class AgentRuntime(Protocol):
    @property
    def descriptor(self) -> AgentRuntimeDescriptor: ...

    @property
    def model_catalog_backend(self) -> object | None: ...

    def start(self) -> None: ...

    def close(self) -> None: ...

    def execute(self, request: AgentRuntimeRequest) -> AgentRuntimeResult: ...


class DelegatingAgentRuntime:
    """Small adapter that exposes any transport through the common contract."""

    def __init__(
        self,
        *,
        descriptor: AgentRuntimeDescriptor,
        execute: Callable[[AgentRuntimeRequest], AgentRuntimeResult],
        start: Callable[[], None] | None = None,
        close: Callable[[], None] | None = None,
        model_catalog_backend: object | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._execute = execute
        self._start = start or (lambda: None)
        self._close = close or (lambda: None)
        self._model_catalog_backend = model_catalog_backend

    @property
    def descriptor(self) -> AgentRuntimeDescriptor:
        return self._descriptor

    @property
    def model_catalog_backend(self) -> object | None:
        return self._model_catalog_backend

    def start(self) -> None:
        self._start()

    def close(self) -> None:
        self._close()

    def execute(self, request: AgentRuntimeRequest) -> AgentRuntimeResult:
        if request.mode not in self.descriptor.capabilities.modes:
            raise AgentRuntimeError(
                "agent_runtime_mode_not_supported",
                "Выбранный агент не поддерживает этот режим.",
                category="configuration",
            )
        return self._execute(request)


class AgentRuntimeRegistry:
    """Thread-safe, data-driven registry keyed by the exact profile ID."""

    def __init__(self) -> None:
        self._runtimes: dict[str, AgentRuntime] = {}
        self._capabilities: dict[str, object] = {}
        self._start_errors: dict[str, str] = {}
        self._lock = threading.RLock()

    def register_capability(
        self,
        capability_id: str,
        implementation: object,
    ) -> None:
        """Bind one provider-neutral process capability to this registry."""

        if not _IDENTIFIER.fullmatch(capability_id):
            raise ValueError("capability_id is not a bounded identifier")
        with self._lock:
            existing = self._capabilities.get(capability_id)
            if existing is implementation:
                return
            if existing is not None:
                raise ValueError(
                    f"duplicate agent runtime capability: {capability_id}"
                )
            self._capabilities[capability_id] = implementation

    def capability(self, capability_id: str) -> object | None:
        if not _IDENTIFIER.fullmatch(capability_id):
            return None
        with self._lock:
            return self._capabilities.get(capability_id)

    def register(self, runtime: AgentRuntime) -> None:
        descriptor = runtime.descriptor
        with self._lock:
            if descriptor.profile_id in self._runtimes:
                raise ValueError(
                    f"duplicate agent runtime profile: {descriptor.profile_id}"
                )
            self._runtimes[descriptor.profile_id] = runtime

    def descriptors(self) -> tuple[AgentRuntimeDescriptor, ...]:
        with self._lock:
            return tuple(
                runtime.descriptor
                for runtime in sorted(
                    self._runtimes.values(),
                    key=lambda item: (
                        item.descriptor.auto_priority,
                        item.descriptor.profile_id,
                    ),
                )
            )

    def require(self, profile_id: str) -> AgentRuntime:
        with self._lock:
            runtime = self._runtimes.get(profile_id)
        if runtime is None:
            raise AgentRuntimeError(
                "agent_runtime_not_registered",
                "Выбранный агент не зарегистрирован на этом runtime.",
                category="configuration",
            )
        return runtime

    def resolve(
        self,
        *,
        requested_profile: str,
        connected_profiles: Mapping[str, str],
    ) -> tuple[AgentRuntime, str]:
        """Resolve once from server-owned connected profiles.

        An explicit profile either resolves exactly or fails. ``auto`` may
        choose the first registered connected runtime by descriptor priority;
        that choice is returned to the caller and is not retried elsewhere.
        """

        if requested_profile != "auto":
            runtime = self.require(requested_profile)
            credential_tenant_id = connected_profiles.get(requested_profile)
            if credential_tenant_id is None:
                raise AgentRuntimeError(
                    "provider_not_connected",
                    "Эта модель ещё не подключена суперадминистратором.",
                    category="authentication",
                )
            return runtime, credential_tenant_id
        for descriptor in self.descriptors():
            credential_tenant_id = connected_profiles.get(descriptor.profile_id)
            if credential_tenant_id is not None:
                return self.require(descriptor.profile_id), credential_tenant_id
        raise AgentRuntimeError(
            "provider_not_connected",
            "Суперадминистратор ещё не подключил ни одного агента.",
            category="authentication",
        )

    def start_all(self) -> Mapping[str, str]:
        """Start every registered runtime without making one provider global.

        A failed eager start is recorded for diagnostics. Exact execution may
        retry its own transport later, but the registry never substitutes a
        different runtime.
        """

        errors: dict[str, str] = {}
        for descriptor in self.descriptors():
            runtime = self.require(descriptor.profile_id)
            try:
                runtime.start()
            except Exception as exc:  # transport-specific error stays private
                errors[descriptor.profile_id] = type(exc).__name__
        with self._lock:
            self._start_errors = errors
        return MappingProxyType(dict(errors))

    def close_all(self) -> Mapping[str, str]:
        errors: dict[str, str] = {}
        for descriptor in reversed(self.descriptors()):
            runtime = self.require(descriptor.profile_id)
            try:
                runtime.close()
            except Exception as exc:  # best-effort process shutdown
                errors[descriptor.profile_id] = type(exc).__name__
        return MappingProxyType(dict(errors))

    def start_errors(self) -> Mapping[str, str]:
        with self._lock:
            return MappingProxyType(dict(self._start_errors))

    def model_catalog_backend(self) -> object | None:
        for descriptor in self.descriptors():
            runtime = self.require(descriptor.profile_id)
            if (
                descriptor.capabilities.model_catalog
                and runtime.model_catalog_backend is not None
            ):
                return runtime.model_catalog_backend
        return None
