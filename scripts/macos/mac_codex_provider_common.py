#!/usr/bin/env python3
"""Shared, non-secret macOS LaunchAgent lifecycle helpers."""

from __future__ import annotations

import hashlib
import html
import json
import os
import plistlib
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


LABEL = "ru.kolibriai.mac-codex-provider"
MANAGED_MARKER = ".managed-by-kolibri-mac-codex-provider"
MAC_CODEX_READINESS_REFRESH_SECONDS = 240
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
RUNTIME_SOURCE_FILES = (
    ("ops/agent_host.py", "agent_host.py"),
    ("ops/control_plane_endpoint.py", "control_plane_endpoint.py"),
    ("ops/runner_access.py", "runner_access.py"),
    ("ops/release_authority.py", "release_authority.py"),
    ("ops/release_helper.py", "release_helper.py"),
    ("ops/release_installer.py", "release_installer.py"),
    ("ops/macos/mac_codex_provider_launcher.py", "mac_codex_provider_launcher.py"),
)
FORBIDDEN_ENVIRONMENT_KEYS = frozenset({
    "CODEX_ACCESS_TOKEN",
    "CODEX_HOME",
    "OPENAI_API_KEY",
    "KOLIBRI_FACTORY_CONTROL_URL",
    "KOLIBRI_FACTORY_CONTROL_URLS",
})


class MacProviderConfigError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MacProviderLayout:
    home: Path
    base: Path
    releases: Path
    config: Path
    work: Path
    artifacts: Path
    logs: Path
    runner_access: Path
    provider_credential: Path
    sanitized_log: Path
    bootstrap_log: Path
    launch_agent: Path

    @classmethod
    def from_home(cls, home: str | Path) -> "MacProviderLayout":
        owner_home = Path(home).expanduser().resolve()
        base = owner_home / "Library" / "Application Support" / "Kolibri" / "mac-codex-provider"
        logs = base / "logs"
        return cls(
            home=owner_home,
            base=base,
            releases=base / "runtime" / "releases",
            config=base / "config",
            work=owner_home / ".kolibri-agent" / "worktrees",
            artifacts=owner_home / ".kolibri-agent" / "artifacts",
            logs=logs,
            runner_access=base / "config" / "runner-access.json",
            provider_credential=base / "config" / "external-provider-actor.credential",
            sanitized_log=logs / "agent-host.log",
            bootstrap_log=logs / "launchd-bootstrap.log",
            launch_agent=owner_home / "Library" / "LaunchAgents" / f"{LABEL}.plist",
        )


def validate_identifier(value: str, field: str) -> str:
    normalized = str(value or "").strip()
    if not SAFE_ID.fullmatch(normalized):
        raise MacProviderConfigError(f"invalid_{field}")
    return normalized


def require_regular_file(path: str | Path, code: str, *, executable: bool = False) -> Path:
    candidate = Path(path).expanduser()
    try:
        info = candidate.lstat()
    except OSError as exc:
        raise MacProviderConfigError(code) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise MacProviderConfigError(code)
    resolved = candidate.resolve()
    if executable and not os.access(resolved, os.X_OK):
        raise MacProviderConfigError(code)
    return resolved


def require_executable(path: str | Path, code: str) -> Path:
    candidate = Path(path).expanduser().absolute()
    try:
        resolved = candidate.resolve(strict=True)
        info = resolved.stat()
    except OSError as exc:
        raise MacProviderConfigError(code) from exc
    if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
        raise MacProviderConfigError(code)
    return candidate


def ensure_directory(path: Path, mode: int = 0o700, *, change_mode: bool = True) -> Path:
    try:
        info = path.lstat()
    except FileNotFoundError:
        path.mkdir(parents=True, mode=mode)
        info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise MacProviderConfigError("managed_directory_unsafe")
    if change_mode:
        os.chmod(path, mode)
    return path


def source_files(source_root: str | Path) -> list[tuple[Path, str]]:
    root = Path(source_root).expanduser().resolve()
    result: list[tuple[Path, str]] = []
    for relative, installed_name in RUNTIME_SOURCE_FILES:
        result.append((require_regular_file(root / relative, "runtime_source_missing"), installed_name))
    return result


