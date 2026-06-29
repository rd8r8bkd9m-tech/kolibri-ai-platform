#!/usr/bin/env python3
"""Collect read-only Kolibri GoMesh Home evidence through mesh-agent exec.

The collector is intended for a non-Home node that can reach Home's
kolibri-mesh-agent on 10.99.0.1:8081. It runs only a fixed allowlist of
read-only GoMesh commands, stores full command envelopes locally, and prints a
compact summary. It does not create rollout locks, does not call selector
apply, and does not change MikroTik or Home routing.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_AGENT_URL = "http://10.99.0.1:8081"
DEFAULT_ENV_FILE = Path("/etc/kolibri/mesh-agent.env")
DEFAULT_OUTPUT_ROOT = Path("/opt/kolibri/repo/.run")

COMMANDS: dict[str, dict[str, Any]] = {
    "status": {
        "command": "/usr/local/sbin/kolibri-gomesh-status --runtime --pretty",
        "timeout_seconds": 240,
        "required": True,
    },
    "readiness": {
        "command": "/usr/local/sbin/kolibri-gomesh-readiness-audit --pretty",
        "timeout_seconds": 300,
        "required": True,
    },
    "objective": {
        "command": "/usr/local/sbin/kolibri-gomesh-objective-audit --pretty",
        "timeout_seconds": 300,
        "required": True,
    },
    "routeros_live": {
        "command": "/usr/local/sbin/kolibri-gomesh-routeros-live-audit --pretty",
        "timeout_seconds": 120,
        "required": True,
    },
    "dump_status": {
        "command": "/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit status --pretty",
        "timeout_seconds": 60,
        "required": True,
    },
}

OPTIONAL_COMMANDS: dict[str, dict[str, Any]] = {
    "operator": {
        "command": "/usr/local/sbin/kolibri-gomesh-operator-report --pretty",
        "timeout_seconds": 300,
        "required": False,
    },
}


def load_token(env_file: Path) -> str:
    token = os.environ.get("KOLIBRI_MESH_EXEC_TOKEN", "").strip()
    if token:
        return token
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key == "KOLIBRI_MESH_EXEC_TOKEN":
                return value.strip().strip("'\"")
    raise SystemExit("KOLIBRI_MESH_EXEC_TOKEN not found in environment or env file")


def request_exec(agent_url: str, token: str, command: str, timeout_seconds: int) -> dict[str, Any]:
    payload = json.dumps(
        {"command": command, "timeout_seconds": timeout_seconds},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{agent_url.rstrip('/')}/api/exec",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds + 10) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def parse_json_text(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        return {"parse_error": str(exc), "raw_prefix": value[:500]}
    return parsed if isinstance(parsed, dict) else {"parse_error": "JSON root is not object"}


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def write_latest(output_root: Path, output_dir: Path, summary: dict[str, Any]) -> None:
    latest_json = output_root / "gomesh-home-live-latest.json"
    latest_dir = output_root / "gomesh-home-live-latest-dir"
    latest_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_dir.write_text(str(output_dir) + "\n", encoding="utf-8")


def command_summary(envelope: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "exit_code": envelope.get("exit_code"),
        "duration": envelope.get("duration"),
        "stdout_json_ok": "parse_error" not in parsed,
        "stderr_prefix": str(envelope.get("stderr", ""))[:240],
    }


def build_summary(
    output_dir: Path,
    command_specs: dict[str, dict[str, Any]],
    envelopes: dict[str, dict[str, Any]],
    parsed: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status = parsed.get("status", {})
    readiness = parsed.get("readiness", {})
    objective = parsed.get("objective", {})
    routeros = parsed.get("routeros_live", {})
    readiness_body = readiness.get("readiness", {})
    objective_audit = objective.get("audit", {})
    routeros_access = routeros.get("access", {}) or {}
    routeros_dump = routeros.get("dump_audit", {}) or {}
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "read_only_home_mesh_exec_collection",
        "evidence_dir": str(output_dir),
        "live_changes_made": False,
        "commands": {
            name: command_summary(envelopes[name], parsed.get(name, {}))
            for name in command_specs
            if name in envelopes
        },
        "home_runtime": {
            "status_ok": status.get("ok"),
            "active_exit_count": status.get("active_exit_count"),
            "countries": status.get("countries", []),
            "client_service": (status.get("runtime", {}).get("client_service", {}) or {}).get("stdout"),
            "health_timer": (status.get("runtime", {}).get("health_timer", {}) or {}).get("stdout"),
            "service_profile_ok": (status.get("runtime", {}).get("service_profile", {}) or {}).get("ok"),
            "external_ip": (status.get("runtime", {}).get("external_ip", {}) or {}).get("stdout"),
            "target_checks": [
                {
                    "id": item.get("id"),
                    "ok": item.get("ok"),
                    "http_code": item.get("stdout"),
                    "duration_ms": item.get("duration_ms"),
                }
                for item in status.get("runtime", {}).get("target_http_codes", [])
            ],
            "canary_routes": [
                {
                    "id": item.get("id"),
                    "ok": item.get("ok"),
                    "source_ip": item.get("source_ip"),
                    "expected_tun": item.get("expected_tun"),
                    "expected_table": item.get("expected_table"),
                }
                for item in status.get("runtime", {}).get("canary_routes", [])
            ],
        },
        "readiness": {
            "ok": readiness.get("ok"),
            "current_canary_state_ok": readiness_body.get("current_canary_state_ok"),
            "automatic_apply_ready": readiness_body.get("automatic_apply_ready"),
            "whole_lan_rollout_ready": readiness_body.get("whole_lan_rollout_ready"),
            "current_endpoint": readiness_body.get("current_endpoint"),
            "current_health": readiness_body.get("current_health"),
            "service_route_policy_ok": (readiness_body.get("service_route_policy", {}) or {}).get("ok"),
            "active_canary_count": readiness_body.get("active_canary_count"),
            "whole_lan_rollout_blockers": readiness_body.get("whole_lan_rollout_blockers", []),
        },
        "objective": {
            "ok": objective.get("ok"),
            "objective_complete": objective_audit.get("objective_complete"),
            "ready_for_supervised_next_group": objective_audit.get("ready_for_supervised_next_group"),
            "ready_for_whole_lan": objective_audit.get("ready_for_whole_lan"),
            "requirement_statuses": {
                key: value.get("status")
                for key, value in (objective_audit.get("requirements") or {}).items()
                if isinstance(value, dict)
            },
            "remaining_requirements": objective_audit.get("remaining_requirements", []),
        },
        "routeros_live": {
            "ok": routeros.get("ok"),
            "expected_scope": routeros.get("expected_scope"),
            "router_host": routeros_access.get("router_host"),
            "tcp_open_ports": [
                item.get("port")
                for item in routeros_access.get("tcp_checks", [])
                if item.get("ok")
            ],
            "ssh_batch_ok": (routeros_access.get("ssh_batch_probe", {}) or {}).get("ok"),
            "api_login_ok": (routeros_access.get("api_probe", {}) or {}).get("login_ok"),
            "api_bootstrap_bundle_ready": (routeros_access.get("api_bootstrap_bundle", {}) or {}).get("ok"),
            "manual_live_dump_required": routeros_access.get("manual_live_dump_required"),
            "live_config_verified": routeros_dump.get("live_config_verified"),
            "dump_blockers": routeros_dump.get("blockers", []),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--include-operator", action="store_true", help="Also run the slower optional operator report")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    token = load_token(args.env_file)
    output_dir = args.output_root / f"gomesh-home-live-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    output_dir.mkdir(parents=True, exist_ok=False)

    envelopes: dict[str, dict[str, Any]] = {}
    parsed: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    command_specs = dict(COMMANDS)
    if args.include_operator:
        command_specs.update(OPTIONAL_COMMANDS)

    for name, spec in command_specs.items():
        try:
            envelope = request_exec(
                args.agent_url,
                token,
                str(spec["command"]),
                int(spec["timeout_seconds"]),
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            envelope = {
                "exec_id": "",
                "stdout": "",
                "stderr": f"{type(exc).__name__}: {exc}",
                "exit_code": 125,
                "duration": "",
            }
        envelopes[name] = envelope
        stdout = str(envelope.get("stdout", ""))
        stderr = str(envelope.get("stderr", ""))
        write_text(output_dir / f"{name}.exec.json", json.dumps(envelope, ensure_ascii=False, indent=2))
        write_text(output_dir / f"{name}.stdout", stdout)
        write_text(output_dir / f"{name}.stderr", stderr)
        parsed[name] = parse_json_text(stdout)
        if spec.get("required") and envelope.get("exit_code") != 0:
            failures.append(f"{name} exit_code={envelope.get('exit_code')}")

    summary = build_summary(output_dir, command_specs, envelopes, parsed)
    summary["required_failures"] = failures
    summary["ok"] = not failures
    write_text(output_dir / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    write_latest(args.output_root, output_dir, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
