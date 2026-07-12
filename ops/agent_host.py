#!/usr/bin/env python3
"""Persistent Kolibri remote agent host."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import hmac
import json
import os
import platform
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ops.control_plane_endpoint import resolve_home_control_plane_url
except ImportError:  # installed standalone beside this script
    from control_plane_endpoint import resolve_home_control_plane_url

try:
    from ops.release_helper import (
        RELEASE_CAPABILITY,
        RELEASE_TASK_KINDS,
        ReleaseHelperClient,
        ReleaseInstallError,
    )
except ImportError:  # installed standalone beside this script
    from release_helper import (
        RELEASE_CAPABILITY,
        RELEASE_TASK_KINDS,
        ReleaseHelperClient,
        ReleaseInstallError,
    )

try:
    from ops.runner_access import RunnerAccessError, load_runner_access_manifest
except ImportError:  # installed standalone beside this script
    from runner_access import RunnerAccessError, load_runner_access_manifest


STOP = False
AGENT_HOST_RUNTIME_SCHEMA = "kolibri.agent-host-runtime.v1"
RELEASE_MANIFEST_SCHEMA = "kolibri.release.v1"
AGENT_HOST_RUNTIME_PATH = "ops/agent_host.py"
MIMO_RESPONSE_AGENT_NAME = "kolibri-response-only"
MIMO_RESPONSE_AGENT_PROFILE_PATH = "ops/mimo/kolibri-response-only.md"
MIMO_RESPONSE_PROFILE_MAX_BYTES = 16 * 1024
MIMO_RESPONSE_PROFILE_SHA256 = "80cc13e7dd89c8045c8317d55b4ebe96dccd76a371a2b51f4c1cd5c7cec2ca45"
LEASE_HEARTBEAT_PROBE_KIND = "lease_heartbeat_probe"
LEASE_HEARTBEAT_PROBE_SCHEMA = "kolibri.lease-heartbeat-probe.v1"
LEASE_HEARTBEAT_PROBE_MIN_SECONDS = 61
LEASE_HEARTBEAT_PROBE_MAX_SECONDS = 180
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
IMAGE_EVIDENCE_SCHEMA = "kolibri.image-generation-evidence.v1"
MAX_FACTORY_IMAGE_BYTES = 6 * 1024 * 1024
READ_ONLY_PERMISSION_PACK_MARKERS = {"read_only", "readonly", "read-only", "no_push", "no-push", "nopush"}
FORBIDDEN_READ_ONLY_PERMISSIONS = {"full_autonomy", "git_push", "write_worktree"}
WRITE_WORKTREE_TASK_KINDS = {"impl_factory_smoke", "impl_retry_error_clearance"}
GIT_PUSH_TASK_KINDS = {"impl_factory_smoke", "impl_retry_error_clearance"}
MIMO_DIRECT_KINDS = {"owner_remote_task", "direct_mimo", "mimo_direct", "mimo_task"}
SAFE_MIMO_RESULT_FIELDS = {
    "answer",
    "blockers",
    "branch",
    "changed_files",
    "commit",
    "message",
    "next_action",
    "output",
    "pr_url",
    "pull_request_url",
    "response",
    "result",
    "status",
    "summary",
    "tests",
    "text",
}
SECRET_FIELD_HINTS = ("authorization", "cookie", "key", "password", "secret", "token")
CONTRACT_STATUSES = {"completed", "blocked", "failed"}
CONTRACT_RESULT_FIELDS = [
    "task_id",
    "status",
    "requested_runner",
    "runner",
    "runner_binding_verified",
    "changed_files",
    "artifact_dir",
    "required_artifacts_present",
    "required_artifacts_missing",
    "write_scope",
    "write_scope_violations",
    "read_only",
    "product_code_modification_forbidden",
    "product_code_changed",
    "push_attempted",
    "push_blocked",
    "blocked_reason",
    "failure_reason",
    "tests_run",
    "backend_test_environment",
    "next_recommended_task",
]
SUPPORTED_TASK_KINDS = {
    "direct_mimo",
    "impl_factory_smoke",
    "impl_retry_error_clearance",
    "mimo_direct",
    "mimo_task",
    "orchestrator_chat_response",
    "owner_remote_task",
    "read_only_probe",
    "review_pr",
    "telegram_chat_response",
    "telegram_image_generation",
    "image_generation",
    LEASE_HEARTBEAT_PROBE_KIND,
} | set(RELEASE_TASK_KINDS)
NO_PUSH_FLAGS = ("git_push_forbidden", "no_push", "read_only")
PRODUCT_CODE_FORBIDDEN_FLAGS = ("product_code_modification_forbidden", "read_only")
REQUIRED_ARTIFACT_KEYS = ("required_outputs", "required_artifacts")
PUSH_PERMISSION_NAMES = {"git_push", "full_autonomy"}
FULL_AUTONOMY_PACKS = {"full_autonomy", "full-autonomy", "autonomous_full"}
CANONICAL_RUN_ARTIFACT_FILES = ("PLAN.md", "ACTIONS.md", "TESTS.md", "RESULT.md", "NEXT.md")
CANONICAL_RUN_ARTIFACT_DIR_KEYS = (
    "canonical_run_artifact_dir",
    "run_artifact_dir",
    "run_artifacts_dir",
)
CANONICAL_RUN_ARTIFACT_ALIAS_KEYS = (
    "canonical_run_artifact_aliases",
    "run_artifact_aliases",
    "run_artifacts_aliases",
)
BACKEND_TEST_ENV_KEYS = (
    "backend_python_verification_env",
    "backend_test_environment",
    "backend_verification_environment",
)
BACKEND_TEST_ENV_TYPES = {"backend_python", "python_backend"}
SUPPORTED_AI_RUNNERS = {"api", "codex", "local_llm", "mimo"}
MIMO_AUTO25_MODEL = "mimo/mimo-auto"
MIMO_AUTO25_DISPLAY_NAME = "Mimo Auto 2.5"
MIMO_AUTO25_CLI_CONTRACT = "mimo-auto25-response-only-v2"
MIMO_AUTO25_DIRECT_CLI_CONTRACT = "mimo-auto25-direct-permission-bypass-v1"
FACTORY_PROVIDER_CONTRACT = "kolibri.factory-provider.readonly.v1"
EXTERNAL_PROVIDER_AUTH_HMAC_CONTRACT = "kolibri.external-provider-hmac.v1"
EXTERNAL_PROVIDER_CREDENTIAL_SCHEMA = "kolibri.external-provider-credential.v1"
EXTERNAL_CODEX_PROVIDER_RUNTIMES = frozenset({
    "macos_launchagent",
    "home_systemd_user",
})
CODEX_TASK_MODEL = "gpt-5.5"
CODEX_READINESS_MARKER = "KOLIBRI_CODEX_READY"
CODEX_PROVIDER_NETWORK_INSTRUCTION = (
    "Provider network policy: use only the native web_search tool for fresh internet data. "
    "Do not run curl, wget, or other shell network clients. Use no more than three focused "
    "search queries, open only the authoritative sources needed, cite them, and answer promptly. "
    "Do not search when the task does not require current internet information."
)
NATIVE_WEB_SEARCH_EVIDENCE_SCHEMA = "kolibri.native-web-search-evidence.v1"
MAX_NATIVE_WEB_SEARCH_QUERIES = 3
MAX_NATIVE_WEB_SEARCH_EVENTS = 12
MAX_NATIVE_WEB_SEARCH_QUERY_BYTES = 2_048
PROVIDER_PROXY_ENV = "KOLIBRI_PROVIDER_PROXY_URL"
PROVIDER_NO_PROXY_BASE = (
    "localhost",
    "127.0.0.1",
    "::1",
    "home",
    "api.telegram.org",
    "kolibriai.ru",
)
GLOBAL_PROXY_VARIABLES = (
    "ALL_PROXY",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


def _canonical_release_agent_host(
    current_link: str | Path | None = None,
    release_root: str | Path | None = None,
) -> tuple[Path, dict[str, Any]] | None:
    """Return the root-owned release runtime selected by the atomic current link.

    ``/usr/local/bin/kolibri-agent-host`` remains the bootstrap/fallback entry
    point.  It may re-exec a signed release only after the privileged installer
    has published a direct child of the immutable release root and the runtime
    bytes still match that release's canonical manifest.
    """

    configured_current = Path(
        current_link
        or os.environ.get("KOLIBRI_RELEASE_CURRENT_LINK")
        or "/opt/kolibri-ai/current"
    )
    configured_root = Path(
        release_root
        or os.environ.get("KOLIBRI_RELEASE_ROOT")
        or "/opt/kolibri-ai/releases"
    )
    if not configured_current.exists() and not configured_current.is_symlink():
        return None
    try:
        current_stat = configured_current.lstat()
        if not stat.S_ISLNK(current_stat.st_mode):
            raise RuntimeError("agent_host_release_current_not_symlink")
        root = configured_root.resolve(strict=True)
        selected = configured_current.resolve(strict=True)
        if selected.parent != root or selected == root:
            raise RuntimeError("agent_host_release_current_boundary_invalid")
        root_stat = root.stat()
        selected_stat = selected.stat()
        if (
            not stat.S_ISDIR(root_stat.st_mode)
            or not stat.S_ISDIR(selected_stat.st_mode)
            or root_stat.st_mode & 0o022
            or selected_stat.st_mode & 0o022
        ):
            raise RuntimeError("agent_host_release_runtime_permissions_invalid")
        manifest_path = selected / ".kolibri-release" / "manifest.json"
        if manifest_path.resolve(strict=True) != manifest_path:
            raise RuntimeError("agent_host_release_runtime_boundary_invalid")
        manifest_stat = manifest_path.lstat()
        if (
            not stat.S_ISREG(manifest_stat.st_mode)
            or manifest_stat.st_mode & 0o022
        ):
            raise RuntimeError("agent_host_release_runtime_permissions_invalid")
        trusted_owner = root_stat.st_uid
        if (
            trusted_owner not in {0, os.geteuid()}
            or current_stat.st_uid != trusted_owner
            or selected_stat.st_uid != trusted_owner
            or manifest_stat.st_uid != trusted_owner
        ):
            raise RuntimeError("agent_host_release_runtime_owner_invalid")
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != RELEASE_MANIFEST_SCHEMA
        ):
            raise RuntimeError("agent_host_release_manifest_invalid")
        canonical = json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if canonical != manifest_bytes:
            raise RuntimeError("agent_host_release_manifest_not_canonical")
        release_id = str(manifest.get("release_id") or "")
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", release_id)
            or selected.name != release_id
        ):
            raise RuntimeError("agent_host_release_manifest_invalid")
        files = manifest.get("files")
        if not isinstance(files, list):
            raise RuntimeError("agent_host_release_manifest_invalid")
        records = [item for item in files if isinstance(item, dict) and item.get("path") == AGENT_HOST_RUNTIME_PATH]
        profile_records = [
            item
            for item in files
            if isinstance(item, dict) and item.get("path") == MIMO_RESPONSE_AGENT_PROFILE_PATH
        ]
        if not records and not profile_records:
            # One migration-only compatibility case: historical signed
            # product releases predate both immutable Agent Host runtime
            # records.  They are never executed as Agent Host code; the
            # root-managed bootstrap remains active until a complete signed
            # runtime/profile pair is selected.
            return None
        if len(records) != 1:
            raise RuntimeError("agent_host_release_runtime_not_manifested")
        if len(profile_records) != 1:
            raise RuntimeError("mimo_response_profile_not_manifested")
        runtime = selected / AGENT_HOST_RUNTIME_PATH
        response_profile = selected / MIMO_RESPONSE_AGENT_PROFILE_PATH
        if (
            runtime.resolve(strict=True) != runtime
            or response_profile.resolve(strict=True) != response_profile
        ):
            raise RuntimeError("agent_host_release_runtime_boundary_invalid")
        runtime_stat = runtime.lstat()
        response_profile_stat = response_profile.lstat()
        if (
            not stat.S_ISREG(runtime_stat.st_mode)
            or not stat.S_ISREG(response_profile_stat.st_mode)
            or runtime_stat.st_mode & 0o022
            or response_profile_stat.st_mode & 0o022
            or not runtime_stat.st_mode & 0o111
            or not 1 <= response_profile_stat.st_size <= MIMO_RESPONSE_PROFILE_MAX_BYTES
        ):
            raise RuntimeError("agent_host_release_runtime_permissions_invalid")
        if (
            runtime_stat.st_uid != trusted_owner
            or response_profile_stat.st_uid != trusted_owner
        ):
            raise RuntimeError("agent_host_release_runtime_owner_invalid")
        runtime_sha256 = hashlib.sha256(runtime.read_bytes()).hexdigest()
        response_profile_sha256 = hashlib.sha256(response_profile.read_bytes()).hexdigest()
        if records[0].get("sha256") != runtime_sha256:
            raise RuntimeError("agent_host_release_runtime_digest_mismatch")
        if profile_records[0].get("sha256") != response_profile_sha256:
            raise RuntimeError("mimo_response_profile_digest_mismatch")
        if (
            records[0].get("size_bytes") != runtime_stat.st_size
            or records[0].get("mode") != f"{stat.S_IMODE(runtime_stat.st_mode):04o}"
            or profile_records[0].get("size_bytes") != response_profile_stat.st_size
            or profile_records[0].get("mode")
            != f"{stat.S_IMODE(response_profile_stat.st_mode):04o}"
        ):
            raise RuntimeError("agent_host_release_runtime_metadata_mismatch")
        if response_profile_sha256 != MIMO_RESPONSE_PROFILE_SHA256:
            raise RuntimeError("mimo_response_profile_contract_invalid")
        manifest_digest = f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}"
        return runtime, {
            "schema_version": AGENT_HOST_RUNTIME_SCHEMA,
            "status": "release_bound",
            "release_id": release_id,
            "manifest_digest": manifest_digest,
            "runtime_path": AGENT_HOST_RUNTIME_PATH,
            "runtime_sha256": runtime_sha256,
            "response_profile_path": MIMO_RESPONSE_AGENT_PROFILE_PATH,
            "response_profile_sha256": response_profile_sha256,
        }
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise RuntimeError("agent_host_release_runtime_invalid") from exc


def agent_host_runtime_identity(source_path: str | Path | None = None) -> dict[str, Any]:
    source = Path(source_path or __file__).resolve()
    selected = _canonical_release_agent_host()
    if selected is not None:
        runtime, identity = selected
        if source == runtime.resolve():
            return identity
    try:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        digest = ""
    return {
        "schema_version": AGENT_HOST_RUNTIME_SCHEMA,
        "status": "bootstrap",
        "release_id": None,
        "manifest_digest": None,
        "runtime_path": "bootstrap",
        "runtime_sha256": digest,
        "response_profile_path": MIMO_RESPONSE_AGENT_PROFILE_PATH,
        "response_profile_sha256": None,
    }


def maybe_reexec_release_agent_host() -> bool:
    """Re-exec the currently selected immutable Agent Host release, if any."""

    selected = _canonical_release_agent_host()
    if selected is None:
        return False
    runtime, _identity = selected
    if Path(__file__).resolve() == runtime.resolve():
        return False
    release_root = runtime.parent.parent
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(release_root) + (os.pathsep + existing if existing else "")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    os.execve(
        sys.executable,
        [sys.executable, "-B", str(runtime), *sys.argv[1:]],
        environment,
    )
    return True  # pragma: no cover - successful execve never returns


SECRET_REDACTION_MARKERS = (
    "api_key",
    "authorization",
    "bearer",
    "password",
    "refresh_token",
    "secret",
    "token",
)
MAX_PUBLIC_REASONING_SUMMARY_BYTES = 16 * 1024
PUBLIC_REASONING_PRIVATE_PATTERN = re.compile(
    r"(?:\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b|\b192\.168\.\d{1,3}\.\d{1,3}\b|"
    r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b|/home/|/users/)",
    re.IGNORECASE,
)


class BackendTestEnvironmentError(RuntimeError):
    """Raised when an explicit backend verification environment cannot be prepared."""


class RunnerExecutionError(RuntimeError):
    """Raised when a requested AI runner cannot execute on this node."""

    def __init__(self, error_type: str, runner: str, message: str | None = None, retry: bool = False):
        if message is None:
            message = runner
            runner = "mimo"
        super().__init__(message)
        self.error_type = error_type
        self.runner = runner
        self.retry = retry


class PermissionContractError(RuntimeError):
    """Raised when a read-only/no-push permission pack requests write powers."""

    def __init__(self, classification: dict[str, Any]):
        self.classification = classification
        permissions = ", ".join(classification.get("forbidden_permissions") or [])
        super().__init__(f"read-only/no-push permission pack forbids requested runtime permissions: {permissions}")


class TaskProcessInterrupted(RuntimeError):
    """A local process was fenced by the authoritative task lifecycle."""

    def __init__(self, error_type: str, message: str, *, retry: bool = False):
        super().__init__(f"{error_type}:{message}")
        self.error_type = error_type
        self.retry = retry


def task_max_attempts(task: dict[str, Any], *, default: int = 4) -> int:
    """Consume the canonical total-attempt budget with legacy read support."""

    raw = task.get("max_attempts")
    if raw is None:
        legacy = task.get("max_retries")
        raw = legacy + 1 if isinstance(legacy, int) and not isinstance(legacy, bool) else default
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        return default
    return min(raw, 100)


def task_has_attempt_budget(task: dict[str, Any]) -> bool:
    return int(task.get("attempt", 0)) < task_max_attempts(task)


def provider_runner_proxy_environment(
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build proxy variables only for Mimo/Codex child processes.

    The Agent Host service receives a dedicated Kolibri variable rather than
    global ``HTTPS_PROXY``.  This keeps Home Control Plane, mesh, backend and
    ordinary build commands on their existing routes.
    """

    values = os.environ if source is None else source
    proxy_url = str(values.get(PROVIDER_PROXY_ENV) or "").strip()
    if not proxy_url:
        return {}
    parsed = urllib.parse.urlsplit(proxy_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.port is None
        or not 1024 <= parsed.port <= 65535
    ):
        raise RuntimeError("provider_proxy_contract_invalid")
    manifest_path = str(values.get("KOLIBRI_MESH_MEMBERSHIP_MANIFEST") or "").strip()
    if not manifest_path:
        raise RuntimeError("provider_proxy_membership_unavailable")
    try:
        try:
            from ops.fleet_membership import MeshMembershipSource
        except ImportError:  # installed standalone beside this script
            from fleet_membership import MeshMembershipSource
        snapshot = MeshMembershipSource(manifest_path).load()
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError("provider_proxy_membership_unavailable") from exc
    direct_hosts = list(PROVIDER_NO_PROXY_BASE)
    for member in snapshot.members:
        direct_hosts.extend((member.node_id, member.mesh_ip))
    no_proxy = ",".join(dict.fromkeys(direct_hosts))
    canonical = f"http://127.0.0.1:{parsed.port}"
    return {
        "HTTPS_PROXY": canonical,
        "HTTP_PROXY": canonical,
        "https_proxy": canonical,
        "http_proxy": canonical,
        "NO_PROXY": no_proxy,
        "no_proxy": no_proxy,
    }


