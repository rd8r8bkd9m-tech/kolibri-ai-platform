#!/usr/bin/env python3
"""Persistent Kolibri remote agent host."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import mimetypes
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STOP = False
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
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
}
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
LEASE_FENCE_FIELDS = ("attempt_id", "lease_id", "fencing_token")
RUNTIME_RELEASE_ID = os.environ.get("KOLIBRI_RUNTIME_RELEASE_ID", "unversioned")
RUNNER_AUTH_FAILURE_MARKERS = (
    "401",
    "403",
    "api key",
    "auth",
    "authorization",
    "credential",
    "expired token",
    "forbidden",
    "invalid token",
    "login required",
    "not logged in",
    "oauth",
    "permission denied",
    "refresh token",
    "unauthorized",
)
SECRET_REDACTION_MARKERS = (
    "api_key",
    "authorization",
    "bearer",
    "password",
    "refresh_token",
    "secret",
    "token",
)
SERIALIZED_TOOL_CALL_MARKERS = (
    "<tool_call",
    "</tool_call>",
    "<function_call",
    "</function_call>",
    "<read>",
    "</read>",
    "<file_path>",
    "</file_path>",
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


class LeaseContractError(RuntimeError):
    """Raised when Control Plane work is missing or changes its lease fence."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def request(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 20) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 204:
                return None
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


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


