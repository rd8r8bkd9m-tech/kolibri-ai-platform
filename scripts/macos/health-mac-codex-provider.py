#!/usr/bin/env python3
"""Return redacted health evidence for the Mac Codex provider LaunchAgent."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import plistlib
import stat
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mac_codex_provider_common import (  # noqa: E402
    LABEL,
    MAC_CODEX_READINESS_REFRESH_SECONDS,
    MacProviderConfigError,
    MacProviderLayout,
    json_line,
    require_regular_file,
    validate_launch_agent_payload,
    validate_identifier,
)


MAX_HEALTH_BYTES = 1024 * 1024
READINESS_FRESHNESS_GRACE_SECONDS = 60


def readiness_is_fresh(
    checked_at: Any,
    *,
    now: datetime | None = None,
    refresh_seconds: int = MAC_CODEX_READINESS_REFRESH_SECONDS,
) -> bool:
    if not isinstance(checked_at, str) or not checked_at.strip():
        return False
    try:
        observed = datetime.fromisoformat(checked_at.strip().replace("Z", "+00:00"))
    except ValueError:
        return False
    if observed.tzinfo is None:
        return False
    current = now or datetime.now(timezone.utc)
    age = (current.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
    return -READINESS_FRESHNESS_GRACE_SECONDS <= age <= (
        refresh_seconds + READINESS_FRESHNESS_GRACE_SECONDS
    )


def load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise MacProviderConfigError("installed_runtime_module_unloadable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def regular_mode(path: Path) -> int | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return -1
    return stat.S_IMODE(info.st_mode)


def load_installed_contract(layout: MacProviderLayout) -> tuple[dict[str, Any], Path, Path, str]:
    plist_path = require_regular_file(layout.launch_agent, "launch_agent_missing")
    try:
        payload = plistlib.loads(plist_path.read_bytes())
    except (plistlib.InvalidFileException, ValueError) as exc:
        raise MacProviderConfigError("launch_agent_plist_invalid") from exc
    validate_launch_agent_payload(payload)
    environment = payload["EnvironmentVariables"]
    try:
        configured_home = Path(environment["HOME"]).resolve()
    except (OSError, TypeError) as exc:
        raise MacProviderConfigError("launch_agent_home_invalid") from exc
    if configured_home != layout.home:
        raise MacProviderConfigError("launch_agent_not_current_user")
    runtime_dir = require_regular_file(
        Path(environment["PYTHONPATH"]) / "agent_host.py",
        "installed_agent_host_missing",
    ).parent
    mesh_manifest = require_regular_file(
        environment["KOLIBRI_MESH_MEMBERSHIP_MANIFEST"],
        "mesh_manifest_invalid",
    )
    runner_access_path = require_regular_file(
        environment["KOLIBRI_RUNNER_ACCESS_MANIFEST"],
        "runner_access_manifest_invalid",
    )
    if runner_access_path != layout.runner_access.resolve():
        raise MacProviderConfigError("runner_access_path_not_managed")
    if not runtime_dir.is_relative_to(layout.releases.resolve()):
        raise MacProviderConfigError("runtime_path_outside_managed_releases")
    runner_access = load_module(runtime_dir / "runner_access.py", "installed_runner_access")
    try:
        policy = runner_access.load_runner_access_manifest(runner_access_path)
    except Exception as exc:
        raise MacProviderConfigError("runner_access_manifest_invalid") from exc
    if policy["runners"]["codex"].get("mode") != "local_service_account":
        raise MacProviderConfigError("codex_local_service_account_required")
    if policy["runners"]["mimo"].get("mode") != "disabled":
        raise MacProviderConfigError("mimo_must_be_disabled")
    endpoint = load_module(runtime_dir / "control_plane_endpoint.py", "installed_control_plane_endpoint")
    try:
        control_url = endpoint.resolve_home_control_plane_url(manifest_path=mesh_manifest)
    except Exception as exc:
        raise MacProviderConfigError("dynamic_home_resolution_failed") from exc
    return payload, runtime_dir, runner_access_path, control_url


def launch_agent_loaded() -> bool:
    try:
        completed = subprocess.run(
            ["/bin/launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def fetch_node(control_url: str, node_id: str, timeout: int) -> dict[str, Any] | None:
    target = f"{control_url}/v1/nodes/{urllib.parse.quote(node_id, safe='')}?scope=all"
    request = urllib.request.Request(target, method="GET", headers={"Accept": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_HEALTH_BYTES + 1)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError):
        return None
    if len(raw) > MAX_HEALTH_BYTES:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-id", default="mac-codex-provider")
    parser.add_argument("--timeout", type=int, default=5)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    node_id = validate_identifier(args.node_id, "node_id")
    if not 1 <= args.timeout <= 30:
        raise MacProviderConfigError("health_timeout_invalid")
    layout = MacProviderLayout.from_home(Path.home())
    _payload, runtime_dir, runner_access_path, control_url = load_installed_contract(layout)
    log_modes = {
        "sanitized": regular_mode(layout.sanitized_log),
        "bootstrap": regular_mode(layout.bootstrap_log),
    }
    log_permissions_safe = all(mode == 0o600 for mode in log_modes.values())
    credential_mode = regular_mode(layout.provider_credential)
    credential_permissions_safe = credential_mode == 0o600
    evidence: dict[str, Any] = {
        "schema_version": "kolibri.mac-codex-provider-health.v1",
        "status": "validated",
        "node_id": node_id,
        "control_plane_source": "replicated_mesh_manifest",
        "control_plane_url": control_url,
        "runtime_dir": str(runtime_dir),
        "runner_access": str(runner_access_path),
        "log_permissions_safe": log_permissions_safe,
        "credential_permissions_safe": credential_permissions_safe,
        "validate_only": args.validate_only,
    }
    if args.validate_only:
        evidence["passed"] = log_permissions_safe and credential_permissions_safe
        print(json_line(evidence))
        return 0 if evidence["passed"] else 1

    loaded = launch_agent_loaded()
    card = fetch_node(control_url, node_id, args.timeout)
    runners = card.get("runners") if isinstance(card, dict) and isinstance(card.get("runners"), dict) else {}
    codex = runners.get("codex") if isinstance(runners.get("codex"), dict) else {}
    mimo = runners.get("mimo") if isinstance(runners.get("mimo"), dict) else {}
    capabilities = card.get("capabilities") if isinstance(card, dict) and isinstance(card.get("capabilities"), list) else []
    readiness = card.get("runner_readiness") if isinstance(card, dict) and isinstance(card.get("runner_readiness"), dict) else {}
    codex_readiness = readiness.get("codex") if isinstance(readiness.get("codex"), dict) else {}
    codex_probe = codex.get("probe") if isinstance(codex.get("probe"), dict) else {}
    readiness_probe = (
        codex_readiness.get("probe")
        if isinstance(codex_readiness.get("probe"), dict)
        else {}
    )
    observed_codex_model = (
        codex.get("model")
        or codex_probe.get("model")
        or readiness_probe.get("model")
    )
    checks = {
        "launch_agent_loaded": loaded,
        "control_plane_reachable": card is not None,
        "node_identity_matches": isinstance(card, dict) and card.get("node_id") == node_id,
        "codex_available": codex.get("status") == "available",
        "codex_model_pinned": observed_codex_model == "gpt-5.5",
        "codex_capability_advertised": "runner:codex" in capabilities,
        "codex_probe_passed": (
            readiness_probe.get("status") == "passed"
        ),
        "codex_readiness_fresh": readiness_is_fresh(codex_readiness.get("checked_at")),
        "mimo_disabled": mimo.get("status") == "disabled" and "runner:mimo" not in capabilities,
        "log_permissions_safe": log_permissions_safe,
        "credential_permissions_safe": credential_permissions_safe,
    }
    evidence.update({
        "status": "passed" if all(checks.values()) else "failed",
        "passed": all(checks.values()),
        "codex_readiness_refresh_seconds": MAC_CODEX_READINESS_REFRESH_SECONDS,
        "checks": checks,
    })
    print(json_line(evidence))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MacProviderConfigError as exc:
        print(json_line({"status": "failed", "error": exc.code}))
        raise SystemExit(1)