def agent_child_environment(
    overrides: dict[str, str] | None = None,
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return a child environment with no inherited machine-global proxy."""

    environment = dict(os.environ if source is None else source)
    for name in GLOBAL_PROXY_VARIABLES:
        environment.pop(name, None)
    if overrides:
        environment.update(overrides)
    return environment


class ResponseOnlyToolEventError(RuntimeError):
    """Mimo emitted a tool event despite the response-only agent profile."""


class ResponseOnlyToolOutputError(RuntimeError):
    """A response-only runner serialized a tool call as assistant text."""


class NativeWebSearchEvidenceError(RuntimeError):
    """A Codex native-search JSONL trace exceeded the bounded evidence policy."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mimo_auto25_runner_contract() -> dict[str, Any]:
    """Return the response-only Mimo contract advertised to Home."""
    return {
        "provider": "mimo",
        "model": MIMO_AUTO25_MODEL,
        "display_name": MIMO_AUTO25_DISPLAY_NAME,
        "model_version": "2.5",
        "cli_contract": MIMO_AUTO25_CLI_CONTRACT,
        "authorization_mode": "no_user_auth",
        "user_authorization_required": False,
        "permission_mode": "deny_all_response_only",
        "output_format": "json",
        "worktree_scoped": True,
        "factory_provider_contract": FACTORY_PROVIDER_CONTRACT,
        "prompt_transport": "file",
        "sandbox": "read-only",
        "execution_scope": "response_only",
        "response_agent": MIMO_RESPONSE_AGENT_NAME,
        "response_agent_profile": MIMO_RESPONSE_AGENT_PROFILE_PATH,
        "response_agent_tools": [],
        "external_plugins": "disabled",
    }


def mimo_auto25_direct_runner_contract() -> dict[str, Any]:
    """Describe the legacy write-capable Mimo path without safe-route claims."""

    return {
        "provider": "mimo",
        "model": MIMO_AUTO25_MODEL,
        "display_name": MIMO_AUTO25_DISPLAY_NAME,
        "model_version": "2.5",
        "cli_contract": MIMO_AUTO25_DIRECT_CLI_CONTRACT,
        "authorization_mode": "no_user_auth",
        "user_authorization_required": False,
        "permission_mode": "dangerously_skip_permissions",
        "output_format": "json",
        "worktree_scoped": False,
        "working_directory": "task-worktree",
        "prompt_transport": "argv",
        "sandbox": "none",
        "response_agent": None,
        "response_agent_tools": None,
        "external_plugins": "cli_default",
    }


def codex_factory_runner_contract() -> dict[str, Any]:
    """Return the safe contract required by the Home provider gateway."""

    return {
        "provider": "codex",
        "model": CODEX_TASK_MODEL,
        "display_name": "Codex authenticated runner",
        "authorization_mode": "node_managed",
        "authorization_flow": "browser_device",
        "user_authorization_required": False,
        "permission_mode": "task_contract",
        "output_format": "jsonl",
        "worktree_scoped": True,
        "factory_provider_contract": FACTORY_PROVIDER_CONTRACT,
        "prompt_transport": "stdin",
        "sandbox": "read-only",
        "network_access": "provider_managed_search",
    }


def codex_direct_runner_contract() -> dict[str, Any]:
    """Describe the legacy write-capable Codex invocation truthfully."""

    return {
        "provider": "codex",
        "model": CODEX_TASK_MODEL,
        "display_name": "Codex authenticated runner",
        "authorization_mode": "node_managed",
        "authorization_flow": "browser_device",
        "user_authorization_required": False,
        "permission_mode": "danger_full_access",
        "output_format": "jsonl",
        "worktree_scoped": False,
        "working_directory": "task-worktree",
        "prompt_transport": "stdin",
        "sandbox": "danger-full-access",
        "network_access": "provider_default",
    }


def is_factory_provider_task(task: dict[str, Any]) -> bool:
    envelope = task_envelope(task)
    source = envelope.get("source") if isinstance(envelope.get("source"), dict) else {}
    return (
        str(task.get("kind") or envelope.get("kind") or "") == "owner_remote_task"
        and source.get("kind") == "kolibri_provider_gateway"
        and source.get("control_plane") == "home"
    )


def is_response_only_provider_task(task: dict[str, Any]) -> bool:
    """Return whether a provider call is a response boundary, not code work."""

    envelope = task_envelope(task)
    task_kind = str(task.get("kind") or envelope.get("kind") or "")
    constraints = (
        envelope.get("constraints")
        if isinstance(envelope.get("constraints"), dict)
        else {}
    )
    response_kind = task_kind in {
        "orchestrator_chat_response",
        "telegram_chat_response",
    }
    declared_readonly = (
        task_kind == "owner_remote_task"
        and constraints.get("read_only") is True
        and not envelope.get("write_scope")
    )
    return bool(is_factory_provider_task(task) or response_kind or declared_readonly)


def load_mimo_response_agent_profile(
    configured_path: str | Path | None = None,
) -> tuple[bytes, str]:
    """Load the bundled/root-managed no-tools profile and fail closed."""

    candidates = []
    explicit = configured_path or os.environ.get("KOLIBRI_MIMO_RESPONSE_AGENT_PROFILE")
    if explicit:
        candidates.append(Path(explicit))
    else:
        candidates.extend([
            Path(__file__).resolve().parent / "mimo" / f"{MIMO_RESPONSE_AGENT_NAME}.md",
            Path("/usr/local/lib/kolibri/mimo") / f"{MIMO_RESPONSE_AGENT_NAME}.md",
        ])
    source = next((candidate for candidate in candidates if candidate.exists()), None)
    if source is None:
        raise RuntimeError("mimo_response_profile_missing")
    try:
        info = source.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_mode & 0o022
            or info.st_uid not in {0, os.geteuid()}
            or not 1 <= info.st_size <= MIMO_RESPONSE_PROFILE_MAX_BYTES
        ):
            raise RuntimeError("mimo_response_profile_unsafe")
        payload = source.read_bytes()
        text = payload.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise RuntimeError("mimo_response_profile_unreadable") from exc
    digest = hashlib.sha256(payload).hexdigest()
    if digest != MIMO_RESPONSE_PROFILE_SHA256:
        raise RuntimeError("mimo_response_profile_contract_invalid")
    required_fragments = {
        "mode: primary",
        f"model: {MIMO_AUTO25_MODEL}",
        "tool_allowlist: []",
        '  "*": deny',
        "tools:",
        *{
            f"  {name}: false"
            for name in ("bash", "read", "write", "edit", "glob", "grep", "webfetch", "actor", "task")
        },
    }
    if not required_fragments.issubset(set(text.splitlines())):
        raise RuntimeError("mimo_response_profile_contract_invalid")
    return payload, digest


def install_mimo_response_agent_profile(worktree: Path) -> tuple[Path, str]:
    payload, digest = load_mimo_response_agent_profile()
    profile_dir = worktree / ".mimocode" / "agents"
    profile_dir.mkdir(parents=True, mode=0o700, exist_ok=False)
    target = profile_dir / f"{MIMO_RESPONSE_AGENT_NAME}.md"
    descriptor = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
    return target, digest


def remove_mimo_response_agent_profile(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return
    for directory in (path.parent, path.parent.parent):
        try:
            directory.rmdir()
        except OSError:
            break


def mimo_auto25_command(executable: str, title: str, prompt: str, worktree: Path) -> tuple[list[str], str]:
    """Build the canonical Mimo Auto 2.5 invocation without logging prompt or paths."""
    command = [
        executable,
        "run",
        "--format",
        "json",
        "--model",
        MIMO_AUTO25_MODEL,
        "--dangerously-skip-permissions",
        "--dir",
        str(worktree),
        "--title",
        title,
        prompt,
    ]
    command_label = (
        f"{executable} run --format json --model {MIMO_AUTO25_MODEL} "
        f"--dangerously-skip-permissions --dir <task-worktree> --title {title} <prompt>"
    )
    return command, command_label


def mimo_auto25_readonly_command(
    executable: str,
    title: str,
    prompt_path: Path,
    worktree: Path,
) -> tuple[list[str], str]:
    """Build the factory chat route without placing customer input in argv."""
    command = [
        executable,
        "run",
        "--pure",
        "Выполни инструкцию из прикреплённого файла. Не изменяй файлы.",
        "--format",
        "json",
        "--model",
        MIMO_AUTO25_MODEL,
        "--agent",
        MIMO_RESPONSE_AGENT_NAME,
        "--dir",
        str(worktree),
        "--title",
        title,
        "--file",
        str(prompt_path),
    ]
    command_label = (
        f"{executable} run --pure <attached-instruction> --format json --model {MIMO_AUTO25_MODEL} "
        f"--agent {MIMO_RESPONSE_AGENT_NAME} --dir <task-worktree> --title {title} --file <prompt-file>"
    )
    return command, command_label


def response_only_tool_event_name(event: dict[str, Any]) -> str | None:
    """Return the first structured tool marker in a Mimo JSONL event."""

    stack: list[Any] = [event]
    direct_keys = {
        "command", "tool", "tool_call", "tool_calls", "tool_name", "toolname",
    }
    event_type_markers = {
        "actor", "bash", "command", "edit", "shell", "task", "tool", "tool-call",
        "tool_call", "tool_use", "web_search", "web_search_preview", "write",
    }
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(key).strip().lower().replace("-", "_")
                if normalized_key in direct_keys and child not in (None, "", [], {}):
                    return normalized_key
                if normalized_key in {"type", "event_type", "kind"} and isinstance(child, str):
                    normalized_type = child.strip().lower().replace("-", "_")
                    if (
                        normalized_type in event_type_markers
                        or "tool_call" in normalized_type
                        or normalized_type.startswith("tool_")
                        or normalized_type.endswith("_tool")
                    ):
                        return normalized_type
                stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)
    return None


_SERIALIZED_TOOL_CALL_MARKUP = re.compile(
    r"(?:"
    r"<\s*(?:tool[_-]?call|function[_-]?call)\b[^>]*/\s*>"
    r"|"
    r"<\s*(?:tool[_-]?call|function[_-]?call)\b[^>]*>.*?"
    r"</\s*(?:tool[_-]?call|function[_-]?call)\s*>"
    r"\s*"
    r")+",
    flags=re.IGNORECASE | re.DOTALL,
)
_SERIALIZED_TOOL_CALL_TYPES = {
    "function_call",
    "tool_call",
    "tool_calls",
    "tool_use",
}


def _normalized_json_object(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).strip().lower().replace("-", "_"): child
        for key, child in value.items()
    }


def _looks_like_serialized_tool_call(value: Any) -> bool:
    fields = _normalized_json_object(value)
    if not fields:
        return False
    call_type = str(fields.get("type") or fields.get("kind") or "").strip()
    call_type = call_type.lower().replace("-", "_")
    if call_type in _SERIALIZED_TOOL_CALL_TYPES:
        return any(
            fields.get(key) not in (None, "", [], {})
            for key in ("arguments", "call_id", "function", "input", "name", "tool")
        )
    function = fields.get("function")
    if isinstance(function, dict):
        function_fields = _normalized_json_object(function)
        if function_fields.get("name") and any(
            key in function_fields for key in ("arguments", "input")
        ):
            return True
    return bool(
        (fields.get("name") or fields.get("tool"))
        and any(key in fields for key in ("arguments", "input"))
    )


def serialized_tool_call_output_name(response_text: str) -> str | None:
    """Classify assistant text that is itself a serialized tool invocation.

    The check intentionally requires the entire response to be a call envelope.
    Explanatory prose that merely discusses tool calls, or embeds an example in
    Markdown, remains valid response content.
    """

    candidate = str(response_text or "").strip()
    if not candidate:
        return None
    if _SERIALIZED_TOOL_CALL_MARKUP.fullmatch(candidate):
        return "tool_call_markup"
    if candidate.startswith("```"):
        return None
    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    fields = _normalized_json_object(payload)
    if fields:
        for wrapper in ("function_call", "tool_call", "tool_calls", "tool_use"):
            calls = fields.get(wrapper)
            if isinstance(calls, dict) and _looks_like_serialized_tool_call(calls):
                return wrapper
            if (
                isinstance(calls, list)
                and calls
                and all(_looks_like_serialized_tool_call(call) for call in calls)
            ):
                return wrapper
        if _looks_like_serialized_tool_call(payload):
            return "tool_call_json"
        choices = fields.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                choice_fields = _normalized_json_object(choice)
                for container in ("delta", "message"):
                    nested = _normalized_json_object(choice_fields.get(container))
                    calls = nested.get("tool_calls")
                    if (
                        isinstance(calls, list)
                        and calls
                        and all(_looks_like_serialized_tool_call(call) for call in calls)
                    ):
                        return "openai_tool_calls"
    elif (
        isinstance(payload, list)
        and payload
        and all(_looks_like_serialized_tool_call(call) for call in payload)
    ):
        return "tool_call_json_list"
    return None


def request(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    timeout: int = 20,
    headers: dict[str, str] | None = None,
) -> Any:
    data = None if body is None else json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=request_headers)
    try:
        if "Authorization" in request_headers:
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *_args, **_kwargs):
                    return None
            opener = urllib.request.build_opener(NoRedirect())
            opened = opener.open(req, timeout=timeout)
        else:
            opened = urllib.request.urlopen(req, timeout=timeout)
        with opened as resp:
            if resp.status == 204:
                return None
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def load_external_provider_credential(path: str | Path | None) -> dict[str, Any]:
    if not path:
        raise RuntimeError("external_provider_actor_credential_file_missing")
    candidate = Path(path).expanduser()
    try:
        info = candidate.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.getuid()
            or not 64 <= info.st_size <= 2048
        ):
            raise RuntimeError("external_provider_actor_credential_file_unsafe")
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("external_provider_actor_credential_file_unreadable") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version", "credential_id", "node_id", "epoch", "token",
    }:
        raise RuntimeError("external_provider_actor_credential_invalid")
    if (
        payload.get("schema_version") != EXTERNAL_PROVIDER_CREDENTIAL_SCHEMA
        or not re.fullmatch(r"[A-Za-z0-9._~-]{1,128}", str(payload.get("credential_id") or ""))
        or not re.fullmatch(r"[A-Za-z0-9._~-]{1,128}", str(payload.get("node_id") or ""))
        or type(payload.get("epoch")) is not int
        or payload["epoch"] < 1
        or not re.fullmatch(r"[A-Za-z0-9._~-]{32,512}", str(payload.get("token") or ""))
    ):
        raise RuntimeError("external_provider_actor_credential_invalid")
    return payload


def external_provider_request_headers(
    credential: dict[str, Any],
    node_id: str,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    payload = b"" if body is None else json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    body_sha256 = hashlib.sha256(payload).hexdigest()
    if credential.get("node_id") != node_id:
        raise RuntimeError("external_provider_actor_credential_node_mismatch")
    token = str(credential["token"])
    credential_id = str(credential["credential_id"])
    epoch = str(credential["epoch"])
    canonical = "\n".join((
        EXTERNAL_PROVIDER_AUTH_HMAC_CONTRACT,
        method.upper(), path, body_sha256, timestamp, nonce, node_id, credential_id, epoch,
    ))
    key = hashlib.sha256(token.encode("utf-8")).digest()
    signature = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Authorization": f"Bearer {token}",
        "X-Kolibri-Actor-Timestamp": timestamp,
        "X-Kolibri-Actor-Nonce": nonce,
        "X-Kolibri-Actor-Signature": signature,
        "X-Kolibri-Actor-Node": node_id,
        "X-Kolibri-Actor-Contract": EXTERNAL_PROVIDER_AUTH_HMAC_CONTRACT,
        "X-Kolibri-Actor-Credential": credential_id,
        "X-Kolibri-Actor-Epoch": epoch,
    }