def runtime_digest(files: list[tuple[Path, str]]) -> str:
    digest = hashlib.sha256()
    for path, installed_name in sorted(files, key=lambda item: item[1]):
        digest.update(installed_name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def atomic_write(path: Path, payload: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_path, mode)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass


def render_launch_agent(template_path: Path, replacements: Mapping[str, str]) -> tuple[bytes, dict[str, Any]]:
    template = require_regular_file(template_path, "launch_agent_template_missing").read_text(encoding="utf-8")
    rendered = template
    for key, value in replacements.items():
        if any(character in value for character in ("\0", "\n", "\r")):
            raise MacProviderConfigError("launch_agent_value_invalid")
        rendered = rendered.replace(f"__{key}__", html.escape(value, quote=True))
    if re.search(r"__[A-Z0-9_]+__", rendered):
        raise MacProviderConfigError("launch_agent_placeholder_unresolved")
    try:
        payload = plistlib.loads(rendered.encode("utf-8"))
    except (plistlib.InvalidFileException, ValueError) as exc:
        raise MacProviderConfigError("launch_agent_plist_invalid") from exc
    validate_launch_agent_payload(payload)
    return plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False), payload


def validate_launch_agent_payload(payload: Any) -> None:
    if not isinstance(payload, dict) or payload.get("Label") != LABEL:
        raise MacProviderConfigError("launch_agent_label_invalid")
    if payload.get("KolibriManagedContract") != "kolibri.mac-codex-provider.launchagent.v1":
        raise MacProviderConfigError("launch_agent_managed_contract_invalid")
    arguments = payload.get("ProgramArguments")
    if not isinstance(arguments, list) or not arguments or not all(isinstance(item, str) for item in arguments):
        raise MacProviderConfigError("launch_agent_arguments_invalid")
    if "--control-url" in arguments or "--control-urls" in arguments:
        raise MacProviderConfigError("launch_agent_static_control_plane_forbidden")
    environment = payload.get("EnvironmentVariables")
    if not isinstance(environment, dict):
        raise MacProviderConfigError("launch_agent_environment_invalid")
    if FORBIDDEN_ENVIRONMENT_KEYS.intersection(environment):
        raise MacProviderConfigError("launch_agent_secret_or_static_environment_forbidden")
    required_environment = {
        "HOME", "PATH", "PYTHONPATH", "KOLIBRI_MESH_MEMBERSHIP_MANIFEST",
        "KOLIBRI_RUNNER_ACCESS_MANIFEST", "KOLIBRI_NODE_LABELS_JSON",
        "KOLIBRI_CODEX_READINESS_REFRESH_SECONDS",
        "KOLIBRI_EXTERNAL_PROVIDER_ACTOR_CREDENTIAL_FILE",
    }
    if not required_environment.issubset(environment):
        raise MacProviderConfigError("launch_agent_environment_incomplete")
    if environment.get("KOLIBRI_CODEX_READINESS_REFRESH_SECONDS") != str(
        MAC_CODEX_READINESS_REFRESH_SECONDS
    ):
        raise MacProviderConfigError("launch_agent_readiness_refresh_invalid")
    keep_alive = payload.get("KeepAlive")
    if not isinstance(keep_alive, dict) or keep_alive.get("SuccessfulExit") is not False:
        raise MacProviderConfigError("launch_agent_keepalive_invalid")
    if payload.get("RunAtLoad") is not True or payload.get("Umask") != 0o77:
        raise MacProviderConfigError("launch_agent_safety_policy_invalid")
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True).lower()
    for forbidden in ("bearer ", "api_key", "access_token", "refresh_token", "private_key"):
        if forbidden in serialized:
            raise MacProviderConfigError("launch_agent_secret_material_forbidden")


def launchctl(command: list[str], *, tolerate_missing: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["/bin/launchctl", *command],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MacProviderConfigError("launchctl_operation_failed") from exc
    if completed.returncode and not tolerate_missing:
        raise MacProviderConfigError("launchctl_operation_failed")
    return completed


def json_line(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