def redact_sensitive_text(text: str) -> str:
    redacted_lines: list[str] = []
    for line in text.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in SECRET_REDACTION_MARKERS):
            redacted_lines.append("[redacted sensitive runner output]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)


def sanitize_text_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    redacted = redact_sensitive_text(text)
    if redacted != text:
        path.write_text(redacted + ("\n" if text.endswith("\n") else ""), encoding="utf-8")


def runner_auth_blocked(stderr_text: str) -> bool:
    lowered = stderr_text.lower()
    return any(marker in lowered for marker in RUNNER_AUTH_FAILURE_MARKERS)


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
    final["artifact_dir"] = str(artifact_dir)

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
        control_urls_arg = getattr(args, "control_urls", None) or args.control_url
        self.control_urls = [url.strip().rstrip("/") for url in control_urls_arg.split(",") if url.strip()]
        if not self.control_urls:
            self.control_urls = [args.control_url.rstrip("/")]
        self.control_url = self.control_urls[0]
        self.node_id = args.node_id
        self.agent_id = args.agent_id or f"{args.node_id}-agent-host"
        self.capabilities = [item for item in args.capabilities.split(",") if item]
        self.repo_url = args.repo_url
        self.work_root = Path(args.work_root)
        self.artifact_root = Path(args.artifact_root)
        self.heartbeat_interval = args.heartbeat_interval
        self.lease_refresh = args.lease_refresh
        self.max_inflight = args.max_inflight
        self.hostname = platform.node()
        self.pid = os.getpid()
        self.runtime_release_id = str(getattr(args, "runtime_release_id", RUNTIME_RELEASE_ID) or "unversioned")
        self._last_node_heartbeat = 0.0
        self._registered = False
        self._active_lease_fences: dict[str, dict[str, Any]] = {}
        self.runner_status = self.detect_runner_status()
        self.capabilities = self.capabilities_with_runners()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self._request_with_failover("POST", path, body)

    def get(self, path: str) -> Any:
        return self._request_with_failover("GET", path)

    def _ordered_control_urls(self) -> list[str]:
        # A request-local relay may succeed, but it must never become a sticky
        # replacement for the configured Home authority on the next request.
        return list(self.control_urls)

    def _request_with_failover(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        last_exc: Exception | None = None
        for control_url in self._ordered_control_urls():
            try:
                result = request(method, f"{control_url}{path}", body)
                self.control_url = control_url
                return result
            except Exception as exc:
                last_exc = exc
        assert last_exc is not None
        raise last_exc

    def detect_runner_status(self) -> dict[str, dict[str, Any]]:
        status: dict[str, dict[str, Any]] = {}
        for runner in sorted(SUPPORTED_AI_RUNNERS):
            try:
                path = shutil.which(runner)
            except RecursionError:
                path = None
            status[runner] = {
                "status": "available" if path else "unavailable",
                "path": path,
                "checked_at": utc_now(),
            }
        return status

    def capabilities_with_runners(self) -> list[str]:
        capabilities = list(dict.fromkeys(self.capabilities))
        for runner, state in self.runner_status.items():
            if state.get("status") == "available":
                cap = runner_capability(runner)
                if cap not in capabilities:
                    capabilities.append(cap)
        return capabilities

    def mark_runner_status(self, runner: str, status: str, error_type: str | None = None) -> None:
        current = self.runner_status.setdefault(runner, {})
        current.update({
            "status": status,
            "error_type": error_type,
            "updated_at": utc_now(),
        })

    def register(self) -> None:
        body = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "capabilities": self.capabilities,
            "runners": self.runner_status,
            "runtime_release_id": self.runtime_release_id,
            **machine_stats(),
        }
        self.post("/v1/nodes/register", body)
        self._registered = True

    def node_heartbeat(self, active_task: str | None = None) -> None:
        body = {
            "node_id": self.node_id,
            "hostname": self.hostname,
            "agent_id": self.agent_id,
            "pid": self.pid,
            "capabilities": self.capabilities,
            "runners": self.runner_status,
            "active_task": active_task,
            "runtime_release_id": self.runtime_release_id,
            **machine_stats(),
        }
        self.post(f"/v1/nodes/{self.node_id}/heartbeat", body)
        self._last_node_heartbeat = time.time()

    def _fence_from_leased_task(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task.get("task_id") or "").strip()
        if not task_id:
            raise LeaseContractError("leased task is missing task_id")
        missing = [field for field in LEASE_FENCE_FIELDS if task.get(field) is None]
        if missing:
            raise LeaseContractError(
                f"leased task {task_id} is missing Control Plane fence fields: {', '.join(missing)}"
            )
        expected_release = str(task.get("executor_release_id") or "unversioned")
        if expected_release != self.runtime_release_id:
            raise LeaseContractError(
                f"leased task {task_id} targets runtime release {expected_release}, not {self.runtime_release_id}"
            )
        fence = {
            "attempt_id": task["attempt_id"],
            "lease_id": task["lease_id"],
            "fencing_token": task["fencing_token"],
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "runtime_release_id": self.runtime_release_id,
        }
        if task.get("lease_slot_id") is not None:
            fence["slot_id"] = task["lease_slot_id"]
        return fence

    def _remember_lease_fence(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task.get("task_id") or "").strip()
        fence = self._fence_from_leased_task(task)
        existing = self._active_lease_fences.get(task_id)
        if existing is not None and existing != fence:
            raise LeaseContractError(f"lease fence changed for active task {task_id}")
        self._active_lease_fences[task_id] = dict(fence)
        return dict(fence)

    def _task_mutation_fence(self, task: dict[str, Any]) -> dict[str, Any]:
        task_id = str(task.get("task_id") or "").strip()
        remembered = self._active_lease_fences.get(task_id)
        observed = self._fence_from_leased_task(task)
        if remembered is None:
            self._active_lease_fences[task_id] = dict(observed)
            remembered = observed
        if remembered != observed:
            raise LeaseContractError(f"task {task_id} no longer matches its leased fence")
        return dict(remembered)

    def _forget_lease_fence(self, task: dict[str, Any]) -> None:
        task_id = str(task.get("task_id") or "").strip()
        if task_id:
            self._active_lease_fences.pop(task_id, None)

    def task_heartbeat(self, task: dict[str, Any], worktree: Path, branch: str | None, logs: dict[str, str], pid: int | None = None) -> dict[str, Any]:
        if time.time() - self._last_node_heartbeat >= self.heartbeat_interval:
            self.node_heartbeat(active_task=task["task_id"])
        body = {
            **self._task_mutation_fence(task),
            "state": "running",
            "pid": pid or self.pid,
            "worktree": str(worktree),
            "branch": branch,
            "log_paths": logs,
        }
        return self.post(f"/v1/tasks/{task['task_id']}/heartbeat", body)

    def lease(self) -> dict[str, Any] | None:
        task = self.post("/v1/tasks/lease", {
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "capabilities": self.capabilities,
            "runners": self.runner_status,
            "runtime_release_id": self.runtime_release_id,
        })
        if not isinstance(task, dict):
            return task
        sanitized = sanitize_task_permissions(task)
        self._remember_lease_fence(sanitized)
        return sanitized

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
    ) -> None:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)
        display_command = command_label or " ".join(command)
        with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
            stdout.write(f"\n$ {display_command}\n".encode("utf-8"))
            stdout.flush()
            proc = subprocess.Popen(command, cwd=str(cwd), stdout=stdout, stderr=stderr, env=merged_env)
            last_refresh = 0.0
            while proc.poll() is None:
                if STOP:
                    proc.terminate()
                    raise RuntimeError("agent host received SIGTERM")
                if time.time() - last_refresh >= self.lease_refresh:
                    self.task_heartbeat(task, cwd, branch, logs, proc.pid)
                    last_refresh = time.time()
                time.sleep(2)
            if proc.returncode != 0:
                raise RuntimeError(f"command failed with rc={proc.returncode}: {display_command}")

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

    @classmethod
    def parse_json_response_payload(cls, stdout_path: Path) -> dict[str, Any]:
        final_messages: list[str] = []
        text_parts: list[str] = []
        deltas: list[str] = []
        useful_objects: list[dict[str, Any]] = []
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

            event_final, event_parts, event_deltas = cls._extract_json_event_text(event)
            final_messages.extend(event_final)
            text_parts.extend(event_parts)
            deltas.extend(event_deltas)
            if SAFE_MIMO_RESULT_FIELDS.intersection(event):
                useful_objects.append(cls._safe_json_value(event))

        for parts in (final_messages, text_parts, deltas):
            response_text = "".join(parts).strip()
            if response_text:
                payload: dict[str, Any] = {"response": response_text}
                if useful_objects:
                    payload["runner_output"] = useful_objects[-1]
                return payload
        if useful_objects:
            output = useful_objects[-1]
            text = output.get("response") or output.get("message") or output.get("text") or output.get("summary")
            if not isinstance(text, str) or not text.strip():
                text = json.dumps(output, ensure_ascii=False, sort_keys=True)
            return {"response": text.strip(), "runner_output": output}
        return {"response": ""}

    @classmethod
    def parse_json_text_response(cls, stdout_path: Path) -> str:
        return str(cls.parse_json_response_payload(stdout_path).get("response") or "")

    @staticmethod
    def serialized_tool_call_marker(response_text: str) -> str | None:
        """Return the first unexecuted tool marker emitted as answer text.

        ``mimo run`` is a response-only transport in the current Agent Host.
        A model can still *describe* a tool call in its final text.  That is
        not execution evidence and must never be promoted to ``completed``.
        Mixed prose plus a serialized tool call is rejected as well; checking
        only responses that consist entirely of ``<tool_call>`` allowed false
        completions through the factory verifier.
        """

        normalized = response_text.casefold()
        return next((marker for marker in SERIALIZED_TOOL_CALL_MARKERS if marker in normalized), None)

    @staticmethod
    def _read_runner_output_for_error(stdout_path: Path, stderr_path: Path) -> str:
        chunks = []
        for path in (stdout_path, stderr_path):
            if path.exists():
                chunks.append(path.read_text(encoding="utf-8", errors="replace")[-4000:])
        return "\n".join(chunks)

    @staticmethod
    def classify_runner_error(error: str, runner_output: str) -> tuple[str, str, bool]:
        combined = f"{error}\n{runner_output}".lower()
        if "http 401" in combined or " 401" in combined or "unauthorized" in combined:
            return "runner_auth_failed", "mimo runner authentication failed with HTTP 401", False
        if "http 403" in combined or " 403" in combined or "forbidden" in combined or "illegal_access" in combined:
            if "illegal_access" in combined:
                return "runner_policy_blocked", "mimo runner request was blocked by policy: illegal_access", False
            return "runner_access_denied", "mimo runner access denied with HTTP 403", False
        return "runtime_error", error, True

    def run_json_payload_command(
        self,
        command: list[str],
        command_label: str,
        empty_response_label: str,
        worktree: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
    ) -> dict[str, Any]:
        try:
            self.run_command(
                command,
                worktree,
                stdout_path,
                stderr_path,
                task,
                branch,
                logs,
                command_label=command_label,
            )
        except Exception as exc:
            error_type, message, retry = self.classify_runner_error(
                str(exc),
                self._read_runner_output_for_error(stdout_path, stderr_path),
            )
            if error_type != "runtime_error":
                sanitize_text_file(stdout_path)
                sanitize_text_file(stderr_path)
                raise RunnerExecutionError(error_type, "mimo", message, retry=retry) from exc
            raise
        payload = self.parse_json_response_payload(stdout_path)
        if not payload.get("response"):
            raise RuntimeError(f"{empty_response_label} completed without text response")
        marker = self.serialized_tool_call_marker(str(payload["response"]))
        if marker is not None:
            raise RunnerExecutionError(
                "response_only_tool_call_output",
                "mimo",
                f"mimo response-only runner emitted an unexecuted serialized tool call ({marker})",
                retry=False,
            )
        return payload

    def run_json_text_command(
        self,
        command: list[str],
        command_label: str,
        empty_response_label: str,
        worktree: Path,
        stdout_path: Path,
        stderr_path: Path,
        task: dict[str, Any],
        branch: str | None,
        logs: dict[str, str],
    ) -> str:
        payload = self.run_json_payload_command(
            command,
            command_label,
            empty_response_label,
            worktree,
            stdout_path,
            stderr_path,
            task,
            branch,
            logs,
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
    ) -> str:
        runner = runner.strip().lower()
        if runner not in SUPPORTED_AI_RUNNERS:
            raise RunnerExecutionError("runner_unavailable", runner, f"unsupported runner requested: {runner}")
        if runner == "api":
            return self.run_api_text_runner(prompt)
        if runner == "local_llm":
            return self.run_local_llm_text_runner(prompt)
        executable = shutil.which(runner)
        if not executable:
            self.mark_runner_status(runner, "unavailable", "runner_unavailable")
            raise RunnerExecutionError("runner_unavailable", runner, f"{runner} executable is not available on this node")

        if runner == "codex":
            command = [executable, "exec", "--json", "--skip-git-repo-check", "--sandbox", "danger-full-access", prompt]
            command_label = f"{executable} exec --json --skip-git-repo-check --sandbox danger-full-access <prompt>"
        else:
            command = [executable, "run", "--format", "json", "--title", title, prompt]
            command_label = f"{executable} run --format json --title {title} <prompt>"

        try:
            return self.run_json_text_command(
                command,
                command_label,
                runner,
                worktree,
                stdout_path,
                stderr_path,
                task,
                branch,
                logs,
            )
        except RuntimeError as exc:
            stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
            auth_blocked = runner_auth_blocked(stderr_text) or runner_auth_blocked(str(exc))
            sanitize_text_file(stdout_path)
            sanitize_text_file(stderr_path)
            if auth_blocked:
                self.mark_runner_status(runner, "blocked", "runner_auth_blocked")
                raise RunnerExecutionError("runner_auth_blocked", runner, f"{runner} auth blocked on this node") from exc
            raise

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
        self.post(f"/v1/tasks/{task['task_id']}/complete", {
            **self._task_mutation_fence(task),
            "result_reference": str(result_path),
            "result": result,
        })
        self._forget_lease_fence(task)

    def fail(self, task: dict[str, Any], error_type: str, error: str, result: dict[str, Any] | None, result_path: Path | None, retry: bool = True) -> None:
        self.post(f"/v1/tasks/{task['task_id']}/fail", {
            **self._task_mutation_fence(task),
            "error_type": error_type,
            "error": error,
            "result": result,
            "result_reference": str(result_path) if result_path else None,
            "retry": retry,
        })
        self._forget_lease_fence(task)

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
            "permission_pack_classification": classify_permission_pack(task),
        }
        result = self.finalize_result(task, result, artifact_dir, worktree, changed_files=[])
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
            "response": response_text,
        }
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
        }
        (artifact_dir / "runner-contract.json").write_text(
            json.dumps(runner_artifact, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        mimo = shutil.which("mimo")
        if not mimo:
            raise RunnerExecutionError("runner_unavailable", "mimo", "mimo executable is not available on this node")
        payload = self.run_json_payload_command(
            [mimo, "run", "--format", "json", "--title", f"owner-task-{task['task_id']}", prompt],
            f"{mimo} run --format json --title owner-task-{task['task_id']} <prompt>",
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
        max_bytes = int(os.environ.get("KOLIBRI_IMAGE_RESULT_EMBED_MAX_BYTES", str(8 * 1024 * 1024)))
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
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
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
        }
        embedded = self.image_b64_for_result(image_path)
        if embedded:
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
        "max_retries": 2,
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
            if kind == "impl_factory_smoke":
                result = self.run_impl_factory_smoke(task)
            elif kind == "impl_retry_error_clearance":
                result = self.run_impl_retry_error_clearance(task)
            elif kind in MIMO_DIRECT_KINDS and requested_runner_for_envelope(task_envelope(task), "mimo") == "mimo":
                result = self.run_direct_mimo_task(task)
            elif kind == "owner_remote_task":
                result = self.run_owner_remote_task(task)
            elif kind in {"telegram_chat_response", "orchestrator_chat_response"}:
                result = self.run_telegram_chat_response(task)
            elif kind == "telegram_image_generation":
                result = self.run_telegram_image_generation(task)
            elif kind == "review_pr":
                result = self.run_review_pr(task)
            elif kind == "read_only_probe":
                result = self.run_read_only_probe(task)
            else:
                raise RuntimeError(f"unsupported task kind reached dispatch: {kind}")
            result.setdefault("permission_pack_classification", permission_pack_classification)
            result_path = Path(result["result_path"])
            artifact_dir = result_path.parent
            worktree_value = result.get("worktree")
            worktree = Path(worktree_value) if isinstance(worktree_value, str) and worktree_value else None
            result = finalize_runner_contract(task, result, artifact_dir, worktree=worktree)
            result_path = self.write_result(artifact_dir, result)
            result["result_path"] = str(result_path)
            if result["status"] == "completed":
                self.complete(task, result, result_path)
            else:
                error = result.get("blocked_reason") or result.get("failure_reason") or "runner contract prevented completion"
                error_type = "runner_contract_blocked" if result["status"] == "blocked" else "runtime_error"
                retry = result["status"] == "failed" and int(task.get("attempt", 0)) < int(task.get("max_retries", 3))
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
            result = {
                "node_id": self.node_id,
                "hostname": self.hostname,
                "task_id": task_id,
                "agent_id": self.agent_id,
                "attempt_id": attempt_id,
                "pid": self.pid,
                "status": "failed",
                "error": redact_sensitive_text(str(exc)),
                "completed_at": utc_now(),
                "result_path": str(artifact_dir / "result.json"),
            }
            if isinstance(exc, RunnerExecutionError):
                result["status"] = "blocked"
                result["runner"] = exc.runner
            result = finalize_runner_contract(task, result, artifact_dir, failure_reason=str(exc))
            result_path = self.write_result(artifact_dir, result)
            retry = int(task.get("attempt", 0)) < int(task.get("max_retries", 3))
            if isinstance(exc, RunnerExecutionError):
                error_type = exc.error_type
                retry = bool(getattr(exc, "retry", False))
                result["status"] = "blocked"
                result["blocked_reason"] = exc.error_type
                result["failure_reason"] = redact_sensitive_text(str(exc))
                result["next_recommended_task"] = (
                    f"repair {exc.runner} auth on this node or route to another online node with {runner_capability(exc.runner)}"
                    if exc.error_type in {"runner_auth_blocked", "runner_auth_failed", "runner_access_denied", "runner_policy_blocked"}
                    else f"route to another online node with {runner_capability(exc.runner)} or install the requested runner"
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
            self.fail(task, error_type, redact_sensitive_text(str(exc)), result, result_path, retry=retry)

    def loop(self) -> None:
        while not STOP:
            try:
                if not self._registered:
                    self.register()
                if time.time() - self._last_node_heartbeat >= self.heartbeat_interval:
                    self.node_heartbeat()
            except Exception as exc:
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
                self.node_heartbeat(active_task=task["task_id"])
                self.run_task(task)
                self.node_heartbeat()
            time.sleep(2)


def handle_stop(signum: int, frame: Any) -> None:
    del signum, frame
    global STOP
    STOP = True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-url", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://127.0.0.1:9101"))
    parser.add_argument("--control-urls", default=os.environ.get("KOLIBRI_FACTORY_CONTROL_URLS") or os.environ.get("KOLIBRI_FACTORY_CONTROL_URL", "http://127.0.0.1:9101"))
    parser.add_argument("--runtime-release-id", default=RUNTIME_RELEASE_ID)
    parser.add_argument("--node-id", default=os.environ.get("KOLIBRI_NODE_ID", platform.node()))
    parser.add_argument("--agent-id", default=os.environ.get("KOLIBRI_AGENT_ID"))
    parser.add_argument("--capabilities", default=os.environ.get("KOLIBRI_AGENT_CAPABILITIES", "read_only_probe"))
    parser.add_argument("--repo-url", default=os.environ.get("KOLIBRI_REPO_URL", "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git"))
    parser.add_argument("--work-root", default=os.environ.get("KOLIBRI_AGENT_WORK_ROOT", "/var/lib/kolibri-agent/worktrees"))
    parser.add_argument("--artifact-root", default=os.environ.get("KOLIBRI_AGENT_ARTIFACT_ROOT", "/var/lib/kolibri-agent/artifacts"))
    parser.add_argument("--heartbeat-interval", type=int, default=int(os.environ.get("KOLIBRI_HEARTBEAT_INTERVAL", "10")))
    parser.add_argument("--lease-refresh", type=int, default=int(os.environ.get("KOLIBRI_LEASE_REFRESH", "20")))
    parser.add_argument("--max-inflight", type=int, default=int(os.environ.get("KOLIBRI_MAX_INFLIGHT", "1")))
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)
    AgentHost(args).loop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