def machine_stats() -> dict[str, Any]:
    disk = shutil.disk_usage("/")
    ram = {}
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in meminfo.splitlines():
            name, value = line.split(":", 1)
            if name in {"MemTotal", "MemAvailable"}:
                ram[name] = value.strip()
    except OSError:
        pass
    return {
        "cpu": os.cpu_count(),
        "ram": ram,
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validated_image_file(path: Path) -> tuple[str, str, int]:
    """Validate generated bytes, not an extension supplied by a generator."""

    if not path.is_file():
        raise RuntimeError("image generator completed without an image file")
    size_bytes = path.stat().st_size
    if size_bytes <= 0:
        raise RuntimeError("image generator returned an empty image")
    if size_bytes > MAX_FACTORY_IMAGE_BYTES:
        raise RuntimeError("image generator result exceeds the bounded factory transport")
    content = path.read_bytes()
    media_type = ""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(content) < 33 or content[12:16] != b"IHDR" or content[-8:-4] != b"IEND":
            raise RuntimeError("image generator returned an invalid PNG container")
        media_type = "image/png"
    elif content.startswith(b"\xff\xd8"):
        if len(content) < 4 or not content.endswith(b"\xff\xd9"):
            raise RuntimeError("image generator returned an invalid JPEG container")
        media_type = "image/jpeg"
    elif len(content) >= 16 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        if int.from_bytes(content[4:8], "little") + 8 != len(content) or content[12:16] not in {
            b"VP8 ", b"VP8L", b"VP8X",
        }:
            raise RuntimeError("image generator returned an invalid WebP container")
        media_type = "image/webp"
    else:
        raise RuntimeError("image generator returned an unsupported image container")
    return media_type, hashlib.sha256(content).hexdigest(), size_bytes


def image_generator_configured() -> bool:
    """Detect only secret/command presence; never expose either value."""

    return bool(
        os.environ.get("KOLIBRI_IMAGE_GENERATOR_CMD", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )


def _string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        values = []
        for item in value:
            values.extend(_string_values(item))
        return values
    if isinstance(value, dict):
        return [str(key) for key, enabled in value.items() if enabled]
    return [str(value)]


def _normalized_token(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def classify_permission_pack(task: dict[str, Any]) -> dict[str, Any]:
    envelope = task_envelope(task)
    kind = str(task.get("kind") or envelope.get("kind") or "")
    pack_values: list[str] = []
    permission_values: list[str] = []
    evidence: list[dict[str, str]] = []

    for key_name in ("permission_pack", "permissionPack", "permissions_pack", "permission_profile"):
        for value in _string_values(envelope_value(envelope, key_name)):
            pack_values.append(value)
            evidence.append({"field": key_name, "value": value})
    for value in _string_values(envelope_value(envelope, "permission_packs")):
        pack_values.append(value)
        evidence.append({"field": "permission_packs", "value": value})
    for value in _string_values(envelope_value(envelope, "permissions")):
        permission_values.append(value)
        evidence.append({"field": "permissions", "value": value})

    for key_name in ("full_autonomy", "git_push", "write_worktree"):
        if envelope_truthy(envelope, key_name):
            permission_values.append(key_name)
            evidence.append({"field": key_name, "value": str(envelope_value(envelope, key_name))})
    if envelope_truthy(envelope, "read_only"):
        pack_values.append("read_only")
        evidence.append({"field": "read_only", "value": str(envelope_value(envelope, "read_only"))})
    if envelope_truthy(envelope, "no_push"):
        pack_values.append("no_push")
        evidence.append({"field": "no_push", "value": str(envelope_value(envelope, "no_push"))})

    normalized_packs = {_normalized_token(value) for value in pack_values}
    normalized_permissions = {_normalized_token(value) for value in permission_values}
    permission_markers = {_normalized_token(marker) for marker in READ_ONLY_PERMISSION_PACK_MARKERS}
    read_only_no_push = any(marker in token for token in normalized_packs for marker in permission_markers)
    forbidden_permissions = sorted(normalized_permissions & FORBIDDEN_READ_ONLY_PERMISSIONS)

    if kind in WRITE_WORKTREE_TASK_KINDS:
        forbidden_permissions.append("write_worktree")
    if kind in GIT_PUSH_TASK_KINDS:
        forbidden_permissions.append("git_push")
    forbidden_permissions = sorted(set(forbidden_permissions))

    domain = "gomesh" if any("gomesh" in _normalized_token(value) for value in pack_values + permission_values) else "generic"
    decision = "blocked" if read_only_no_push and forbidden_permissions else "allowed"
    return {
        "contract": "agent_host_permission_pack_runtime_gate",
        "domain": domain,
        "kind": kind,
        "read_only_no_push": read_only_no_push,
        "permission_packs": sorted(normalized_packs),
        "requested_permissions": sorted(normalized_permissions),
        "forbidden_permissions": forbidden_permissions if read_only_no_push else [],
        "evidence": evidence,
        "decision": decision,
    }


def task_envelope(task: dict[str, Any]) -> dict[str, Any]:
    envelope = task.get("envelope")
    return envelope if isinstance(envelope, dict) else {}


def envelope_value(envelope: dict[str, Any], key_name: str, default: Any = None) -> Any:
    if key_name in envelope:
        return envelope[key_name]
    constraints = envelope.get("constraints")
    if isinstance(constraints, dict) and key_name in constraints:
        return constraints[key_name]
    return default


def truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def envelope_truthy(envelope: dict[str, Any], *keys: str) -> bool:
    return any(truthy(envelope_value(envelope, key_name, False)) for key_name in keys)


def ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def requested_runner_for_envelope(envelope: dict[str, Any], default: str | None = None) -> str | None:
    runner = envelope_value(envelope, "runner", default)
    if runner is None:
        return None
    normalized = str(runner).strip().lower()
    return normalized or None


def runner_capability(runner: str) -> str:
    return f"runner:{runner}"


def is_declared_runner_capability(capability: str) -> bool:
    normalized = str(capability or "").strip().lower()
    return any(
        normalized in {f"runner:{runner}", f"runner_{runner}", f"{runner}_runner"}
        for runner in SUPPORTED_AI_RUNNERS
    )


def redact_sensitive_text(text: str) -> str:
    redacted_lines: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in SECRET_REDACTION_MARKERS):
            redacted_lines.append("[redacted sensitive runner output]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)


def public_reasoning_summary_from_event(event: Any) -> str | None:
    """Return only an explicit safe reasoning-summary surface from JSONL."""

    if not isinstance(event, dict):
        return None
    event_type = str(event.get("type") or "").strip().lower()
    value: Any = None
    if event_type == "response.reasoning_summary_text.delta":
        value = event.get("delta")
    elif event_type in {
        "item.completed", "item.delta", "reasoning_summary.completed",
        "reasoning_summary.delta",
    }:
        item = event.get("item")
        if not isinstance(item, dict):
            item = event
        if str(item.get("type") or "").strip().lower() not in {
            "reasoning", "reasoning_summary", "summary_text",
        }:
            return None
        value = item.get("delta") or item.get("text") or item.get("summary")
        if isinstance(value, dict):
            value = value.get("text")
    if not isinstance(value, str):
        return None
    text = value.replace("\x00", "").strip()
    encoded = text.encode("utf-8", errors="replace")
    if not text or len(encoded) > MAX_PUBLIC_REASONING_SUMMARY_BYTES:
        return None
    lowered = text.lower()
    if (
        any(marker in lowered for marker in SECRET_REDACTION_MARKERS)
        or PUBLIC_REASONING_PRIVATE_PATTERN.search(text)
        or any(ord(character) < 32 and character not in "\n\r\t" for character in text)
    ):
        return None
    return text


def sanitize_text_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    redacted = redact_sensitive_text(text)
    if redacted != text:
        path.write_text(redacted + ("\n" if text.endswith("\n") else ""), encoding="utf-8")


def envelope_list(envelope: dict[str, Any], *keys: str) -> list[Any]:
    values: list[Any] = []
    for key_name in keys:
        values.extend(ensure_list(envelope_value(envelope, key_name)))
    return values


def envelope_dict(envelope: dict[str, Any], *keys: str) -> dict[str, Any] | None:
    for key_name in keys:
        value = envelope_value(envelope, key_name)
        if isinstance(value, dict):
            return value
    return None


def artifact_spec_path(spec: Any) -> str | None:
    if isinstance(spec, str):
        return spec.strip() or None
    if isinstance(spec, dict):
        for key_name in ("path", "file", "artifact", "output"):
            value = spec.get(key_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def as_posix_path(value: str | Path) -> str:
    return str(value).replace("\\", "/").strip()


def changed_file_display(path: str | Path, worktree: Path | None = None, artifact_dir: Path | None = None) -> str:
    raw = as_posix_path(path)
    candidate = Path(raw)
    for base in (worktree, artifact_dir):
        if base and candidate.is_absolute():
            try:
                return candidate.relative_to(base).as_posix()
            except ValueError:
                pass
    return raw.lstrip("./")


def path_is_under(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base.resolve())
        return True
    except (OSError, ValueError):
        return False


def is_docs_path(changed: str) -> bool:
    normalized = changed.strip("/")
    return normalized == "docs" or normalized.startswith("docs/")


def is_artifact_path(changed: str | Path, artifact_dir: Path | None) -> bool:
    if not artifact_dir:
        return False
    candidate = Path(str(changed))
    return candidate.is_absolute() and path_is_under(candidate, artifact_dir)


def path_matches_scope(changed: str | Path, scope_entry: Any, worktree: Path | None = None, artifact_dir: Path | None = None) -> bool:
    if not isinstance(scope_entry, str) or not scope_entry.strip():
        return False
    changed_display = changed_file_display(changed, worktree, artifact_dir)
    scope = as_posix_path(scope_entry).strip().rstrip("/")
    if not scope:
        return False

    candidate = Path(str(changed))
    scope_path = Path(scope)
    if candidate.is_absolute() and scope_path.is_absolute():
        try:
            return path_is_under(candidate, scope_path) or candidate.resolve() == scope_path.resolve()
        except OSError:
            return False
    if candidate.is_absolute() and artifact_dir and scope_path.is_absolute() and path_is_under(candidate, artifact_dir):
        return path_is_under(candidate, scope_path)

    if fnmatch.fnmatch(changed_display, scope):
        return True
    if scope.endswith("/**"):
        prefix = scope[:-3].rstrip("/")
        return changed_display == prefix or changed_display.startswith(f"{prefix}/")
    if scope.endswith("/*"):
        prefix = scope[:-2].rstrip("/")
        return changed_display.startswith(f"{prefix}/") and "/" not in changed_display[len(prefix) + 1:]
    return changed_display == scope or changed_display.startswith(f"{scope}/")


def changed_file_allowed_by_scope(changed: str | Path, write_scope: list[Any], worktree: Path | None, artifact_dir: Path | None) -> bool:
    return any(path_matches_scope(changed, scope_entry, worktree, artifact_dir) for scope_entry in write_scope)


def collect_git_changed_files(worktree: Path | None) -> list[str]:
    if not worktree or not worktree.exists() or not (worktree / ".git").exists():
        return []
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=str(worktree),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    changed: list[str] = []
    for line in proc.stdout.splitlines():
        if not line:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        if path.startswith('"') and path.endswith('"'):
            path = path[1:-1]
        if path:
            changed.append(path)
    return sorted(set(changed))


def product_code_changed(changed_files: list[str], artifact_dir: Path | None = None) -> bool:
    for changed in changed_files:
        if is_docs_path(changed) or is_artifact_path(changed, artifact_dir):
            continue
        return True
    return False


def required_artifact_candidates(spec_path: str, worktree: Path | None, artifact_dir: Path | None) -> list[Path]:
    path = Path(spec_path)
    if path.is_absolute():
        return [path]
    candidates: list[Path] = []
    if worktree:
        candidates.append(worktree / spec_path)
    if artifact_dir:
        candidates.append(artifact_dir / spec_path)
    return candidates


def canonical_run_artifact_dir(envelope: dict[str, Any]) -> str | None:
    for key_name in CANONICAL_RUN_ARTIFACT_DIR_KEYS:
        value = envelope_value(envelope, key_name)
        if isinstance(value, str) and value.strip():
            return value.strip().rstrip("/")
    return None


def canonical_run_artifact_aliases(envelope: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for value in envelope_list(envelope, *CANONICAL_RUN_ARTIFACT_ALIAS_KEYS):
        if isinstance(value, str) and value.strip():
            aliases.append(value.strip().rstrip("/"))
    return list(dict.fromkeys(aliases))


def resolve_artifact_dir_spec(spec_path: str, worktree: Path | None, artifact_dir: Path | None) -> Path:
    path = Path(spec_path)
    if path.is_absolute():
        return path
    if worktree:
        return worktree / spec_path
    if artifact_dir:
        return artifact_dir / spec_path
    return path


def canonical_run_artifact_paths(run_dir: str) -> list[str]:
    return [f"{run_dir.rstrip('/')}/{filename}" for filename in CANONICAL_RUN_ARTIFACT_FILES]


def complete_run_artifact_dir(base_dir: Path) -> bool:
    return all((base_dir / filename).is_file() for filename in CANONICAL_RUN_ARTIFACT_FILES)


def copy_complete_run_artifact_alias(alias_dir: Path, canonical_dir_path: Path) -> None:
    canonical_dir_path.mkdir(parents=True, exist_ok=True)
    for filename in CANONICAL_RUN_ARTIFACT_FILES:
        target = canonical_dir_path / filename
        if not target.exists():
            shutil.copy2(alias_dir / filename, target)


def finalize_canonical_run_artifacts(
    envelope: dict[str, Any],
    worktree: Path | None,
    artifact_dir: Path | None,
) -> dict[str, Any]:
    run_dir = canonical_run_artifact_dir(envelope)
    if not run_dir:
        return {}

    canonical_dir_path = resolve_artifact_dir_spec(run_dir, worktree, artifact_dir)
    aliases = canonical_run_artifact_aliases(envelope)
    alias_log: list[dict[str, Any]] = []
    alias_used: str | None = None

    if not complete_run_artifact_dir(canonical_dir_path):
        for alias in aliases:
            alias_dir_path = resolve_artifact_dir_spec(alias, worktree, artifact_dir)
            complete = complete_run_artifact_dir(alias_dir_path)
            alias_log.append({
                "alias": alias,
                "canonical": run_dir,
                "complete": complete,
                "action": "copied_to_canonical" if complete and alias_used is None else "inspected",
            })
            if complete and alias_used is None:
                copy_complete_run_artifact_alias(alias_dir_path, canonical_dir_path)
                alias_used = alias
                break

    present: list[str] = []
    missing: list[str] = []
    for artifact_path in canonical_run_artifact_paths(run_dir):
        resolved = resolve_artifact_dir_spec(artifact_path, worktree, artifact_dir)
        if resolved.is_file():
            present.append(artifact_path)
        else:
            missing.append(artifact_path)

    if alias_log and artifact_dir:
        log_path = artifact_dir / "run-artifact-aliases.json"
        log_path.write_text(json.dumps(alias_log, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return {
        "canonical_run_artifact_dir": run_dir,
        "canonical_run_artifacts": canonical_run_artifact_paths(run_dir),
        "canonical_run_artifact_aliases": aliases,
        "canonical_run_artifact_alias_used": alias_used,
        "canonical_run_artifact_alias_log": alias_log,
        "canonical_run_artifacts_present": present,
        "canonical_run_artifacts_missing": missing,
    }


def verify_required_artifacts(envelope: dict[str, Any], worktree: Path | None, artifact_dir: Path | None) -> tuple[list[str], list[str]]:
    present: list[str] = []
    missing: list[str] = []
    for spec in envelope_list(envelope, *REQUIRED_ARTIFACT_KEYS):
        spec_path = artifact_spec_path(spec)
        if not spec_path:
            continue
        if any(candidate.exists() for candidate in required_artifact_candidates(spec_path, worktree, artifact_dir)):
            present.append(spec_path)
        else:
            missing.append(spec_path)
    return present, missing


def backend_test_environment_spec(envelope: dict[str, Any]) -> dict[str, Any] | None:
    spec = envelope_dict(envelope, *BACKEND_TEST_ENV_KEYS)
    if spec is None:
        return None
    if not truthy(spec.get("enabled", True)):
        return None
    env_type = str(spec.get("type") or "backend_python").strip()
    if env_type not in BACKEND_TEST_ENV_TYPES:
        raise BackendTestEnvironmentError(f"backend_test_environment_failed: unsupported backend test env type: {env_type}")
    return spec


def backend_test_environment_path(spec: dict[str, Any], artifact_dir: Path) -> Path:
    configured = spec.get("path") or spec.get("venv_path") or spec.get("env_dir")
    if isinstance(configured, str) and configured.strip():
        path = Path(configured.strip())
        return path if path.is_absolute() else artifact_dir / path
    return artifact_dir / "backend-test-env"


def backend_test_environment_requirement_files(spec: dict[str, Any]) -> list[str]:
    values = []
    values.extend(ensure_list(spec.get("requirements")))
    values.extend(ensure_list(spec.get("requirements_files")))
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def backend_test_environment_packages(spec: dict[str, Any]) -> list[str]:
    return [item.strip() for item in ensure_list(spec.get("packages")) if isinstance(item, str) and item.strip()]


def backend_verifier_command(command: list[str], env_python: Path) -> list[str]:
    if not command:
        return command
    executable = Path(command[0]).name
    if executable in {"python", "python3"}:
        return [str(env_python), *command[1:]]
    if executable == "pytest":
        return [str(env_python), "-m", "pytest", *command[1:]]
    return command


def backend_test_environment_metadata(
    spec: dict[str, Any],
    env_dir: Path,
    status: str,
    error: str | None = None,
    cleaned: bool = False,
) -> dict[str, Any]:
    metadata = {
        "enabled": True,
        "type": str(spec.get("type") or "backend_python"),
        "path": str(env_dir),
        "python": str(spec.get("python") or "python3"),
        "requirements": backend_test_environment_requirement_files(spec),
        "packages": backend_test_environment_packages(spec),
        "cleanup": truthy(spec.get("cleanup", True)),
        "status": status,
        "cleaned": cleaned,
    }
    if error:
        metadata["error"] = error
    return metadata


def push_forbidden_by_envelope(envelope: dict[str, Any]) -> bool:
    return envelope_truthy(envelope, *NO_PUSH_FLAGS)


def push_block_reason(envelope: dict[str, Any]) -> str | None:
    reasons = [flag for flag in NO_PUSH_FLAGS if truthy(envelope_value(envelope, flag, False))]
    return ", ".join(reasons) if reasons else None


def sanitized_permissions_for_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    permissions = envelope_list(envelope, "permissions", "permission_set", "allowed_permissions")
    permission_pack = envelope_value(envelope, "permission_pack")
    if push_forbidden_by_envelope(envelope) and isinstance(permission_pack, str) and permission_pack.strip().lower() in FULL_AUTONOMY_PACKS:
        permission_pack = "read_only" if push_forbidden_by_envelope(envelope) else permission_pack
    if push_forbidden_by_envelope(envelope):
        permissions = [
            item
            for item in permissions
            if not (isinstance(item, str) and item.strip().lower() in PUSH_PERMISSION_NAMES)
        ]
    return {
        "permission_pack": permission_pack,
        "permissions": permissions,
        "git_push_allowed": not push_forbidden_by_envelope(envelope),
    }


def sanitize_task_permissions(task: dict[str, Any]) -> dict[str, Any]:
    envelope = task_envelope(task)
    if not envelope:
        return task
    effective = sanitized_permissions_for_envelope(envelope)
    task["effective_permissions"] = effective
    envelope["effective_permissions"] = effective
    if push_forbidden_by_envelope(envelope):
        for key_name in ("permissions", "permission_set", "allowed_permissions"):
            if key_name in envelope:
                envelope[key_name] = [
                    item
                    for item in ensure_list(envelope.get(key_name))
                    if not (isinstance(item, str) and item.strip().lower() in PUSH_PERMISSION_NAMES)
                ]
        if str(envelope.get("permission_pack", "")).strip().lower() in FULL_AUTONOMY_PACKS:
            envelope["permission_pack"] = "read_only"
    return task


def review_clone_auth_failure_message(stderr_text: str, repo_url: str) -> str | None:
    lowered = stderr_text.lower()
    markers = (
        "permission denied",
        "could not read from remote repository",
        "authentication failed",
        "repository not found",
        "could not resolve hostname",
        "terminal prompts disabled",
    )
    if not any(marker in lowered for marker in markers):
        return None
    return (
        "review_clone_auth_failed: repair Agent Host git credentials or repo access "
        f"for {repo_url}; clone failed before review checkout"
    )


def next_recommended_task_for(blockers: list[str], envelope: dict[str, Any]) -> str:
    configured = envelope_value(envelope, "next_recommended_task")
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    joined = " ".join(blockers)
    if "unsupported_task_kind" in joined or "unsupported_required_capability" in joined:
        return "enable a supported read-only runner for this task kind before resubmitting"
    if "required_artifacts_missing" in joined:
        return "rerun the task with corrected required_artifacts paths or produce the missing outputs"
    if "write_scope_violations" in joined:
        return "resubmit with a precise write_scope or move outputs into the allowed artifact paths"
    if "product_code" in joined:
        return "split product-code changes from read-only or documentation-only task constraints"
    if "push" in joined:
        return "resubmit through a no-push workflow or explicitly allow git push"
    if "review_clone_auth_failed" in joined:
        return "repair Agent Host git credentials, then rerun the review task"
    if "backend_test_environment_failed" in joined:
        return "repair the declared backend test environment requirements or package list, then rerun verification"
    return "inspect the runner contract blockers and resubmit with corrected constraints"


def finalize_runner_contract(
    task: dict[str, Any],
    result: dict[str, Any] | None,
    artifact_dir: Path,
    worktree: Path | None = None,
    changed_files: list[str] | None = None,
    push_attempted: bool | None = None,
    push_blocked: bool | None = None,
    blocked_reason: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    envelope = task_envelope(task)
    final = dict(result or {})
    kind = task.get("kind") or envelope.get("kind")
    original_status = final.get("status")
    if original_status not in CONTRACT_STATUSES:
        if original_status:
            final.setdefault("runner_status", original_status)
        final["status"] = "completed"
    final.setdefault("task_id", task["task_id"])
    final.setdefault("kind", kind)
    if task.get("attempt_id") is not None:
        final["attempt_id"] = task.get("attempt_id")
    if "fencing_token" in task:
        final["fencing_token"] = task.get("fencing_token")
    final["artifact_dir"] = str(artifact_dir)
    requested_runner = requested_runner_for_envelope(envelope)
    result_runner = str(final.get("runner") or "").strip().lower() or None
    final["requested_runner"] = requested_runner
    final["runner"] = result_runner
    final["runner_binding_verified"] = (
        None if requested_runner is None else result_runner == requested_runner
    )

    effective_changed = changed_files
    if effective_changed is None:
        effective_changed = ensure_list(final.get("changed_files")) or collect_git_changed_files(worktree)
    final["changed_files"] = [changed_file_display(path, worktree, artifact_dir) for path in effective_changed if isinstance(path, str)]

    write_scope = envelope_list(envelope, "write_scope")
    final["write_scope"] = write_scope

    required_present, required_missing = verify_required_artifacts(envelope, worktree, artifact_dir)
    canonical_artifacts = finalize_canonical_run_artifacts(envelope, worktree, artifact_dir)
    if canonical_artifacts:
        required_present.extend(canonical_artifacts["canonical_run_artifacts_present"])
        required_missing.extend(canonical_artifacts["canonical_run_artifacts_missing"])
        final.update(canonical_artifacts)
    final["required_artifacts_present"] = required_present
    final["required_artifacts_missing"] = required_missing
    final["effective_permissions"] = sanitized_permissions_for_envelope(envelope)

    read_only = envelope_truthy(envelope, "read_only")
    product_forbidden = envelope_truthy(envelope, *PRODUCT_CODE_FORBIDDEN_FLAGS)
    docs_only = envelope_truthy(envelope, "documentation_artifacts_only")
    final["read_only"] = read_only
    final["product_code_modification_forbidden"] = product_forbidden

    changed_product = product_code_changed(final["changed_files"], artifact_dir)
    final["product_code_changed"] = changed_product

    write_scope_violations: list[str] = []
    if write_scope:
        write_scope_violations = [
            changed
            for changed in final["changed_files"]
            if not changed_file_allowed_by_scope(changed, write_scope, worktree, artifact_dir)
        ]
    if docs_only:
        docs_only_violations = [
            changed
            for changed in final["changed_files"]
            if not is_docs_path(changed)
            and not is_artifact_path(changed, artifact_dir)
            and not changed_file_allowed_by_scope(changed, write_scope, worktree, artifact_dir)
        ]
        write_scope_violations = sorted(set(write_scope_violations + docs_only_violations))
    final["write_scope_violations"] = write_scope_violations

    forbidden_push = push_forbidden_by_envelope(envelope)
    attempted = bool(final.get("push_attempted", False) if push_attempted is None else push_attempted)
    blocked = bool(final.get("push_blocked", False) if push_blocked is None else push_blocked)
    if forbidden_push and not attempted:
        blocked = True
    final["push_attempted"] = attempted
    final["push_blocked"] = blocked
    final["push_block_reason"] = final.get("push_block_reason") or push_block_reason(envelope)

    tests_run = final.get("tests_run")
    if tests_run is None:
        tests_run = final.get("checks", [])
    final["tests_run"] = ensure_list(tests_run)

    blockers: list[str] = []
    if blocked_reason:
        blockers.append(blocked_reason)
    if not artifact_dir.exists():
        blockers.append("artifact_dir_missing")
    if required_missing:
        blockers.append("required_artifacts_missing")
    if write_scope_violations:
        blockers.append("write_scope_violations")
    if read_only and changed_product:
        blockers.append("read_only_product_code_changed")
    if product_forbidden and changed_product:
        blockers.append("product_code_modification_forbidden")
    if forbidden_push and attempted:
        blockers.append("forbidden_push_attempted")
    if requested_runner is not None and result_runner != requested_runner:
        blockers.append("runner_result_mismatch")

    if blockers:
        final["status"] = "blocked"
        final["blocked_reason"] = "; ".join(dict.fromkeys(blockers))
        final["failure_reason"] = failure_reason
    else:
        final.setdefault("blocked_reason", None)
        final["failure_reason"] = failure_reason
    final["next_recommended_task"] = final.get("next_recommended_task") or (
        next_recommended_task_for(blockers, envelope) if blockers else None
    )

    for field in CONTRACT_RESULT_FIELDS:
        final.setdefault(field, None)
    return final


def unsupported_task_result(task: dict[str, Any], artifact_dir: Path, reason: str, worktree: Path | None = None) -> dict[str, Any]:
    return finalize_runner_contract(
        task,
        {
            "task_id": task["task_id"],
            "status": "blocked",
            "kind": task.get("kind") or task_envelope(task).get("kind"),
            "changed_files": [],
        },
        artifact_dir,
        worktree=worktree,
        changed_files=[],
        blocked_reason=reason,
    )


class AgentHost:
    def __init__(self, args: argparse.Namespace):
        self.control_url = resolve_home_control_plane_url(
            getattr(args, "control_url", None),
            getattr(args, "control_urls", None),
            manifest_path=getattr(args, "mesh_membership_manifest", None),
        )
        self.node_id = args.node_id
        self.agent_id = args.agent_id or f"{args.node_id}-agent-host"
        self.configured_capabilities = [
            item
            for item in args.capabilities.split(",")
            if item
            and item not in {RELEASE_CAPABILITY, "image_generation"}
            and not is_declared_runner_capability(item)
        ]
        if LEASE_HEARTBEAT_PROBE_KIND not in self.configured_capabilities:
            self.configured_capabilities.append(LEASE_HEARTBEAT_PROBE_KIND)
        self.capabilities = list(self.configured_capabilities)
        self.repo_url = args.repo_url
        self.work_root = Path(args.work_root)
        self.artifact_root = Path(args.artifact_root)
        if not 1 <= int(args.heartbeat_interval) <= 10:
            raise RuntimeError("agent_host_heartbeat_interval_must_be_between_1_and_10_seconds")
        self.heartbeat_interval = int(args.heartbeat_interval)
        self.lease_refresh = args.lease_refresh
        self.max_inflight = args.max_inflight
        configured_refresh = int(
            getattr(args, "codex_readiness_refresh_seconds", 0) or 0
        )
        self.codex_readiness_refresh_seconds = (
            0 if configured_refresh <= 0 else min(max(configured_refresh, 60), 3_600)
        )
        try:
            labels = json.loads(getattr(args, "labels_json", None) or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError("KOLIBRI_NODE_LABELS_JSON is invalid") from exc
        if not isinstance(labels, dict) or any(
            not isinstance(key, str) or not isinstance(value, (str, int, float, bool))
            for key, value in labels.items()
        ):
            raise RuntimeError("KOLIBRI_NODE_LABELS_JSON must be a flat object")
        self.labels = labels
        self._external_provider_actor = bool(
            labels.get("provider") == "codex"
            and labels.get("runtime") in EXTERNAL_CODEX_PROVIDER_RUNTIMES
            and labels.get("physical_node_id") == self.node_id
            and (
                labels.get("runtime") != "home_systemd_user"
                or labels.get("authority") == "home"
            )
        )
        self._external_provider_credential: dict[str, Any] | None = None
        if self._external_provider_actor:
            credential = load_external_provider_credential(
                getattr(args, "external_provider_credential_file", None)
                or os.environ.get("KOLIBRI_EXTERNAL_PROVIDER_ACTOR_CREDENTIAL_FILE")
            )
            self._external_provider_credential = credential
        self.hostname = platform.node()
        self.pid = os.getpid()
        self.agent_host_runtime = agent_host_runtime_identity()
        self._last_node_heartbeat = 0.0
        self._active_task_id: str | None = None
        self._runtime_restart_requested = False
        self._codex_readiness_probe_active = False
        self._registered = False
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.release_helper: ReleaseHelperClient | None = None
        self.release_installer_status: dict[str, Any] = {
            "status": "unavailable",
            "capability": RELEASE_CAPABILITY,
            "reasons": ["release_installer_not_initialized"],
        }
        self.refresh_release_installer_capability()
        try:
            self.runner_access = load_runner_access_manifest()
            self.runner_access_error = None
        except RunnerAccessError as exc:
            self.runner_access = None
            self.runner_access_error = exc.code
        self.runner_status = self.detect_runner_status()
        self.capabilities = self.capabilities_with_runners()
        self._last_codex_readiness_refresh = time.monotonic()

    def post(self, path: str, body: dict[str, Any]) -> Any:
        headers = (
            external_provider_request_headers(
                self._external_provider_credential, self.node_id, "POST", path, body,
            )
            if self._external_provider_credential else None
        )
        return request("POST", f"{self.control_url}{path}", body, headers=headers)

    def get(self, path: str) -> Any:
        headers = (
            external_provider_request_headers(
                self._external_provider_credential, self.node_id, "GET", path, None,
            )
            if self._external_provider_credential else None
        )
        return request("GET", f"{self.control_url}{path}", headers=headers)

    def detect_runner_status(self) -> dict[str, dict[str, Any]]:
        status: dict[str, dict[str, Any]] = {}
        for runner in sorted(SUPPORTED_AI_RUNNERS):
            try:
                path = shutil.which(runner)
            except RecursionError:
                path = None
            if runner == "codex":
                status[runner] = self.detect_codex_runner_status(path)
            elif runner == "mimo":
                if (
                    self.runner_access is not None
                    and self.runner_access["runners"]["mimo"].get("mode") == "disabled"
                ):
                    status[runner] = {
                        "status": "disabled",
                        "path": path,
                        "checked_at": utc_now(),
                        "error_type": "runner_disabled",
                    }
                elif not path:
                    status[runner] = {
                        "status": "unavailable",
                        "path": None,
                        "checked_at": utc_now(),
                        "error_type": "runner_unavailable",
                    }
                else:
                    try:
                        _profile, profile_sha256 = load_mimo_response_agent_profile()
                        status[runner] = {
                            "status": "available",
                            "path": path,
                            "checked_at": utc_now(),
                            "error_type": None,
                            "response_profile_sha256": profile_sha256,
                        }
                    except RuntimeError:
                        status[runner] = {
                            "status": "unavailable",
                            "path": path,
                            "checked_at": utc_now(),
                            "error_type": "mimo_response_profile_unavailable",
                        }
            else:
                status[runner] = {
                    "status": "available" if path else "unavailable",
                    "path": path,
                    "checked_at": utc_now(),
                }
            if runner == "mimo":
                status[runner].update(mimo_auto25_runner_contract())
            elif runner == "codex":
                status[runner].update(codex_factory_runner_contract())
        return status

    @staticmethod
    def _codex_probe_environment() -> dict[str, str]:
        allowed = (
            "PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "SSL_CERT_FILE",
            "SSL_CERT_DIR",
        )
        environment = {name: os.environ[name] for name in allowed if os.environ.get(name)}
        environment.update(provider_runner_proxy_environment())
        return environment

    def detect_codex_runner_status(self, executable: str | None) -> dict[str, Any]:
        checked_at = utc_now()
        base: dict[str, Any] = {
            "status": "unavailable",
            "path": executable,
            "checked_at": checked_at,
            "readiness_contract": "kolibri.codex-readiness.v1",
            "login_status": "not_checked",
            "probe": {
                "model": CODEX_TASK_MODEL,
                "sandbox": "read-only",
                "status": "not_run",
            },
        }
        if self.runner_access is None:
            return {**base, "error_type": self.runner_access_error or "runner_access_manifest_missing"}
        policy = self.runner_access["runners"]["codex"]
        mode = policy.get("mode")
        base["access_mode"] = mode
        if mode == "disabled":
            return {**base, "error_type": "runner_disabled"}
        if mode == "trusted_broker":
            # A broker declaration is safe to replicate, but is not by itself
            # execution evidence. The future broker adapter must replace this
            # with a bounded live attestation before capability publication.
            return {
                **base,
                "status": "degraded",
                "error_type": "runner_broker_attestation_required",
                "broker_ref": policy["broker_ref"],
                "authorization_ref": policy["authorization_ref"],
            }
        if not executable:
            return {**base, "error_type": "runner_unavailable"}

        try:
            environment = self._codex_probe_environment()
        except RuntimeError:
            return {**base, "error_type": "provider_proxy_contract_invalid"}
        login_timeout = min(10, int(policy["probe"]["timeout_seconds"]))
        try:
            login = subprocess.run(
                [executable, "login", "status"],
                cwd=self.work_root,
                capture_output=True,
                text=True,
                timeout=login_timeout,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {**base, "error_type": "runner_login_status_failed"}
        login_summary = f"{login.stdout}\n{login.stderr}".lower()
        if login.returncode != 0 or "logged in" not in login_summary:
            return {
                **base,
                "status": "blocked",
                "login_status": "unauthenticated",
                "error_type": "runner_auth_blocked",
            }

        base["login_status"] = "authenticated"
        timeout = int(policy["probe"]["timeout_seconds"])
        command = [
            executable,
            "exec",
            "--json",
            "--ephemeral",
            "--skip-git-repo-check",
            "--ignore-user-config",
            "--ignore-rules",
            "--color",
            "never",
            "--sandbox",
            "read-only",
            "-C",
            str(self.work_root),
            "-c",
            'shell_environment_policy.inherit="none"',
            "--model",
            CODEX_TASK_MODEL,
            "-",
        ]
        prompt = f"Reply with exactly {CODEX_READINESS_MARKER} and nothing else."
        started = time.monotonic()
        try:
            probe = subprocess.run(
                command,
                cwd=self.work_root,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=environment,
            )
        except subprocess.TimeoutExpired:
            return {
                **base,
                "error_type": "runner_probe_timeout",
                "probe": {**base["probe"], "status": "failed", "duration_ms": timeout * 1000},
            }
        except OSError:
            return {**base, "error_type": "runner_probe_failed"}
        duration_ms = int((time.monotonic() - started) * 1000)
        combined = f"{probe.stdout}\n{probe.stderr}"
        if probe.returncode != 0:
            error_type, _message, _retry = self.classify_runner_error("codex", "probe_failed", combined)
            state = "blocked" if error_type in {
                "runner_auth_failed", "runner_access_denied", "runner_auth_blocked",
            } else "unavailable"
            return {
                **base,
                "status": state,
                "error_type": error_type,
                "probe": {**base["probe"], "status": "failed", "duration_ms": duration_ms},
            }
        with tempfile.TemporaryDirectory(prefix="codex-readiness-", dir=self.work_root) as temp_dir:
            output_path = Path(temp_dir) / "stdout.jsonl"
            output_path.write_text(probe.stdout, encoding="utf-8")
            response_text = self.parse_json_text_response(output_path).strip()
        if response_text != CODEX_READINESS_MARKER:
            return {
                **base,
                "error_type": "runner_probe_output_mismatch",
                "probe": {**base["probe"], "status": "failed", "duration_ms": duration_ms},
            }
        return {
            **base,
            "status": "available",
            "error_type": None,
            "probe": {
                **base["probe"],
                "status": "passed",
                "duration_ms": duration_ms,
                "output_sha256": hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
            },
        }

    def capabilities_with_runners(self) -> list[str]:
        capabilities = list(dict.fromkeys(self.configured_capabilities))
        if image_generator_configured():
            capabilities.append("image_generation")
        for runner, state in self.runner_status.items():
            if state.get("status") == "available":
                cap = runner_capability(runner)
                if cap not in capabilities:
                    capabilities.append(cap)
        if self.release_installer_status.get("status") == "available":
            capabilities.append(RELEASE_CAPABILITY)
        return capabilities

    def refresh_codex_readiness_if_due(self, *, now: float | None = None) -> bool:
        """Refresh the bounded Codex attestation only while this worker is idle.

        Fleet workers keep this disabled by default.  The managed Mac provider
        opts in explicitly, so its browser-authorized local session is probed
        in place without copying any authentication material to Home or to
        another node.  The Agent Host loop is synchronous, and the explicit
        active/probe guards keep a readiness subprocess from overlapping a
        leased customer task or another readiness subprocess.
        """

        interval = self.codex_readiness_refresh_seconds
        if interval <= 0 or self._active_task_id or self._codex_readiness_probe_active:
            return False
        observed_at = time.monotonic() if now is None else float(now)
        if observed_at - self._last_codex_readiness_refresh < interval:
            return False

        # Fence retries before starting the subprocess.  An unexpected local
        # probe failure must not create a tight loop or leak its exception text.
        self._last_codex_readiness_refresh = observed_at
        self._codex_readiness_probe_active = True
        try:
            try:
                executable = shutil.which("codex")
                refreshed = self.detect_codex_runner_status(executable)
            except Exception:
                refreshed = {
                    "status": "unavailable",
                    "path": None,
                    "checked_at": utc_now(),
                    "readiness_contract": "kolibri.codex-readiness.v1",
                    "login_status": "not_checked",
                    "error_type": "runner_readiness_refresh_failed",
                    "probe": {
                        "model": CODEX_TASK_MODEL,
                        "sandbox": "read-only",
                        "status": "failed",
                    },
                }
            refreshed.update(codex_factory_runner_contract())
            self.runner_status["codex"] = refreshed
            # This is the authoritative capability withdrawal path: any
            # blocked/unavailable refresh removes runner:codex immediately.
            self.capabilities = self.capabilities_with_runners()
            return True
        finally:
            self._codex_readiness_probe_active = False

    def codex_readiness_evidence(self) -> dict[str, Any]:
        """Return the redacted, schema-bounded readiness record for Home."""

        state = self.runner_status.get("codex", {})
        probe_state = state.get("probe") if isinstance(state.get("probe"), dict) else {}
        probe: dict[str, Any] = {
            "model": CODEX_TASK_MODEL,
            "sandbox": "read-only",
            "status": str(probe_state.get("status") or "not_run"),
        }
        if isinstance(probe_state.get("duration_ms"), int):
            probe["duration_ms"] = probe_state["duration_ms"]
        output_sha256 = str(probe_state.get("output_sha256") or "")
        if re.fullmatch(r"[a-f0-9]{64}", output_sha256):
            probe["output_sha256"] = output_sha256
        evidence: dict[str, Any] = {
            "schema_version": "kolibri.codex-readiness.v1",
            "node_id": self.node_id,
            "checked_at": str(state.get("checked_at") or utc_now()),
            "access_mode": str(state.get("access_mode") or "unconfigured"),
            "status": str(state.get("status") or "unavailable"),
            "login_status": str(state.get("login_status") or "not_checked"),
            "error_type": state.get("error_type"),
            "probe": probe,
        }
        broker_ref = state.get("broker_ref")
        if broker_ref in {"runner-broker://home/codex", "runner-broker://mac/codex"}:
            evidence["broker_ref"] = broker_ref
        return evidence

    def refresh_release_installer_capability(self) -> None:
        try:
            if self.release_helper is None:
                self.release_helper = ReleaseHelperClient.from_environment()
            self.release_installer_status = self.release_helper.prerequisite_status()
        except ReleaseInstallError as exc:
            self.release_helper = None
            self.release_installer_status = {
                "status": "unavailable",
                "capability": RELEASE_CAPABILITY,
                "reasons": [exc.code],
            }
        if hasattr(self, "runner_status"):
            self.capabilities = self.capabilities_with_runners()

    def mark_runner_status(self, runner: str, status: str, error_type: str | None = None) -> None:
        current = self.runner_status.setdefault(runner, {})
        current.update({
            "status": status,
            "error_type": error_type,
            "updated_at": utc_now(),
        })

    def persist_runner_failure(self, exc: RunnerExecutionError) -> None:
        """Keep a failed runner out of scheduling until an explicit repair/probe.

        The Control Plane also records the failure, but Agent Host heartbeats
        are authoritative for live capability state.  Persisting it locally
        prevents the next heartbeat from accidentally undoing quarantine.
        """
        blocked_errors = {
            "runner_auth_blocked",
            "runner_auth_failed",
            "runner_access_denied",
            "runner_policy_blocked",
            "provider_risk_control",
        }
        status = (
            "blocked"
            if exc.error_type in blocked_errors
            else "unavailable"
            if exc.error_type in {
                "runner_unavailable",
                "provider_runner_outdated",
                "mimo_response_profile_unavailable",
            }
            else None
        )
        if status is None:
            return
        self.mark_runner_status(exc.runner, status, exc.error_type)
        self.capabilities = self.capabilities_with_runners()

    def validated_mimo_worktree(self, worktree: Path) -> Path:
        candidate = worktree.resolve()
        if not candidate.is_dir() or not path_is_under(candidate, self.work_root):
            raise RunnerExecutionError(
                "runner_worktree_boundary_violation",
                "mimo",
                "mimo runner worktree is outside the Agent Host task root",
                retry=False,
            )
        return candidate

    def mimo_auto25_invocation(self, executable: str, title: str, prompt: str, worktree: Path) -> tuple[list[str], str]:
        return mimo_auto25_command(executable, title, prompt, self.validated_mimo_worktree(worktree))

    def register(self) -> None:
        self.refresh_release_installer_capability()
        self.capabilities = self.capabilities_with_runners()
        body = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "capabilities": self.capabilities,
            "runners": self.runner_status,
            "runner_readiness": {"codex": self.codex_readiness_evidence()},
            "release_installer": self.release_installer_status,
            "agent_host_runtime": self.agent_host_runtime,
            "labels": self.labels,
            **machine_stats(),
        }
        self.post("/v1/nodes/register", body)
        self._registered = True

    def node_heartbeat(self, active_task: str | None = None) -> None:
        self.refresh_release_installer_capability()
        self.capabilities = self.capabilities_with_runners()
        body = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "capabilities": self.capabilities,
            "runners": self.runner_status,
            "runner_readiness": {"codex": self.codex_readiness_evidence()},
            "release_installer": self.release_installer_status,
            "agent_host_runtime": self.agent_host_runtime,
            "labels": self.labels,
            "active_task": active_task,
            **machine_stats(),
        }
        self.post(f"/v1/nodes/{self.node_id}/heartbeat", body)
        self._last_node_heartbeat = time.time()

    def task_heartbeat(
        self,
        task: dict[str, Any],
        worktree: Path,
        branch: str | None,
        logs: dict[str, str],
        pid: int | None = None,
        progress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Long tasks still refresh their node card. Otherwise a healthy busy
        # worker is classified as stale and removed from routing.
        if time.time() - self._last_node_heartbeat >= self.heartbeat_interval:
            self.node_heartbeat(active_task=task["task_id"])
        body = {
            "state": "running",
            "attempt_id": task.get("attempt_id"),
            "fencing_token": task.get("fencing_token"),
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "pid": pid or self.pid,
            "worktree": str(worktree),
            "branch": branch,
            "log_paths": logs,
        }
        if progress is not None:
            body["progress"] = progress
        return self.post(f"/v1/tasks/{task['task_id']}/heartbeat", body)

    def lease(self) -> dict[str, Any] | None:
        self.refresh_release_installer_capability()
        self.capabilities = self.capabilities_with_runners()
        task = self.post("/v1/tasks/lease", {
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
            "runners": self.runner_status,
            "runner_readiness": {"codex": self.codex_readiness_evidence()},
            "release_installer": self.release_installer_status,
        })
        return sanitize_task_permissions(task) if isinstance(task, dict) else task

    def run_command(
        self,
        command: list[str],
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
        env: dict[str, str] | None = None,
        command_label: str | None = None,
        stdin_path: Path | None = None,
    ) -> None:
        envelope = task_envelope(task)
        constraints = (
            envelope.get("constraints")
            if isinstance(envelope.get("constraints"), dict)
            else {}
        )
        raw_max_wall = constraints.get("max_wall_seconds")
        deadline: float | None = None
        if raw_max_wall is not None:
            if (
                isinstance(raw_max_wall, bool)
                or not isinstance(raw_max_wall, (int, float))
                or not 0 < float(raw_max_wall) <= 86_400
            ):
                raise TaskProcessInterrupted(
                    "task_contract_invalid",
                    "constraints.max_wall_seconds must be between 0 and 86400",
                    retry=False,
                )
            started = task.setdefault("_agent_host_started_monotonic", time.monotonic())
            deadline = float(started) + float(raw_max_wall)
            if time.monotonic() >= deadline:
                raise TaskProcessInterrupted(
                    "provider_timeout",
                    "execution exceeded constraints.max_wall_seconds before process start",
                    retry=False,
                )
        if STOP:
            raise TaskProcessInterrupted(
                "task_cancelled",
                "agent host received SIGTERM before process start",
                retry=False,
            )
        try:
            authoritative = self.task_heartbeat(task, cwd, branch, logs)
        except Exception as exc:
            raise TaskProcessInterrupted(
                "task_lease_fenced",
                "Control Plane heartbeat or lease fence was lost before process start",
                retry=False,
            ) from exc
        if self.task_cancel_requested(authoritative):
            raise TaskProcessInterrupted(
                "task_cancelled",
                "Control Plane returned a terminal cancellation fence before process start",
                retry=False,
            )
        merged_env = agent_child_environment(env)
        display_command = command_label or " ".join(command)
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            stdout.write(f"\n$ {display_command}\n".encode("utf-8"))
            stdout.flush()
            reasoning_offset = stdout.tell()
            reasoning_remainder = b""
            reasoning_sequence = 0

            def reasoning_progress() -> dict[str, Any] | None:
                """Tail explicit JSONL reasoning summaries for public progress.

                The raw runner log remains an operator artifact.  Only event
                shapes accepted by ``public_reasoning_summary_from_event``
                cross the Control Plane boundary, so hidden analysis and
                arbitrary stdout can never become customer-visible progress.
                """

                nonlocal reasoning_offset, reasoning_remainder, reasoning_sequence
                if not is_response_only_provider_task(task):
                    return None
                try:
                    current_size = stdout_path.stat().st_size
                    if current_size <= reasoning_offset:
                        return None
                    with stdout_path.open("rb") as progress_stream:
                        progress_stream.seek(reasoning_offset)
                        chunk = progress_stream.read(min(current_size - reasoning_offset, 256 * 1024))
                    reasoning_offset += len(chunk)
                except OSError:
                    return None
                payload = reasoning_remainder + chunk
                lines = payload.splitlines(keepends=True)
                reasoning_remainder = b""
                if lines and not lines[-1].endswith((b"\n", b"\r")):
                    reasoning_remainder = lines.pop()
                    if len(reasoning_remainder) > 64 * 1024:
                        reasoning_remainder = b""
                latest: str | None = None
                for raw_line in lines:
                    try:
                        event = json.loads(raw_line.decode("utf-8", errors="strict"))
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    summary = public_reasoning_summary_from_event(event)
                    if summary is not None:
                        reasoning_sequence += 1
                        latest = summary
                if latest is None:
                    return None
                return {
                    "schema_version": "kolibri.public-progress.v1",
                    "type": "reasoning_summary_delta",
                    "sequence": reasoning_sequence,
                    "delta": latest,
                }
            stdin_stream = stdin_path.open("rb") if stdin_path is not None else None
            try:
                proc = subprocess.Popen(
                    command,
                    cwd=str(cwd),
                    stdin=stdin_stream,
                    stdout=stdout,
                    stderr=stderr,
                    env=merged_env,
                    start_new_session=True,
                )
            finally:
                if stdin_stream is not None:
                    stdin_stream.close()
            last_refresh = time.monotonic()
            refresh_interval = min(max(float(self.lease_refresh), 0.25), 2.0)
            while proc.poll() is None:
                if STOP:
                    self.terminate_process_group(proc)
                    raise TaskProcessInterrupted(
                        "task_cancelled", "agent host received SIGTERM", retry=False
                    )
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    self.terminate_process_group(proc)
                    raise TaskProcessInterrupted(
                        "provider_timeout",
                        "execution exceeded constraints.max_wall_seconds",
                        retry=False,
                    )
                if now - last_refresh >= refresh_interval:
                    try:
                        progress = reasoning_progress()
                        if progress is None:
                            authoritative = self.task_heartbeat(
                                task, cwd, branch, logs, proc.pid
                            )
                        else:
                            authoritative = self.task_heartbeat(
                                task,
                                cwd,
                                branch,
                                logs,
                                proc.pid,
                                progress=progress,
                            )
                    except Exception as exc:
                        self.terminate_process_group(proc)
                        raise TaskProcessInterrupted(
                            "task_lease_fenced",
                            "Control Plane heartbeat or lease fence was lost",
                            retry=False,
                        ) from exc
                    if self.task_cancel_requested(authoritative):
                        self.terminate_process_group(proc)
                        raise TaskProcessInterrupted(
                            "task_cancelled",
                            "Control Plane returned a terminal cancellation fence",
                            retry=False,
                        )
                    last_refresh = now
                sleep_for = (
                    0.25
                    if deadline is None
                    else max(0.01, min(0.25, deadline - now))
                )
                time.sleep(sleep_for)
            final_progress = reasoning_progress()
            if final_progress is not None:
                try:
                    authoritative = self.task_heartbeat(
                        task,
                        cwd,
                        branch,
                        logs,
                        proc.pid,
                        progress=final_progress,
                    )
                except Exception as exc:
                    raise TaskProcessInterrupted(
                        "task_lease_fenced",
                        "Control Plane heartbeat or lease fence was lost after process exit",
                        retry=False,
                    ) from exc
                if self.task_cancel_requested(authoritative):
                    raise TaskProcessInterrupted(
                        "task_cancelled",
                        "Control Plane returned a terminal cancellation fence after process exit",
                        retry=False,
                    )
            if self.process_group_exists(proc.pid):
                self.terminate_process_group(proc, grace_seconds=0.0)
                raise TaskProcessInterrupted(
                    "task_process_leak",
                    "command exited while descendants remained in its process group",
                    retry=False,
                )
            if proc.returncode != 0:
                raise RuntimeError(f"command failed with rc={proc.returncode}: {display_command}")

    @staticmethod
    def task_cancel_requested(authoritative: Any) -> bool:
        if not isinstance(authoritative, dict):
            return True
        nested = authoritative.get("task")
        if isinstance(nested, dict):
            authoritative = nested
        state = str(authoritative.get("state") or "").strip().lower()
        return bool(
            state not in {"leased", "running"}
            or authoritative.get("cancel_requested_at")
            or authoritative.get("cancel_fence_id")
        )

    @staticmethod
    def process_group_exists(process_group_id: int) -> bool:
        try:
            os.killpg(process_group_id, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    @staticmethod
    def terminate_process_group(
        proc: subprocess.Popen[Any],
        grace_seconds: float = 2.0,
    ) -> bool:
        process_group_id = proc.pid
        if not AgentHost.process_group_exists(process_group_id):
            proc.poll()
            return False
        try:
            os.killpg(process_group_id, signal.SIGTERM)
        except ProcessLookupError:
            proc.poll()
            return False
        deadline = time.monotonic() + max(0.0, grace_seconds)
        while (
            AgentHost.process_group_exists(process_group_id)
            and time.monotonic() < deadline
        ):
            proc.poll()
            time.sleep(0.05)
        if AgentHost.process_group_exists(process_group_id):
            try:
                os.killpg(process_group_id, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            proc.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            pass
        return True

    def git_push(
        self,
        task: dict[str, Any],
        command: list[str],
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        branch: str | None,
        logs: dict[str, str],
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        envelope = task_envelope(task)
        reason = push_block_reason(envelope)
        if reason:
            with stdout_path.open("ab") as stdout:
                stdout.write(f"\n$ git push skipped by runner contract: {reason}\n".encode("utf-8"))
            return {
                "push_attempted": False,
                "push_blocked": True,
                "push_block_reason": reason,
            }
        self.run_command(command, cwd, stdout_path, stderr_path, task, branch, logs, env)
        return {
            "push_attempted": True,
            "push_blocked": False,
            "push_block_reason": None,
        }

    def git_push_after_contract_verification(
        self,
        task: dict[str, Any],
        command: list[str],
        cwd: Path,
        stdout_path: Path,
        stderr_path: Path,
        branch: str | None,
        logs: dict[str, str],
        result: dict[str, Any],
        artifact_dir: Path,
        changed_files: list[str],
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        preflight = self.finalize_result(task, result, artifact_dir, cwd, changed_files=changed_files)
        if preflight["status"] != "completed":
            preflight["push_attempted"] = False
            preflight["push_blocked"] = True
            preflight["push_block_reason"] = preflight.get("blocked_reason") or "contract_verification_failed"
            with stdout_path.open("ab") as stdout:
                stdout.write(
                    f"\n$ git push skipped by runner contract preflight: {preflight['push_block_reason']}\n".encode("utf-8")
                )
            return preflight
        push_info = self.git_push(task, command, cwd, stdout_path, stderr_path, branch, logs, env)
        return self.finalize_result(
            task,
            {**preflight, **push_info},
            artifact_dir,
            cwd,
            changed_files=changed_files,
        )

    def unsupported_task_reason(self, task: dict[str, Any]) -> str | None:
        envelope = task_envelope(task)
        kind = task.get("kind") or envelope.get("kind")
        if kind not in SUPPORTED_TASK_KINDS:
            return f"unsupported_task_kind:{kind}"
        required_capability = envelope_value(envelope, "required_capability")
        if required_capability and required_capability not in self.capabilities:
            return f"unsupported_required_capability:{required_capability}"
        return None

    @staticmethod
    def _content_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            text = content.get("text")
            return text if isinstance(text, str) else ""
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str) and item.get("type") in {None, "text", "output_text"}:
                        parts.append(text)
            return "".join(parts)
        return ""

    @staticmethod
    def _safe_json_value(value: Any) -> Any:
        if isinstance(value, dict):
            safe = {}
            for key, item in value.items():
                key_text = str(key).lower()
                if any(hint in key_text for hint in SECRET_FIELD_HINTS):
                    safe[key] = "[redacted]"
                else:
                    safe[key] = AgentHost._safe_json_value(item)
            return safe
        if isinstance(value, list):
            return [AgentHost._safe_json_value(item) for item in value]
        return value

    @classmethod
    def _extract_json_event_text(cls, event: dict[str, Any]) -> tuple[list[str], list[str], list[str]]:
        final_messages: list[str] = []
        text_parts: list[str] = []
        deltas: list[str] = []

        part = event.get("part") or {}
        if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
            text_parts.append(part["text"])

        msg = event.get("msg") or {}
        if isinstance(msg, dict):
            msg_type = str(msg.get("type") or "")
            text = msg.get("message") or msg.get("text") or cls._content_text(msg.get("content"))
            if text:
                if "delta" in msg_type:
                    deltas.append(text)
                else:
                    final_messages.append(text)

        event_type = str(event.get("type") or "")
        text = event.get("message") or event.get("text") or cls._content_text(event.get("content"))
        if text:
            if "delta" in event_type:
                deltas.append(text)
            elif event_type in {"agent_message", "assistant_message", "message"}:
                final_messages.append(text)

        item = event.get("item") or {}
        if isinstance(item, dict) and item.get("type") in {"message", "assistant_message", "agent_message"}:
            item_text = item.get("message") or item.get("text") or cls._content_text(item.get("content"))
            if item_text:
                final_messages.append(item_text)

        return final_messages, text_parts, deltas

    @staticmethod
    def _native_web_search_event(event: dict[str, Any]) -> dict[str, Any] | None:
        """Return a hash-only fact for one real Codex ``web_search`` event.

        Codex JSONL currently exposes the search query and lifecycle event, but
        not the fetched result body or source URLs.  The Agent Host therefore
        records only a query digest and lifecycle status.  Assistant text is
        never interpreted as tool evidence.
        """

        container_type = str(event.get("type") or "").strip().lower()
        if container_type not in {
            "item.started", "item.completed", "item.failed",
            "web_search.started", "web_search.completed", "web_search.failed",
        }:
            return None
        item = event.get("item")
        if not isinstance(item, dict):
            return None
        item_type = str(item.get("type") or "").strip().lower()
        if item_type not in {"web_search", "web_search_preview"}:
            return None
        call_id = str(item.get("id") or item.get("call_id") or "").strip()
        query = item.get("query")
        action = item.get("action")
        if not isinstance(query, str) and isinstance(action, dict):
            query = action.get("query")
        query_sha256: str | None = None
        if isinstance(query, str):
            encoded_query = query.encode("utf-8", errors="replace")
            if len(encoded_query) > MAX_NATIVE_WEB_SEARCH_QUERY_BYTES:
                raise NativeWebSearchEvidenceError(
                    "native_web_search_query_too_large"
                )
            if query.strip():
                query_sha256 = hashlib.sha256(encoded_query).hexdigest()
        explicit_status = str(item.get("status") or "").strip().lower()
        failed = (
            container_type.endswith(".failed")
            or explicit_status in {"failed", "error", "cancelled", "canceled"}
            or bool(item.get("error"))
        )
        completed = (
            not failed
            and (
                container_type.endswith(".completed")
                or explicit_status in {"completed", "succeeded", "success"}
            )
        )
        return {
            # Call IDs are used only to bind a completed event to the query
            # seen in its matching started event; they are never serialized.
            "call_id": call_id,
            "query_sha256": query_sha256,
            "status": "failed" if failed else "completed" if completed else "started",
        }

    @staticmethod
    def _native_web_search_evidence(
        events: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not events:
            return None
        if len(events) > MAX_NATIVE_WEB_SEARCH_EVENTS:
            raise NativeWebSearchEvidenceError(
                "native_web_search_event_limit_exceeded"
            )
        call_queries: dict[str, str] = {}
        query_hashes: set[str] = set()
        for event in events:
            query_sha256 = event.get("query_sha256")
            call_id = str(event.get("call_id") or "")
            if isinstance(query_sha256, str):
                query_hashes.add(query_sha256)
                if call_id:
                    call_queries[call_id] = query_sha256
        if len(query_hashes) > MAX_NATIVE_WEB_SEARCH_QUERIES:
            raise NativeWebSearchEvidenceError(
                "native_web_search_query_limit_exceeded"
            )
        completed_hashes: set[str] = set()
        completed_events = 0
        for event in events:
            if event.get("status") != "completed":
                continue
            query_sha256 = event.get("query_sha256")
            if not isinstance(query_sha256, str):
                query_sha256 = call_queries.get(str(event.get("call_id") or ""))
            if isinstance(query_sha256, str):
                completed_events += 1
                completed_hashes.add(query_sha256)
        # A started event or a model assertion is not execution proof.  Fail
        # closed by omitting evidence unless a completed event is query-bound.
        if not completed_hashes:
            return None
        facts = {
            "schema_version": NATIVE_WEB_SEARCH_EVIDENCE_SCHEMA,
            "tool": "web_search",
            "event_count": len(events),
            "completed_event_count": completed_events,
            "query_count": len(query_hashes),
            "query_sha256": sorted(query_hashes),
        }
        evidence_sha256 = hashlib.sha256(json.dumps(
            facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        return {**facts, "evidence_sha256": evidence_sha256}

    @classmethod
    def _sanitize_native_web_search_log(cls, stdout_path: Path) -> None:
        """Replace native-search JSONL rows with hash-only audit records."""

        if not stdout_path.exists() or not stdout_path.is_file():
            return
        sanitized: list[str] = []
        for raw_line in stdout_path.read_text(
            encoding="utf-8", errors="replace",
        ).splitlines():
            line = raw_line.strip()
            if not line.startswith("{"):
                sanitized.append(redact_sensitive_text(raw_line))
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                sanitized.append(redact_sensitive_text(raw_line))
                continue
            if not isinstance(event, dict):
                sanitized.append(redact_sensitive_text(raw_line))
                continue
            try:
                fact = cls._native_web_search_event(event)
            except NativeWebSearchEvidenceError:
                fact = {
                    "status": "rejected",
                    "query_sha256": hashlib.sha256(
                        line.encode("utf-8", errors="replace")
                    ).hexdigest(),
                }
            if fact is None:
                sanitized.append(redact_sensitive_text(raw_line))
                continue
            safe_event = {
                "type": "kolibri.native_web_search_event",
                "status": fact.get("status"),
                **(
                    {"query_sha256": fact["query_sha256"]}
                    if isinstance(fact.get("query_sha256"), str)
                    else {}
                ),
            }
            sanitized.append(json.dumps(
                safe_event, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ))
        stdout_path.write_text(
            "\n".join(sanitized) + ("\n" if sanitized else ""),
            encoding="utf-8",
        )

    @staticmethod
    def _bind_native_web_search_evidence(
        evidence: dict[str, Any],
        *,
        response_text: str,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        """Bind hash-only tool evidence to the fenced task result."""

        response_sha256 = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
        binding = {
            "schema_version": NATIVE_WEB_SEARCH_EVIDENCE_SCHEMA,
            "task_id": str(task.get("task_id") or ""),
            "attempt_id": str(task.get("attempt_id") or ""),
            "fencing_token": task.get("fencing_token"),
            "response_sha256": response_sha256,
            "evidence_sha256": str(evidence.get("evidence_sha256") or ""),
        }
        binding_sha256 = hashlib.sha256(json.dumps(
            binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        return {
            **evidence,
            "response_sha256": response_sha256,
            "binding_sha256": binding_sha256,
        }

    @classmethod
    def parse_json_response_payload(
        cls,
        stdout_path: Path,
        *,
        forbid_tool_events: bool = False,
        forbid_serialized_tool_calls: bool = False,
    ) -> dict[str, Any]:
        final_messages: list[str] = []
        text_parts: list[str] = []
        deltas: list[str] = []
        useful_objects: list[dict[str, Any]] = []
        runner_errors: list[dict[str, Any]] = []
        native_web_search_events: list[dict[str, Any]] = []
        for line in stdout_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if forbid_tool_events:
                tool_event = response_only_tool_event_name(event)
                if tool_event:
                    raise ResponseOnlyToolEventError(
                        f"mimo_response_only_tool_event:{tool_event}"
                    )
            native_web_search_event = cls._native_web_search_event(event)
            if native_web_search_event is not None:
                native_web_search_events.append(native_web_search_event)

            error = event.get("error")
            if str(event.get("type") or "").lower() == "error" and isinstance(error, dict):
                data = error.get("data") if isinstance(error.get("data"), dict) else {}
                runner_errors.append({
                    "name": str(error.get("name") or "runner_error"),
                    "message": redact_sensitive_text(str(data.get("message") or error.get("message") or "runner error")),
                    "status_code": data.get("statusCode") or data.get("status_code"),
                    "provider_code": data.get("code") if isinstance(data.get("code"), (str, int)) else None,
                    "retryable": data.get("isRetryable") if "isRetryable" in data else data.get("retryable"),
                })

            event_final, event_parts, event_deltas = cls._extract_json_event_text(event)
            final_messages.extend(event_final)
            text_parts.extend(event_parts)
            deltas.extend(event_deltas)
            if SAFE_MIMO_RESULT_FIELDS.intersection(event):
                useful_objects.append(cls._safe_json_value(event))

        native_web_search_evidence = cls._native_web_search_evidence(
            native_web_search_events,
        )

        for parts in (final_messages, text_parts, deltas):
            response_text = "".join(parts).strip()
            if response_text:
                if forbid_serialized_tool_calls:
                    serialized_tool_call = serialized_tool_call_output_name(
                        response_text
                    )
                    if serialized_tool_call:
                        raise ResponseOnlyToolOutputError(
                            f"response_only_serialized_tool_call:{serialized_tool_call}"
                        )
                payload: dict[str, Any] = {"response": response_text}
                if useful_objects:
                    payload["runner_output"] = useful_objects[-1]
                if native_web_search_evidence is not None:
                    payload["native_web_search_evidence"] = native_web_search_evidence
                return payload
        if useful_objects:
            output = useful_objects[-1]
            text = output.get("response") or output.get("message") or output.get("text") or output.get("summary")
            if not isinstance(text, str) or not text.strip():
                text = json.dumps(output, ensure_ascii=False, sort_keys=True)
            if forbid_serialized_tool_calls:
                serialized_tool_call = serialized_tool_call_output_name(text)
                if serialized_tool_call:
                    raise ResponseOnlyToolOutputError(
                        f"response_only_serialized_tool_call:{serialized_tool_call}"
                    )
            return {
                "response": text.strip(),
                "runner_output": output,
                **(
                    {"native_web_search_evidence": native_web_search_evidence}
                    if native_web_search_evidence is not None else {}
                ),
            }
        return {
            "response": "",
            **({"runner_error": runner_errors[-1]} if runner_errors else {}),
            **(
                {"native_web_search_evidence": native_web_search_evidence}
                if native_web_search_evidence is not None else {}
            ),
        }

    @classmethod
    def parse_json_text_response(
        cls,
        stdout_path: Path,
        *,
        forbid_tool_events: bool = False,
        forbid_serialized_tool_calls: bool = False,
    ) -> str:
        return str(
            cls.parse_json_response_payload(
                stdout_path,
                forbid_tool_events=forbid_tool_events,
                forbid_serialized_tool_calls=forbid_serialized_tool_calls,
            ).get("response")
            or ""
        )

    @staticmethod
    def _read_runner_output_for_error(stdout_path: Path, stderr_path: Path) -> str:
        chunks = []
        for path in (stdout_path, stderr_path):
            if path.exists():
                chunks.append(path.read_text(encoding="utf-8", errors="replace")[-4000:])
        return "\n".join(chunks)

    @staticmethod
    def classify_runner_error(runner: str, error: str, runner_output: str) -> tuple[str, str, bool]:
        runner = str(runner or "unknown").strip().lower()
        combined = f"{error}\n{runner_output}".lower()
        if "provider_timeout:" in combined:
            return "provider_timeout", f"{runner} exceeded the task wall-clock deadline", False
        if "task_cancelled:" in combined:
            return "task_cancelled", f"{runner} execution was cancelled by Control Plane", False
        if "task_lease_fenced:" in combined:
            return "task_lease_fenced", f"{runner} lost its authoritative task lease", False
        if "task_process_leak:" in combined:
            return "task_process_leak", f"{runner} left a fenced descendant process", False
        if (
            "requires a newer version" in combined
            or "newer version of codex" in combined
            or "upgrade codex" in combined
            or "update codex" in combined
            or "codex cli is out of date" in combined
        ):
            return (
                "provider_runner_outdated",
                f"{runner} runner must be upgraded before this model can execute",
                False,
            )
        if "illegal_access" in combined:
            return "runner_policy_blocked", f"{runner} runner request was blocked by policy: illegal_access", False
        if (
            "risk control" in combined
            or "risk_control" in combined
            or '"provider_code": 441' in combined
            or '"provider_code": "441"' in combined
        ):
            return "provider_risk_control", f"{runner} runner request was blocked by provider risk control", False
        if "http 401" in combined or " 401" in combined or "unauthorized" in combined:
            return "runner_auth_failed", f"{runner} runner authentication failed with HTTP 401", False
        if "http 403" in combined or " 403" in combined or "forbidden" in combined or "illegal_access" in combined:
            if "illegal_access" in combined:
                return "runner_policy_blocked", f"{runner} runner request was blocked by policy: illegal_access", False
            return "runner_access_denied", f"{runner} runner access denied with HTTP 403", False
        return "runtime_error", error, True

    def run_json_payload_command(
        self,
        command: list[str],
        command_label: str,
        runner: str,
        worktree: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
        stdin_path: Path | None = None,
        forbid_tool_events: bool = False,
        forbid_serialized_tool_calls: bool = False,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            command_options: dict[str, Any] = {"command_label": command_label}
            if stdin_path is not None:
                command_options["stdin_path"] = stdin_path
            if env is not None:
                command_options["env"] = env
            self.run_command(
                command, worktree, stdout_path, stderr_path, task, branch, logs,
                **command_options,
            )
        except TaskProcessInterrupted:
            # The authoritative deadline/cancel/lease fence takes precedence
            # over any stale provider error text already present in the logs.
            raise
        except Exception as exc:
            error_type, message, retry = self.classify_runner_error(
                runner,
                str(exc),
                self._read_runner_output_for_error(stdout_path, stderr_path),
            )
            # Provider stderr can contain credentials or echoed request data
            # even when the exit is an otherwise unclassified runtime error.
            # Classification has already consumed the bounded tail, so retain
            # only sanitized logs for every failure class.
            sanitize_text_file(stdout_path)
            sanitize_text_file(stderr_path)
            if error_type != "runtime_error":
                raise RunnerExecutionError(error_type, runner, message, retry=retry) from exc
            raise
        try:
            payload = self.parse_json_response_payload(
                stdout_path,
                forbid_tool_events=forbid_tool_events,
                forbid_serialized_tool_calls=forbid_serialized_tool_calls,
            )
        except ResponseOnlyToolEventError as exc:
            # Tool payloads can contain command arguments, file contents, or
            # provider internals.  Preserve only the policy verdict; never
            # persist or return the raw forbidden event.
            stdout_path.write_text(
                "[kolibri] Mimo response-only policy violation; raw output withheld\n",
                encoding="utf-8",
            )
            stderr_path.write_text(
                "[kolibri] Mimo response-only policy violation\n",
                encoding="utf-8",
            )
            raise RunnerExecutionError(
                "runner_policy_blocked",
                runner,
                f"{runner} response-only agent emitted a forbidden tool event",
                retry=False,
            ) from exc
        except ResponseOnlyToolOutputError as exc:
            # Serialized calls can contain provider arguments and user data.
            # Retain only the classified policy failure, never the raw output.
            stdout_path.write_text(
                "[kolibri] Response-only tool-call output withheld\n",
                encoding="utf-8",
            )
            stderr_path.write_text(
                "[kolibri] Response-only tool-call output rejected\n",
                encoding="utf-8",
            )
            raise RunnerExecutionError(
                "response_only_tool_call_output",
                runner,
                f"{runner} response-only runner emitted a serialized tool call instead of a final response",
                retry=False,
            ) from exc
        except NativeWebSearchEvidenceError as exc:
            # The JSONL may contain the raw query.  Sanitize it before the
            # failed attempt can be retained as an artifact.
            self._sanitize_native_web_search_log(stdout_path)
            raise RunnerExecutionError(
                "runner_policy_blocked",
                runner,
                str(exc),
                retry=False,
            ) from exc
        if payload.get("native_web_search_evidence") is not None:
            self._sanitize_native_web_search_log(stdout_path)
        if not payload.get("response"):
            structured_error = payload.get("runner_error")
            if isinstance(structured_error, dict):
                classification_input = json.dumps(structured_error, ensure_ascii=False, sort_keys=True)
                error_type, message, retry = self.classify_runner_error(
                    runner,
                    str(structured_error.get("message") or runner),
                    classification_input,
                )
                raise RunnerExecutionError(
                    error_type,
                    runner,
                    message,
                    retry=retry,
                )
            raise RuntimeError(f"{runner} completed without text response")
        return payload

    def run_json_text_command(
        self,
        command: list[str],
        command_label: str,
        runner: str,
        worktree: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
        stdin_path: Path | None = None,
        forbid_tool_events: bool = False,
        forbid_serialized_tool_calls: bool = False,
        env: dict[str, str] | None = None,
    ) -> str:
        payload = self.run_json_payload_command(
            command,
            command_label,
            runner,
            worktree,
            stdout_path,
            stderr_path,
            task,
            branch,
            logs,
            stdin_path=stdin_path,
            forbid_tool_events=forbid_tool_events,
            forbid_serialized_tool_calls=forbid_serialized_tool_calls,
            env=env,
        )
        return str(payload.get("response") or "")

    def run_requested_ai_runner(
        self,
        runner: str,
        prompt: str,
        title: str,
        worktree: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
        execution_metadata: dict[str, Any] | None = None,
    ) -> str:
        runner = runner.strip().lower()
        if runner not in SUPPORTED_AI_RUNNERS:
            raise RunnerExecutionError("runner_unavailable", runner, f"unsupported runner requested: {runner}")
        if runner == "api":
            return self.run_api_text_runner(prompt)
        if runner == "local_llm":
            return self.run_local_llm_text_runner(prompt)
        readiness = self.runner_status.get(runner, {})
        if runner in {"codex", "mimo"} and readiness.get("status") != "available":
            error_type = str(readiness.get("error_type") or "runner_readiness_failed")
            raise RunnerExecutionError(
                error_type,
                runner,
                f"{runner} readiness gate is not available on this node",
                retry=False,
            )
        executable = shutil.which(runner)
        if not executable:
            self.mark_runner_status(runner, "unavailable", "runner_unavailable")
            raise RunnerExecutionError("runner_unavailable", runner, f"{runner} executable is not available on this node")

        prompt_path: Path | None = None
        mimo_profile_path: Path | None = None
        forbid_tool_events = False
        response_only_route = is_response_only_provider_task(task)
        try:
            try:
                provider_environment = provider_runner_proxy_environment()
            except RuntimeError as exc:
                raise RunnerExecutionError(
                    "provider_proxy_contract_invalid",
                    runner,
                    "provider proxy contract is invalid",
                    retry=False,
                ) from exc
            if runner == "codex":
                prompt_path = worktree / ".kolibri-provider-prompt"
                codex_prompt = (
                    f"{CODEX_PROVIDER_NETWORK_INSTRUCTION}\n\n{prompt}"
                    if response_only_route else prompt
                )
                prompt_path.write_text(codex_prompt, encoding="utf-8")
                prompt_path.chmod(0o600)
                if response_only_route:
                    command = [
                        executable, "--search", "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                        "--ignore-user-config", "--ignore-rules", "--color", "never",
                        "--sandbox", "read-only", "--model", CODEX_TASK_MODEL, "-",
                    ]
                    command_label = (
                        f"{executable} --search exec --json --ephemeral --skip-git-repo-check "
                        f"--ignore-user-config --ignore-rules --color never --sandbox read-only "
                        f"--model {CODEX_TASK_MODEL} - <prompt-file>"
                    )
                else:
                    command = [
                        executable, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
                        "--color", "never", "--sandbox", "danger-full-access",
                        "--model", CODEX_TASK_MODEL, "-",
                    ]
                    command_label = (
                        f"{executable} exec --json --ephemeral --skip-git-repo-check --color never "
                        f"--sandbox danger-full-access --model {CODEX_TASK_MODEL} - <prompt-file>"
                    )
            else:
                if response_only_route:
                    prompt_path = worktree / ".kolibri-provider-prompt"
                    prompt_path.write_text(prompt, encoding="utf-8")
                    prompt_path.chmod(0o600)
                    try:
                        mimo_profile_path, profile_sha256 = (
                            install_mimo_response_agent_profile(worktree)
                        )
                    except (OSError, RuntimeError) as exc:
                        raise RunnerExecutionError(
                            "mimo_response_profile_unavailable",
                            "mimo",
                            "Mimo response-only profile could not be installed safely",
                            retry=False,
                        ) from exc
                    expected_profile_sha256 = str(readiness.get("response_profile_sha256") or "")
                    if not expected_profile_sha256 or profile_sha256 != expected_profile_sha256:
                        raise RunnerExecutionError(
                            "mimo_response_profile_unavailable",
                            "mimo",
                            "Mimo response-only profile changed after readiness",
                            retry=False,
                        )
                    command, command_label = mimo_auto25_readonly_command(
                        executable,
                        title,
                        prompt_path,
                        worktree,
                    )
                    forbid_tool_events = True
                else:
                    command, command_label = self.mimo_auto25_invocation(
                        executable, title, prompt, worktree
                    )
            payload = self.run_json_payload_command(
                command,
                command_label,
                runner,
                worktree,
                stdout_path,
                stderr_path,
                task,
                branch,
                logs,
                stdin_path=prompt_path if runner == "codex" else None,
                forbid_tool_events=forbid_tool_events,
                forbid_serialized_tool_calls=response_only_route,
                env=provider_environment,
            )
            if execution_metadata is not None:
                native_evidence = payload.get("native_web_search_evidence")
                if isinstance(native_evidence, dict):
                    execution_metadata["native_web_search_evidence"] = dict(
                        native_evidence
                    )
            return str(payload.get("response") or "")
        except TaskProcessInterrupted:
            raise
        except RunnerExecutionError as exc:
            # Keep the local heartbeat authoritative after a provider/auth
            # failure.  Without this update the Control Plane quarantine was
            # immediately overwritten by the next heartbeat, because the
            # runner was still advertised as "available" merely because its
            # executable existed on disk.
            self.persist_runner_failure(exc)
            raise
        except RuntimeError as exc:
            error_type, message, retry = self.classify_runner_error(
                runner,
                str(exc),
                self._read_runner_output_for_error(stdout_path, stderr_path),
            )
            sanitize_text_file(stdout_path)
            sanitize_text_file(stderr_path)
            if error_type != "runtime_error":
                classified = RunnerExecutionError(error_type, runner, message, retry=retry)
                self.persist_runner_failure(classified)
                raise classified from exc
            raise
        finally:
            if prompt_path is not None:
                try:
                    prompt_path.unlink()
                except FileNotFoundError:
                    pass
            remove_mimo_response_agent_profile(mimo_profile_path)

    def prepare_backend_test_environment(
        self,
        task: dict[str, Any],
        worktree: Path,
        artifact_dir: Path,
        stdout_path: Path,
        stderr_path: Path,
        branch: str | None,
        logs: dict[str, str],
    ) -> tuple[Path, dict[str, Any]] | None:
        spec = backend_test_environment_spec(task_envelope(task))
        if spec is None:
            return None

        env_dir = backend_test_environment_path(spec, artifact_dir)
        if worktree.exists() and path_is_under(env_dir, worktree):
            message = "backend_test_environment_failed: backend test env path must be outside the worktree"
            raise BackendTestEnvironmentError(message)

        python_bin = str(spec.get("python") or "python3")
        requirements = backend_test_environment_requirement_files(spec)
        packages = backend_test_environment_packages(spec)
        metadata = backend_test_environment_metadata(spec, env_dir, "preparing")

        try:
            if env_dir.exists():
                shutil.rmtree(env_dir)
            self.run_command([python_bin, "-m", "venv", str(env_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
            env_python = env_dir / "bin" / "python"
            self.run_command([str(env_python), "-m", "pip", "install", "--upgrade", "pip"], worktree, stdout_path, stderr_path, task, branch, logs)
            if requirements:
                self.run_command([str(env_python), "-m", "pip", "install", *[item for req in requirements for item in ("-r", req)]], worktree, stdout_path, stderr_path, task, branch, logs)
            if packages:
                self.run_command([str(env_python), "-m", "pip", "install", *packages], worktree, stdout_path, stderr_path, task, branch, logs)
        except Exception as exc:
            metadata = backend_test_environment_metadata(spec, env_dir, "failed", error=str(exc))
            if env_dir.exists() and truthy(spec.get("cleanup", True)):
                shutil.rmtree(env_dir, ignore_errors=True)
                metadata["cleaned"] = True
            raise BackendTestEnvironmentError(f"backend_test_environment_failed: {exc}") from exc

        metadata["status"] = "ready"
        return env_dir / "bin" / "python", metadata

    def cleanup_backend_test_environment(self, metadata: dict[str, Any] | None) -> dict[str, Any] | None:
        if not metadata or not truthy(metadata.get("cleanup", True)):
            return metadata
        env_path = metadata.get("path")
        if isinstance(env_path, str) and env_path:
            shutil.rmtree(env_path, ignore_errors=True)
            metadata["cleaned"] = True
        return metadata

    def run_backend_verification_commands(
        self,
        commands: list[list[str]],
        worktree: Path,
        artifact_dir: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        prepared = self.prepare_backend_test_environment(task, worktree, artifact_dir, stdout_path, stderr_path, branch, logs)
        metadata: dict[str, Any] | None = prepared[1] if prepared else None
        env_python = prepared[0] if prepared else None
        executed: list[str] = []
        try:
            for command in commands:
                effective_command = backend_verifier_command(command, env_python) if env_python else command
                executed.append(" ".join(effective_command))
                self.run_command(effective_command, worktree, stdout_path, stderr_path, task, branch, logs, env)
            if metadata:
                metadata["status"] = "passed"
                metadata["commands"] = executed
            return metadata or {"enabled": False, "status": "not_configured", "commands": executed}
        finally:
            if metadata:
                self.cleanup_backend_test_environment(metadata)

    def write_result(self, artifact_dir: Path, result: dict[str, Any]) -> Path:
        result_path = artifact_dir / "result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = []
        for path in sorted(artifact_dir.rglob("*")):
            if path.is_file():
                manifest.append({"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size})
        (artifact_dir / "artifact-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return result_path

    def finalize_result(
        self,
        task: dict[str, Any],
        result: dict[str, Any],
        artifact_dir: Path,
        worktree: Path | None = None,
        changed_files: list[str] | None = None,
    ) -> dict[str, Any]:
        return finalize_runner_contract(task, result, artifact_dir, worktree=worktree, changed_files=changed_files)

    def complete(self, task: dict[str, Any], result: dict[str, Any], result_path: Path) -> None:
        bound_result = dict(result)
        if "fencing_token" in task:
            bound_result["fencing_token"] = task.get("fencing_token")
        self.post(f"/v1/tasks/{task['task_id']}/complete", {
            "attempt_id": task.get("attempt_id"),
            "fencing_token": task.get("fencing_token"),
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "result_reference": str(result_path),
            "result": bound_result,
        })

    def fail(self, task: dict[str, Any], error_type: str, error: str, result: dict[str, Any] | None, result_path: Path | None, retry: bool = True) -> None:
        bound_result = dict(result) if isinstance(result, dict) else result
        requested_runner = requested_runner_for_envelope(task_envelope(task))
        if requested_runner:
            if not isinstance(bound_result, dict):
                bound_result = {}
            # A failed attempt still has to identify the runner it attempted.
            # Fill only an absent binding: an explicit mismatched runner must
            # remain visible and be rejected by the strict Control Plane.
            if not str(bound_result.get("runner") or "").strip():
                bound_result["runner"] = requested_runner
            if not str(bound_result.get("requested_runner") or "").strip():
                bound_result["requested_runner"] = requested_runner
            bound_result["runner_binding_verified"] = (
                str(bound_result.get("runner") or "").strip().lower()
                == requested_runner
            )
        if isinstance(bound_result, dict) and "fencing_token" in task:
            bound_result["fencing_token"] = task.get("fencing_token")
        self.post(f"/v1/tasks/{task['task_id']}/fail", {
            "attempt_id": task.get("attempt_id"),
            "fencing_token": task.get("fencing_token"),
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "error_type": error_type,
            "error": error,
            "result": bound_result,
            "result_reference": str(result_path) if result_path else None,
            "retry": retry,
        })

    def validate_runtime_permission_contract(self, task: dict[str, Any]) -> dict[str, Any]:
        classification = classify_permission_pack(task)
        if classification["decision"] == "blocked":
            raise PermissionContractError(classification)
        return classification

    def prepare_dirs(self, task: dict[str, Any]) -> tuple[Path, Path, dict[str, str]]:
        task_id = task["task_id"]
        attempt_id = task.get("attempt_id") or f"{task_id}-attempt-{task.get('attempt', 1)}"
        worktree = self.work_root / task_id / attempt_id / "repo"
        artifact_dir = self.artifact_root / task_id / attempt_id
        if worktree.exists():
            shutil.rmtree(worktree)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        logs = {
            "stdout": str(artifact_dir / "stdout.log"),
            "stderr": str(artifact_dir / "stderr.log"),
        }
        return worktree, artifact_dir, logs

    def run_read_only_probe(self, task: dict[str, Any]) -> dict[str, Any]:
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        self.task_heartbeat(task, worktree, None, logs)
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": "read_only_probe",
            "message": "read-only probe completed",
            "agent_host_runtime": self.agent_host_runtime,
            "permission_pack_classification": classify_permission_pack(task),
        }
        result = self.finalize_result(task, result, artifact_dir, worktree, changed_files=[])
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_lease_heartbeat_probe(self, task: dict[str, Any]) -> dict[str, Any]:
        """Prove that one fenced attempt remains live beyond a legacy lease window.

        The probe is deliberately read-only and bounded.  It refreshes the
        authoritative task lease at least every five seconds, observes
        cancellation/fencing returned by Home, and emits a content-bound
        result only after more than sixty seconds of the same attempt.
        """

        envelope = task_envelope(task)
        requested = envelope_value(
            envelope,
            "proof_duration_seconds",
            LEASE_HEARTBEAT_PROBE_MIN_SECONDS,
        )
        if (
            isinstance(requested, bool)
            or not isinstance(requested, int)
            or not LEASE_HEARTBEAT_PROBE_MIN_SECONDS
            <= requested
            <= LEASE_HEARTBEAT_PROBE_MAX_SECONDS
        ):
            raise RuntimeError("lease_heartbeat_probe_duration_invalid")

        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        started_at = utc_now()
        started = time.monotonic()
        heartbeat_count = 0
        last_state = "running"
        while True:
            elapsed = max(0.0, time.monotonic() - started)
            heartbeat = self.task_heartbeat(
                task,
                worktree,
                None,
                logs,
            )
            heartbeat_count += 1
            last_state = str(heartbeat.get("state") or "running")
            if last_state in {"cancelled", "failed", "dead_letter"}:
                raise TaskProcessInterrupted(
                    "task_cancelled",
                    "Home fenced the lease heartbeat probe",
                    retry=False,
                )
            elapsed = max(0.0, time.monotonic() - started)
            if elapsed >= requested:
                break
            time.sleep(min(5.0, float(requested) - elapsed))

        observed = max(0.0, time.monotonic() - started)
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": LEASE_HEARTBEAT_PROBE_KIND,
            "message": "fenced lease heartbeat probe completed",
            "agent_host_runtime": self.agent_host_runtime,
            "lease_heartbeat_probe": {
                "schema_version": LEASE_HEARTBEAT_PROBE_SCHEMA,
                "started_at": started_at,
                "completed_at": utc_now(),
                "requested_duration_seconds": requested,
                "observed_duration_seconds": round(observed, 3),
                "heartbeat_count": heartbeat_count,
                "last_authoritative_state": last_state,
            },
            "permission_pack_classification": classify_permission_pack(task),
        }
        result = self.finalize_result(
            task,
            result,
            artifact_dir,
            worktree,
            changed_files=[],
        )
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_release_bundle_task(self, task: dict[str, Any]) -> dict[str, Any]:
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        self.task_heartbeat(task, worktree, None, logs)
        kind = str(task.get("kind") or "")
        try:
            if self.release_helper is None:
                raise ReleaseInstallError(
                    "release_installer_prerequisites_unavailable",
                    evidence={"prerequisite_status": self.release_installer_status},
                )
            def release_progress() -> None:
                heartbeat = self.task_heartbeat(task, worktree, None, logs)
                if heartbeat.get("state") in {"cancelled", "failed", "dead_letter"}:
                    raise ReleaseInstallError("release_task_cancelled")

            release_envelope = {
                **task_envelope(task),
                "task_id": str(task.get("task_id") or ""),
                "attempt_id": str(task.get("attempt_id") or ""),
            }
            release_result = self.release_helper.execute(
                kind,
                release_envelope,
                artifact_dir,
                progress_callback=release_progress,
            )
            if not isinstance(release_result, dict):
                raise ReleaseInstallError("release_result_invalid")
            envelope = release_envelope
            expected_release_id = str(
                envelope.get("release_id")
                if kind == "release_bundle_apply"
                else envelope.get("rollback_to_release_id")
            )
            health = release_result.get("release_health")
            if (
                release_result.get("status") != "completed"
                or not isinstance(health, dict)
                or health.get("status") != "healthy"
                or health.get("release_id") != expected_release_id
                or health.get("manifest_digest") != envelope.get("manifest_digest")
            ):
                raise ReleaseInstallError("release_health_evidence_invalid")
        except ReleaseInstallError as exc:
            release_result = {
                **exc.evidence,
                "status": "failed",
                "kind": kind,
                "error_type": exc.code,
                "failure_reason": exc.code,
                "retryable": exc.retryable,
            }
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "changed_files": [],
            **release_result,
        }
        preserved_failure_reason = result.get("failure_reason")
        result = self.finalize_result(task, result, artifact_dir, worktree, changed_files=[])
        if preserved_failure_reason:
            result["failure_reason"] = preserved_failure_reason
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_telegram_chat_response(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        message = (envelope.get("message") or "").strip()
        if not message:
            raise RuntimeError("telegram chat task missing message")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, None, logs)
        prompt = (
            "Ты — центральный оркестратор Kolibri. Владелец общается с тобой, а не с отдельным сервером или worker. "
            "Отвечай от первого лица как оркестратор: я вижу систему, я выбираю исполнителей, я контролирую PR, CI, review и deployment. "
            "Используй снимок фабрики ниже как текущий контекст. В нем есть memory: проектная память, недавний диалог, последняя рабочая задача, ожидания владельца и известные ссылки. "
            "Если владелец пишет продолжение без объекта, например 'ссылку не забудь', восстанови смысл из memory.last_work_request и memory.recent_messages. "
            "Не проси уточнить, если связь очевидна; подтверди, что помнишь предыдущую задачу и пришлешь ссылку, когда результат будет готов. "
            "Если данных не хватает, честно скажи, что проверишь. "
            "Стиль: коротко, спокойно, премиально, по-русски, без эмодзи, markdown и служебных идентификаторов. "
            "Не раскрывай task_id, node, agent, worktree, пути, логи или артефакты, если владелец прямо не просит технические доказательства. "
            "Не называй себя брендом Kolibri и не используй фразу 'я Kolibri'. Ты директор-оркестратор проекта, а не название продукта. "
            "Если владелец здоровается, обработай приветствие естественно: каждый ответ должен быть заново сгенерирован по текущему сообщению и снимку фабрики, без заранее заданной фразы. "
            "Если это обычный разговор, отвечай естественно. Если это просьба о разработке, скажи, что ты принял задачу и сам назначишь исполнителя. "
            f"Снимок фабрики JSON: {json.dumps(envelope.get('factory_snapshot') or {}, ensure_ascii=False, sort_keys=True)}\n"
            f"Сообщение владельца: {message}"
        )
        runner = (
            os.environ.get("KOLIBRI_TELEGRAM_RUNNER")
            or os.environ.get("KOLIBRI_AI_RUNNER")
            or requested_runner_for_envelope(envelope, "mimo")
            or "mimo"
        ).strip().lower()
        execution_metadata: dict[str, Any] = {}
        response_text = self.run_requested_ai_runner(
            runner,
            prompt,
            f"telegram-chat-{task['task_id']}",
            worktree,
            stdout_path,
            stderr_path,
            task,
            None,
            logs,
            execution_metadata=execution_metadata,
        )
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": envelope.get("kind", "orchestrator_chat_response"),
            "runner": runner,
            "response": response_text,
        }
        native_web_search_evidence = execution_metadata.get(
            "native_web_search_evidence"
        )
        if (
            runner == "codex"
            and is_response_only_provider_task(task)
            and isinstance(native_web_search_evidence, dict)
        ):
            result["native_web_search_evidence"] = self._bind_native_web_search_evidence(
                native_web_search_evidence,
                response_text=response_text,
                task=task,
            )
        if runner == "mimo":
            result["runner_contract"] = (
                mimo_auto25_runner_contract()
                if is_response_only_provider_task(task)
                else mimo_auto25_direct_runner_contract()
            )
        elif runner == "codex":
            result["runner_contract"] = (
                codex_factory_runner_contract()
                if is_response_only_provider_task(task)
                else codex_direct_runner_contract()
            )
        result = self.finalize_result(task, result, artifact_dir, worktree, changed_files=[])
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_owner_remote_task(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        prompt = (envelope.get("objective") or envelope.get("message") or "").strip()
        if not prompt:
            raise RuntimeError("owner_remote_task missing objective")
        runner = requested_runner_for_envelope(envelope, "mimo") or "mimo"
        if runner not in SUPPORTED_AI_RUNNERS:
            raise RunnerExecutionError("runner_unavailable", runner, f"unsupported runner requested: {runner}")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, envelope.get("branch"), logs)
        execution_metadata: dict[str, Any] = {}
        response_text = self.run_requested_ai_runner(
            runner,
            prompt,
            f"owner-task-{task['task_id']}",
            worktree,
            stdout_path,
            stderr_path,
            task,
            envelope.get("branch"),
            logs,
            execution_metadata=execution_metadata,
        )
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": envelope.get("branch"),
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": "owner_remote_task",
            "runner": runner,
            "response": response_text,
        }
        native_web_search_evidence = execution_metadata.get(
            "native_web_search_evidence"
        )
        if (
            runner == "codex"
            and is_response_only_provider_task(task)
            and isinstance(native_web_search_evidence, dict)
        ):
            result["native_web_search_evidence"] = self._bind_native_web_search_evidence(
                native_web_search_evidence,
                response_text=response_text,
                task=task,
            )
        if runner == "mimo":
            result["runner_contract"] = (
                mimo_auto25_runner_contract()
                if is_response_only_provider_task(task)
                else mimo_auto25_direct_runner_contract()
            )
        elif runner == "codex":
            result["runner_contract"] = (
                codex_factory_runner_contract()
                if is_response_only_provider_task(task)
                else codex_direct_runner_contract()
            )
        result = self.finalize_result(task, result, artifact_dir, worktree, changed_files=[])
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_direct_mimo_task(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task_envelope(task)
        prompt = (envelope.get("objective") or envelope.get("prompt") or envelope.get("message") or "").strip()
        if not prompt:
            raise RuntimeError("direct mimo task missing objective")
        branch = envelope.get("branch")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)
        runner_artifact = {
            "kind": "direct_mimo_run",
            "task_id": task["task_id"],
            "attempt_id": task.get("attempt_id"),
            "runner": "mimo",
            "started_at": utc_now(),
            **mimo_auto25_direct_runner_contract(),
        }
        (artifact_dir / "runner-contract.json").write_text(
            json.dumps(runner_artifact, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        mimo = shutil.which("mimo")
        if not mimo:
            raise RunnerExecutionError("runner_unavailable", "mimo", "mimo executable is not available on this node")
        command, command_label = self.mimo_auto25_invocation(
            mimo,
            f"owner-task-{task['task_id']}",
            prompt,
            worktree,
        )
        payload = self.run_json_payload_command(
            command,
            command_label,
            "mimo",
            worktree,
            stdout_path,
            stderr_path,
            task,
            branch,
            logs,
        )
        runner_output = payload.get("runner_output") if isinstance(payload.get("runner_output"), dict) else {}
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": runner_output.get("branch") or branch,
            "base_ref": envelope.get("base_ref") or envelope.get("base_branch"),
            "pull_request_url": runner_output.get("pull_request_url") or runner_output.get("pr_url"),
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": task.get("kind") or envelope.get("kind") or "owner_remote_task",
            "runner": "mimo",
            "runner_contract": mimo_auto25_direct_runner_contract(),
            "response": payload["response"],
            "tests": runner_output.get("tests"),
            "blockers": runner_output.get("blockers"),
            "next_action": runner_output.get("next_action"),
            "changed_files": runner_output.get("changed_files"),
        }
        if runner_output:
            result["runner_output"] = runner_output
        result = self.finalize_result(task, result, artifact_dir, worktree)
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_api_text_runner(self, prompt: str) -> str:
        endpoint = os.environ.get("KOLIBRI_API_RUNNER_URL", "https://api.openai.com/v1/chat/completions")
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("KOLIBRI_API_RUNNER_TOKEN")
        if not api_key:
            raise RuntimeError("api runner auth is not configured: set OPENAI_API_KEY or KOLIBRI_API_RUNNER_TOKEN")
        body = {
            "model": os.environ.get("KOLIBRI_API_RUNNER_MODEL", "gpt-4.1-mini"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": float(os.environ.get("KOLIBRI_API_RUNNER_TEMPERATURE", "0.2")),
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=int(os.environ.get("KOLIBRI_API_RUNNER_TIMEOUT", "120"))) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        choices = payload.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            text = message.get("content")
            if text:
                return str(text)
        text = payload.get("response") or payload.get("text")
        if text:
            return str(text)
        raise RuntimeError("api runner returned no text")

    def run_local_llm_text_runner(self, prompt: str) -> str:
        endpoint = os.environ.get("KOLIBRI_LOCAL_LLM_URL")
        if not endpoint:
            raise RuntimeError("local_llm runner is not configured: set KOLIBRI_LOCAL_LLM_URL")
        body = {
            "prompt": prompt,
            "model": os.environ.get("KOLIBRI_LOCAL_LLM_MODEL", "local"),
            "stream": False,
        }
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=int(os.environ.get("KOLIBRI_LOCAL_LLM_TIMEOUT", "120"))) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        text = payload.get("response") or payload.get("text") or payload.get("content")
        if text:
            return str(text)
        raise RuntimeError("local_llm runner returned no text")

    def generated_image_path(self, artifact_dir: Path, preferred: Path) -> Path:
        if preferred.exists() and preferred.is_file():
            return preferred
        candidates = [path for path in sorted(artifact_dir.rglob("*")) if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
        if not candidates:
            raise RuntimeError("image generator completed without an image file")
        return candidates[0]

    def image_output_path(self, artifact_dir: Path) -> Path:
        output_format = os.environ.get("KOLIBRI_IMAGE_OUTPUT_FORMAT", "png").strip().lower().lstrip(".")
        if output_format == "jpeg":
            suffix = "jpg"
        elif output_format not in {"png", "jpg", "webp"}:
            suffix = "png"
        else:
            suffix = output_format
        return artifact_dir / f"telegram-image.{suffix}"

    def image_b64_for_result(self, image_path: Path) -> str | None:
        max_bytes = min(
            MAX_FACTORY_IMAGE_BYTES,
            int(os.environ.get("KOLIBRI_IMAGE_RESULT_EMBED_MAX_BYTES", str(MAX_FACTORY_IMAGE_BYTES))),
        )
        if image_path.stat().st_size > max_bytes:
            return None
        return base64.b64encode(image_path.read_bytes()).decode("ascii")

    def run_configured_image_generator(
        self,
        prompt: str,
        output_path: Path,
        worktree: Path,
        artifact_dir: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        logs: dict[str, str],
    ) -> Path:
        command = os.environ.get("KOLIBRI_IMAGE_GENERATOR_CMD")
        if not command:
            return self.run_openai_image_generation(prompt, output_path)
        env = {
            "KOLIBRI_IMAGE_PROMPT": prompt,
            "KOLIBRI_IMAGE_OUTPUT_DIR": str(artifact_dir),
            "KOLIBRI_IMAGE_OUTPUT_PATH": str(output_path),
            "KOLIBRI_IMAGE_SIZE": os.environ.get("KOLIBRI_IMAGE_SIZE", "1024x1024"),
            "KOLIBRI_TASK_ID": task["task_id"],
        }
        self.run_command(["/bin/sh", "-lc", command], worktree, stdout_path, stderr_path, task, None, logs, env)
        return self.generated_image_path(artifact_dir, output_path)

    def run_openai_image_generation(self, prompt: str, output_path: Path) -> Path:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("image generator is not configured: set KOLIBRI_IMAGE_GENERATOR_CMD or OPENAI_API_KEY")
        endpoint = os.environ.get("KOLIBRI_IMAGE_API_URL", "https://api.openai.com/v1/images/generations")
        body: dict[str, Any] = {
            "model": os.environ.get("KOLIBRI_IMAGE_MODEL", "gpt-image-1"),
            "prompt": prompt,
            "size": os.environ.get("KOLIBRI_IMAGE_SIZE", "1024x1024"),
            "n": 1,
        }
        for env_name, field_name in (
            ("KOLIBRI_IMAGE_QUALITY", "quality"),
            ("KOLIBRI_IMAGE_BACKGROUND", "background"),
            ("KOLIBRI_IMAGE_OUTPUT_FORMAT", "output_format"),
        ):
            value = os.environ.get(env_name)
            if value:
                body[field_name] = value
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=int(os.environ.get("KOLIBRI_IMAGE_API_TIMEOUT", "180"))) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        items = payload.get("data") or []
        if not items:
            raise RuntimeError("image API returned no images")
        item = items[0]
        if item.get("b64_json"):
            output_path.write_bytes(base64.b64decode(item["b64_json"]))
            return output_path
        if item.get("url"):
            with urllib.request.urlopen(item["url"], timeout=120) as image_resp:
                output_path.write_bytes(image_resp.read())
            return output_path
        raise RuntimeError("image API returned no usable image payload")

    def run_telegram_image_generation(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        prompt = (envelope.get("prompt") or envelope.get("message") or envelope.get("objective") or "").strip()
        if not prompt:
            raise RuntimeError("telegram image task missing prompt")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, None, logs)
        output_path = self.image_output_path(artifact_dir)
        image_path = self.run_configured_image_generator(prompt, output_path, worktree, artifact_dir, stdout_path, stderr_path, task, logs)
        mime_type, image_sha256, image_size_bytes = validated_image_file(image_path)
        evidence_payload = {
            "schema_version": IMAGE_EVIDENCE_SCHEMA,
            "task_id": str(task["task_id"]),
            "attempt_id": str(task.get("attempt_id") or ""),
            "fencing_token": task.get("fencing_token"),
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "content_sha256": image_sha256,
            "media_type": mime_type,
            "size_bytes": image_size_bytes,
        }
        caption = (envelope.get("caption") or "Готово.").strip()
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": None,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "kind": envelope.get("kind", "telegram_image_generation"),
            "prompt": prompt,
            "caption": caption,
            "response": caption,
            "image_path": str(image_path),
            "image_mime_type": mime_type,
            "image_evidence": {
                **evidence_payload,
                "binding_sha256": canonical_json_sha256(evidence_payload),
                "verdict": "passed",
            },
        }
        embedded = self.image_b64_for_result(image_path)
        if not embedded:
            raise RuntimeError("verified image cannot be transported to the artifact gateway")
        result["image_b64"] = embedded
        result = self.finalize_result(task, result, artifact_dir, worktree, changed_files=[])
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_impl_factory_smoke(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        branch = envelope.get("branch", f"agent/{task['task_id']}/impl/factory-smoke")
        base_ref = envelope.get("base_ref", "origin/main")
        smoke_path = envelope.get("smoke_path", "tests/test_factory_runtime_contracts.py")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)

        git_env = {"GIT_TERMINAL_PROMPT": "0"}
        self.run_command(["git", "clone", self.repo_url, str(worktree)], worktree.parent, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "fetch", "origin"], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "checkout", "-B", branch, base_ref], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "config", "user.name", "Kolibri Factory Agent"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "config", "user.email", "factory-agent@users.noreply.github.com"], worktree, stdout_path, stderr_path, task, branch, logs)

        test_file = worktree / smoke_path
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            "import importlib.util\n"
            "import time\n"
            "from pathlib import Path\n\n"
            "ROOT = Path(__file__).resolve().parents[1]\n\n"
            "def load_control():\n"
            "    spec = importlib.util.spec_from_file_location('factory_control', ROOT / 'ops' / 'factory_control.py')\n"
            "    module = importlib.util.module_from_spec(spec)\n"
            "    assert spec.loader is not None\n"
            "    spec.loader.exec_module(module)\n"
            "    return module\n\n"
            "def test_task_envelope_schema_and_idempotency_key():\n"
            "    control = load_control()\n"
            "    task = control.normalize_task({'task_id': 'SCHEMA-1', 'idempotency_key': 'idem-1', 'kind': 'read_only_probe'})\n"
            "    for key in ['task_id', 'idempotency_key', 'kind', 'state', 'attempt', 'lease_owner', 'lease_until', 'result_reference', 'error_type']:\n"
            "        assert key in task\n"
            "    assert task['idempotency_key'] == 'idem-1'\n"
            "    assert task['state'] == 'queued'\n\n"
            "def test_heartbeat_payload_schema():\n"
            "    payload = {'node_id': '9fts', 'agent_id': 'agent-host-9fts', 'pid': 123, 'capabilities': ['implementation'], 'active_task': None}\n"
            "    assert {'node_id', 'agent_id', 'pid', 'capabilities'} <= set(payload)\n"
            "    assert isinstance(payload['capabilities'], list)\n\n"
            "def test_result_envelope_schema():\n"
            "    result = {'node_id': '9fts', 'agent_id': 'agent-host-9fts', 'task_id': 'SCHEMA-1', 'status': 'completed', 'result_path': '/tmp/result.json'}\n"
            "    assert {'node_id', 'agent_id', 'task_id', 'status', 'result_path'} <= set(result)\n\n"
            "def test_lease_expiry_calculation():\n"
            "    control = load_control()\n"
            "    lease_until = time.time() + control.LEASE_DURATION\n"
            "    assert lease_until > time.time()\n"
            "    assert control.LEASE_DURATION >= 60\n",
            encoding="utf-8",
        )
        if shutil.which("mimo"):
            self.run_command(["mimo", "--version"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([
            "python3", "-c",
            "import compileall,pathlib,sys; paths=[p for p in ('backend','infra','scripts','ops') if pathlib.Path(p).exists()]; sys.exit(0 if compileall.compile_dir('.', quiet=1, maxlevels=0) and all(compileall.compile_dir(p, quiet=1) for p in paths) else 1)",
        ], worktree, stdout_path, stderr_path, task, branch, logs)
        venv_dir = artifact_dir / "venv"
        self.run_command(["python3", "-m", "venv", str(venv_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip", "pytest"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pytest", "-q", smoke_path], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "add", smoke_path], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "commit", "-m", "test: add factory runtime contracts"], worktree, stdout_path, stderr_path, task, branch, logs)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(worktree), text=True).strip()

        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": branch,
            "commit": commit,
            "pull_request_url": None,
            "needs_central_pr": True,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "changed_files": [smoke_path],
            "checks": ["mimo --version", "python3 compileall existing runtime paths", f"pytest -q {smoke_path}"],
        }
        result = self.git_push_after_contract_verification(
            task,
            ["git", "push", "-u", "origin", branch],
            worktree,
            stdout_path,
            stderr_path,
            branch,
            logs,
            result,
            artifact_dir,
            [smoke_path],
            git_env,
        )
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_impl_retry_error_clearance(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        branch = envelope.get("branch", f"agent/{task['task_id']}/impl/retry-error-clearance")
        base_ref = envelope.get("base_ref", "origin/main")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)

        git_env = {"GIT_TERMINAL_PROMPT": "0"}
        self.run_command(["git", "clone", self.repo_url, str(worktree)], worktree.parent, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "fetch", "origin"], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "checkout", "-B", branch, base_ref], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "config", "user.name", "Kolibri Factory Agent"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "config", "user.email", "factory-agent@users.noreply.github.com"], worktree, stdout_path, stderr_path, task, branch, logs)

        patcher = artifact_dir / "apply_retry_error_clearance.py"
        patcher.write_text(
            r"""
from pathlib import Path

control_path = Path("ops/factory_control.py")
text = control_path.read_text(encoding="utf-8")

if "def append_attempt_history(" not in text:
    marker = "\ndef create_review_task(source_task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any] | None:\n"
    helper = '''
def append_attempt_history(task: dict[str, Any], status: str, error_type: str | None, error: str | None, result_reference: str | None) -> None:
    attempt = {
        "attempt": task.get("attempt"),
        "attempt_id": task.get("attempt_id"),
        "status": status,
        "error_type": error_type,
        "error": error,
        "result_reference": result_reference,
        "recorded_at": utc_now(),
    }
    history = task.setdefault("attempt_history", [])
    attempt_id = attempt.get("attempt_id")
    if attempt_id:
        history[:] = [item for item in history if item.get("attempt_id") != attempt_id]
    history.append(attempt)


def apply_task_completion(task: dict[str, Any], body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], bool]:
    result = body.get("result", body)
    needs_review = task.get("envelope", {}).get("create_review_on_complete")
    has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
    task["state"] = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
    task["result"] = result
    task["result_reference"] = body.get("result_reference") or result.get("result_path")
    task["heartbeat_at"] = utc_now()
    task["lease_until"] = None
    task["error_type"] = None
    task["error"] = None
    append_attempt_history(task, "completed", None, None, task.get("result_reference"))
    return task, result, has_pr

'''
    if marker not in text:
        raise SystemExit("create_review_task marker not found")
    text = text.replace(marker, "\n" + helper + marker.lstrip("\n"), 1)

old_complete = '''                result = body.get("result", body)
                needs_review = task.get("envelope", {}).get("create_review_on_complete")
                has_pr = bool(result.get("pull_request_url") or result.get("pr_url"))
                task["state"] = STATE_COMPLETED if (not needs_review or has_pr) else STATE_WAITING_REVIEW
                task["result"] = result
                task["result_reference"] = body.get("result_reference") or result.get("result_path")
                task["heartbeat_at"] = utc_now()
                task["lease_until"] = None
                save_task(task)
                review_task = create_review_task(task, result) if has_pr else None
'''
new_complete = '''                task, result, has_pr = apply_task_completion(task, body)
                save_task(task)
                review_task = create_review_task(task, result) if has_pr else None
'''
if old_complete in text:
    text = text.replace(old_complete, new_complete, 1)
elif "apply_task_completion(task, body)" not in text:
    raise SystemExit("complete block marker not found")

old_fail = '''                task["error_type"] = body.get("error_type", "runtime_error")
                task["error"] = body.get("error")
                task["result"] = body.get("result")
                task["result_reference"] = body.get("result_reference")
                task["lease_until"] = None
'''
new_fail = '''                task["error_type"] = body.get("error_type", "runtime_error")
                task["error"] = body.get("error")
                task["result"] = body.get("result")
                task["result_reference"] = body.get("result_reference")
                task["lease_until"] = None
                append_attempt_history(task, "failed", task.get("error_type"), task.get("error"), task.get("result_reference"))
'''
if old_fail in text:
    text = text.replace(old_fail, new_fail, 1)
elif 'append_attempt_history(task, "failed"' not in text:
    raise SystemExit("fail block marker not found")

control_path.write_text(text, encoding="utf-8")

test_path = Path("tests/test_factory_retry_error_clearance.py")
test_path.write_text('''import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control():
    spec = importlib.util.spec_from_file_location("factory_control", ROOT / "ops" / "factory_control.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_successful_retry_clears_top_level_error_and_keeps_attempt_history():
    control = load_control()
    task = control.normalize_task({
        "task_id": "RETRY-CLEAR-1",
        "idempotency_key": "retry-clear-1",
        "kind": "read_only_probe",
        "max_attempts": 3,
    })
    task["attempt"] = 1
    task["attempt_id"] = "RETRY-CLEAR-1-attempt-1"
    task["state"] = control.STATE_RUNNING
    task["error_type"] = "runtime_error"
    task["error"] = "first attempt failed"
    task["result_reference"] = "/tmp/attempt-1/result.json"
    control.append_attempt_history(task, "failed", task["error_type"], task["error"], task["result_reference"])

    task["attempt"] = 2
    task["attempt_id"] = "RETRY-CLEAR-1-attempt-2"
    task["state"] = control.STATE_RUNNING
    task, result, has_pr = control.apply_task_completion(task, {
        "result": {"status": "completed", "result_path": "/tmp/attempt-2/result.json"},
        "result_reference": "/tmp/attempt-2/result.json",
    })

    assert has_pr is False
    assert result["status"] == "completed"
    assert task["state"] == control.STATE_COMPLETED
    assert task["error_type"] is None
    assert task["error"] is None
    assert task["result_reference"] == "/tmp/attempt-2/result.json"
    assert task["attempt_history"][0]["attempt_id"] == "RETRY-CLEAR-1-attempt-1"
    assert task["attempt_history"][0]["error"] == "first attempt failed"
    assert task["attempt_history"][1]["attempt_id"] == "RETRY-CLEAR-1-attempt-2"
    assert task["attempt_history"][1]["error"] is None
''', encoding="utf-8")
""",
            encoding="utf-8",
        )
        self.run_command(["python3", str(patcher)], worktree, stdout_path, stderr_path, task, branch, logs)
        if shutil.which("mimo"):
            self.run_command(["mimo", "--version"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([
            "python3", "-c",
            "import compileall,pathlib,sys; paths=[p for p in ('backend','infra','scripts','ops') if pathlib.Path(p).exists()]; sys.exit(0 if compileall.compile_dir('.', quiet=1, maxlevels=0) and all(compileall.compile_dir(p, quiet=1) for p in paths) else 1)",
        ], worktree, stdout_path, stderr_path, task, branch, logs)
        venv_dir = artifact_dir / "venv"
        self.run_command(["python3", "-m", "venv", str(venv_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip", "pytest"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command([str(venv_dir / "bin" / "python"), "-m", "pytest", "-q", "tests/test_factory_runtime.py", "tests/test_factory_retry_error_clearance.py"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "add", "ops/factory_control.py", "tests/test_factory_retry_error_clearance.py"], worktree, stdout_path, stderr_path, task, branch, logs)
        self.run_command(["git", "commit", "-m", "factory: clear stale retry error on success"], worktree, stdout_path, stderr_path, task, branch, logs)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(worktree), text=True).strip()

        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": branch,
            "commit": commit,
            "pull_request_url": None,
            "needs_central_pr": True,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
            "status": "completed",
            "changed_files": ["ops/factory_control.py", "tests/test_factory_retry_error_clearance.py"],
            "checks": [
                "mimo --version",
                "python3 compileall existing runtime paths",
                "pytest -q tests/test_factory_runtime.py tests/test_factory_retry_error_clearance.py",
            ],
        }
        result = self.git_push_after_contract_verification(
            task,
            ["git", "push", "-u", "origin", branch],
            worktree,
            stdout_path,
            stderr_path,
            branch,
            logs,
            result,
            artifact_dir,
            ["ops/factory_control.py", "tests/test_factory_retry_error_clearance.py"],
            git_env,
        )
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_review_pr(self, task: dict[str, Any]) -> dict[str, Any]:
        envelope = task.get("envelope", {})
        branch = envelope.get("branch")
        pr_url = envelope.get("pull_request_url")
        base_ref = envelope.get("base_ref", "origin/main")
        if not branch:
            raise RuntimeError("review task missing branch")
        worktree, artifact_dir, logs = self.prepare_dirs(task)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        stdout_path = Path(logs["stdout"])
        stderr_path = Path(logs["stderr"])
        self.task_heartbeat(task, worktree, branch, logs)
        git_env = {"GIT_TERMINAL_PROMPT": "0"}
        try:
            self.run_command(["git", "clone", self.repo_url, str(worktree)], worktree.parent, stdout_path, stderr_path, task, branch, logs, git_env)
        except RuntimeError as exc:
            stderr_text = stderr_path.read_text(encoding="utf-8", errors="ignore") if stderr_path.exists() else ""
            message = review_clone_auth_failure_message(stderr_text, self.repo_url)
            if message:
                raise RuntimeError(message) from exc
            raise
        if base_ref.startswith("origin/"):
            self.run_command(["git", "fetch", "origin", base_ref.removeprefix("origin/")], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "fetch", "origin", branch], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        self.run_command(["git", "checkout", "-B", f"review/{task['task_id']}", "FETCH_HEAD"], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
        diff_files = subprocess.check_output(["git", "diff", "--name-only", f"{base_ref}...HEAD"], cwd=str(worktree), text=True).splitlines()
        blocked = [path for path in diff_files if path.startswith(".env") or path.endswith(".key") or path.endswith(".pem")]
        for changed in diff_files:
            path = worktree / changed
            if path.is_file() and "|| true" in path.read_text(encoding="utf-8", errors="ignore"):
                blocked.append(f"dangerous_or_true:{changed}")
        status = "CHANGES_REQUESTED" if blocked else "APPROVED"
        self.run_command([
            "python3", "-c",
            "import compileall,pathlib,sys; paths=[p for p in ('backend','infra','scripts','ops') if pathlib.Path(p).exists()]; sys.exit(0 if compileall.compile_dir('.', quiet=1, maxlevels=0) and all(compileall.compile_dir(p, quiet=1) for p in paths) else 1)",
        ], worktree, stdout_path, stderr_path, task, branch, logs)
        if (worktree / "tests").exists():
            if backend_test_environment_spec(envelope):
                backend_test_environment = self.run_backend_verification_commands(
                    [["python3", "-m", "pytest", "-q"]],
                    worktree,
                    artifact_dir,
                    stdout_path,
                    stderr_path,
                    task,
                    branch,
                    logs,
                )
            else:
                venv_dir = artifact_dir / "venv"
                self.run_command(["python3", "-m", "venv", str(venv_dir)], worktree, stdout_path, stderr_path, task, branch, logs)
                self.run_command([str(venv_dir / "bin" / "python"), "-m", "pip", "install", "--upgrade", "pip", "pytest"], worktree, stdout_path, stderr_path, task, branch, logs)
                self.run_command([str(venv_dir / "bin" / "python"), "-m", "pytest", "-q"], worktree, stdout_path, stderr_path, task, branch, logs)
                backend_test_environment = None
        else:
            backend_test_environment = None
        github_review = "skipped: gh unavailable"
        if shutil.which("gh"):
            event = "APPROVE" if status == "APPROVED" else "REQUEST_CHANGES"
            self.run_command(["gh", "pr", "review", pr_url or branch, f"--{event.lower().replace('_', '-')}", "--body", status], worktree, stdout_path, stderr_path, task, branch, logs, git_env)
            github_review = "submitted"
        result = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "task_id": task["task_id"],
            "agent_id": self.agent_id,
            "attempt_id": task.get("attempt_id"),
            "pid": self.pid,
            "heartbeat_at": utc_now(),
            "worktree": str(worktree),
            "branch": branch,
            "pull_request_url": pr_url,
            "status": status,
            "github_review": github_review,
            "changed_files": [],
            "reviewed_diff_files": diff_files,
            "findings": blocked,
            "log_paths": logs,
            "result_path": str(artifact_dir / "result.json"),
        }
        if backend_test_environment:
            result["backend_test_environment"] = backend_test_environment
        result = self.finalize_result(task, result, artifact_dir, worktree, changed_files=[])
        result_path = self.write_result(artifact_dir, result)
        result["result_path"] = str(result_path)
        return result

    def run_task(self, task: dict[str, Any]) -> None:
        task["_agent_host_started_monotonic"] = time.monotonic()
        sanitize_task_permissions(task)
        result_path = None
        result = None
        try:
            unsupported_reason = self.unsupported_task_reason(task)
            if unsupported_reason:
                worktree, artifact_dir, logs = self.prepare_dirs(task)
                result = unsupported_task_result(task, artifact_dir, unsupported_reason, worktree=worktree)
                result["node_id"] = self.node_id
                result["hostname"] = self.hostname
                result["agent_id"] = self.agent_id
                result["attempt_id"] = task.get("attempt_id")
                result["pid"] = self.pid
                result["heartbeat_at"] = utc_now()
                result["worktree"] = str(worktree)
                result["log_paths"] = logs
                result["result_path"] = str(artifact_dir / "result.json")
                result_path = self.write_result(artifact_dir, result)
                result["result_path"] = str(result_path)
                self.fail(task, "runner_contract_blocked", unsupported_reason, result, result_path, retry=False)
                return

            permission_pack_classification = self.validate_runtime_permission_contract(task)
            kind = task.get("kind")
            envelope = task_envelope(task)
            factory_provider_task = is_factory_provider_task(task)
            if kind in RELEASE_TASK_KINDS:
                result = self.run_release_bundle_task(task)
            elif kind == "impl_factory_smoke":
                result = self.run_impl_factory_smoke(task)
            elif kind == "impl_retry_error_clearance":
                result = self.run_impl_retry_error_clearance(task)
            elif factory_provider_task:
                # Provider prompts are response generation, never code
                # implementation.  Keep both Mimo and Codex on the uniform
                # read-only file/stdin path advertised to Home.
                result = self.run_owner_remote_task(task)
            elif (
                kind in MIMO_DIRECT_KINDS
                and requested_runner_for_envelope(envelope, "mimo") == "mimo"
                and not is_response_only_provider_task(task)
            ):
                result = self.run_direct_mimo_task(task)
            elif kind == "owner_remote_task":
                result = self.run_owner_remote_task(task)
            elif kind in {"telegram_chat_response", "orchestrator_chat_response"}:
                result = self.run_telegram_chat_response(task)
            elif kind in {"telegram_image_generation", "image_generation"}:
                result = self.run_telegram_image_generation(task)
            elif kind == "review_pr":
                result = self.run_review_pr(task)
            elif kind == "read_only_probe":
                result = self.run_read_only_probe(task)
            elif kind == LEASE_HEARTBEAT_PROBE_KIND:
                result = self.run_lease_heartbeat_probe(task)
            else:
                raise RuntimeError(f"unsupported task kind reached dispatch: {kind}")
            result.setdefault("permission_pack_classification", permission_pack_classification)
            result_path = Path(result["result_path"])
            artifact_dir = result_path.parent
            worktree_value = result.get("worktree")
            worktree = Path(worktree_value) if isinstance(worktree_value, str) and worktree_value else None
            preserved_failure_reason = result.get("failure_reason")
            result = finalize_runner_contract(task, result, artifact_dir, worktree=worktree)
            if kind in RELEASE_TASK_KINDS and preserved_failure_reason:
                result["failure_reason"] = preserved_failure_reason
            result_path = self.write_result(artifact_dir, result)
            result["result_path"] = str(result_path)
            if result["status"] == "completed":
                self.complete(task, result, result_path)
                runtime_activation = result.get("agent_host_runtime")
                if (
                    kind in RELEASE_TASK_KINDS
                    and isinstance(runtime_activation, dict)
                    and runtime_activation.get("included") is True
                    and runtime_activation.get("response_profile_included") is True
                ):
                    # The lease is cleared by the successful completion POST
                    # before this process exits.  Restart=always then enters
                    # through the bootstrap path and re-execs the new immutable
                    # Agent Host, so no second task can run on stale code.
                    self._runtime_restart_requested = True
            else:
                error = result.get("blocked_reason") or result.get("failure_reason") or "runner contract prevented completion"
                error_type = (
                    "runner_contract_blocked"
                    if result["status"] == "blocked"
                    else str(result.get("error_type") or "runtime_error")
                )
                retry = (
                    result["status"] == "failed"
                    and bool(result.get("retryable", True))
                    and task_has_attempt_budget(task)
                )
                self.fail(task, error_type, error, result, result_path, retry=retry)
        except PermissionContractError as exc:
            task_id = task["task_id"]
            attempt_id = task.get("attempt_id") or f"{task_id}-attempt-{task.get('attempt', 1)}"
            artifact_dir = self.artifact_root / task_id / attempt_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            result = {
                "node_id": self.node_id,
                "hostname": self.hostname,
                "task_id": task_id,
                "agent_id": self.agent_id,
                "attempt_id": attempt_id,
                "pid": self.pid,
                "status": "blocked",
                "error_type": "permission_contract_violation",
                "error": str(exc),
                "completed_at": utc_now(),
                "permission_pack_classification": exc.classification,
                "blocked_reason": "permission_contract_violation",
                "next_recommended_task": "remove write-capable runtime permissions or route this as a write-enabled task",
            }
            result = finalize_runner_contract(task, result, artifact_dir, failure_reason=str(exc))
            result_path = self.write_result(artifact_dir, result)
            self.fail(task, "permission_contract_violation", str(exc), result, result_path, retry=False)
        except Exception as exc:
            task_id = task["task_id"]
            attempt_id = task.get("attempt_id") or f"{task_id}-attempt-{task.get('attempt', 1)}"
            artifact_dir = self.artifact_root / task_id / attempt_id
            artifact_dir.mkdir(parents=True, exist_ok=True)
            safe_error = redact_sensitive_text(str(exc))
            result = {
                "node_id": self.node_id,
                "hostname": self.hostname,
                "task_id": task_id,
                "agent_id": self.agent_id,
                "attempt_id": attempt_id,
                "pid": self.pid,
                "status": "failed",
                "error": safe_error,
                "completed_at": utc_now(),
                "result_path": str(artifact_dir / "result.json"),
            }
            requested_runner = requested_runner_for_envelope(task_envelope(task))
            if requested_runner:
                result.setdefault("runner", requested_runner)
            if isinstance(exc, RunnerExecutionError):
                self.persist_runner_failure(exc)
                result["status"] = "blocked"
                result["runner"] = exc.runner
            result = finalize_runner_contract(
                task,
                result,
                artifact_dir,
                failure_reason=safe_error,
            )
            result_path = self.write_result(artifact_dir, result)
            retry = task_has_attempt_budget(task)
            if isinstance(exc, RunnerExecutionError):
                error_type = exc.error_type
                retry = bool(getattr(exc, "retry", False))
                result["status"] = "blocked"
                result["blocked_reason"] = exc.error_type
                result["failure_reason"] = redact_sensitive_text(str(exc))
                if exc.error_type == "provider_runner_outdated":
                    result["next_recommended_task"] = (
                        f"upgrade {exc.runner} on this node, rerun readiness, then restore {runner_capability(exc.runner)}"
                    )
                elif exc.error_type in {
                    "runner_auth_blocked", "runner_auth_failed", "runner_access_denied", "runner_policy_blocked",
                }:
                    result["next_recommended_task"] = (
                        f"repair {exc.runner} auth on this node or route to another online node with {runner_capability(exc.runner)}"
                    )
                else:
                    result["next_recommended_task"] = (
                        f"route to another online node with {runner_capability(exc.runner)} or install the requested runner"
                    )
                result_path = self.write_result(artifact_dir, result)
            elif isinstance(exc, TaskProcessInterrupted):
                error_type = exc.error_type
                retry = exc.retry
                result["failure_reason"] = redact_sensitive_text(str(exc))
                result["next_recommended_task"] = (
                    "resubmit with a larger bounded max_wall_seconds"
                    if exc.error_type == "provider_timeout"
                    else "do not retry a cancelled or fenced task attempt"
                )
                result_path = self.write_result(artifact_dir, result)
            elif isinstance(exc, BackendTestEnvironmentError) or str(exc).startswith("backend_test_environment_failed:"):
                error_type = "backend_test_environment_failed"
                retry = False
                result["status"] = "blocked"
                result["blocked_reason"] = "backend_test_environment_failed"
                result["next_recommended_task"] = "repair the declared backend test environment requirements or package list, then rerun verification"
                result_path = self.write_result(artifact_dir, result)
            elif str(exc).startswith("review_clone_auth_failed:"):
                error_type = "review_clone_auth_failed"
            else:
                error_type = "runtime_error"
            if error_type == "review_clone_auth_failed":
                result["next_recommended_task"] = "repair Agent Host git credentials, then rerun the review task"
                result_path = self.write_result(artifact_dir, result)
                retry = False
            self.fail(task, error_type, safe_error, result, result_path, retry=retry)

    def loop(self) -> None:
        while not STOP and not self._runtime_restart_requested:
            try:
                if not self._registered:
                    self.register()
                readiness_refreshed = self.refresh_codex_readiness_if_due()
                if (
                    readiness_refreshed
                    or time.time() - self._last_node_heartbeat >= self.heartbeat_interval
                ):
                    self.node_heartbeat()
            except Exception as exc:
                # A temporary Control Plane outage must not create a systemd
                # restart storm across the whole fleet.
                self._registered = False
                print(f"{utc_now()} control_plane_heartbeat_failed {exc}", flush=True)
                time.sleep(5)
                continue
            try:
                task = self.lease()
            except Exception as exc:
                print(f"{utc_now()} lease_failed {exc}", flush=True)
                time.sleep(5)
                continue
            if task:
                self._active_task_id = str(task["task_id"])
                try:
                    self.node_heartbeat(active_task=self._active_task_id)
                    self.run_task(task)
                finally:
                    self._active_task_id = None
                if self._runtime_restart_requested:
                    break
                self.node_heartbeat()
            time.sleep(2)


def handle_stop(signum: int, frame: Any) -> None:
    del signum, frame
    global STOP
    STOP = True


def main() -> int:
    maybe_reexec_release_agent_host()
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL"))
    parser.add_argument("--control-urls", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS"))
    parser.add_argument("--node-id", default=os.environ.get("KOLIBRI_NODE_ID", platform.node()))
    parser.add_argument("--agent-id", default=os.environ.get("KOLIBRI_AGENT_ID"))
    parser.add_argument("--capabilities", default=os.environ.get("KOLIBRI_AGENT_CAPABILITIES", "read_only_probe"))
    parser.add_argument("--repo-url", default=os.environ.get("KOLIBRI_REPO_URL", "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git"))
    parser.add_argument("--work-root", default=os.environ.get("KOLIBRI_AGENT_WORK_ROOT", "/var/lib/kolibri-agent/worktrees"))
    parser.add_argument("--artifact-root", default=os.environ.get("KOLIBRI_AGENT_ARTIFACT_ROOT", "/var/lib/kolibri-agent/artifacts"))
    parser.add_argument("--heartbeat-interval", type=int, default=int(os.environ.get("KOLIBRI_HEARTBEAT_INTERVAL", "10")))
    parser.add_argument("--lease-refresh", type=int, default=int(os.environ.get("KOLIBRI_LEASE_REFRESH", "5")))
    parser.add_argument("--max-inflight", type=int, default=int(os.environ.get("KOLIBRI_MAX_INFLIGHT", "1")))
    parser.add_argument(
        "--codex-readiness-refresh-seconds",
        type=int,
        default=int(os.environ.get("KOLIBRI_CODEX_READINESS_REFRESH_SECONDS", "0")),
    )
    parser.add_argument(
        "--external-provider-credential-file",
        default=os.environ.get("KOLIBRI_EXTERNAL_PROVIDER_ACTOR_CREDENTIAL_FILE", ""),
    )
    parser.add_argument("--labels-json", default=os.environ.get("KOLIBRI_NODE_LABELS_JSON", "{}"))
    args = parser.parse_args()
    args.control_url = resolve_home_control_plane_url(args.control_url, args.control_urls)
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    AgentHost(args).loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
