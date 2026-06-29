#!/usr/bin/env python3
"""Build a repeatable RouterOS verification package through Home mesh exec.

The package is read-only for MikroTik/Home routing state. It runs a fixed
allowlist of verification commands on Home through kolibri-mesh-agent, stores
full command envelopes under .run, and writes a compact redacted summary.
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
    "bundle_verify": {
        "command": "/usr/local/sbin/kolibri-gomesh-routeros-api-bundle-verify --pretty",
        "timeout_seconds": 60,
        "required": True,
    },
    "routeros_live": {
        "command": "/usr/local/sbin/kolibri-gomesh-routeros-live-audit --pretty",
        "timeout_seconds": 120,
        "required": True,
    },
    "oneshot_create_dry": {
        "command": "/usr/local/sbin/kolibri-gomesh-routeros-api-oneshot-server --mode create --dry-run --pretty",
        "timeout_seconds": 30,
        "required": True,
    },
    "dump_prepare": {
        "command": "/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit prepare --pretty",
        "timeout_seconds": 60,
        "required": True,
    },
    "dump_status": {
        "command": "/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit status --pretty",
        "timeout_seconds": 60,
        "required": True,
    },
    "rollout_preflight": {
        "command": "/usr/local/sbin/kolibri-gomesh-rollout-preflight --pretty",
        "timeout_seconds": 320,
        "required": True,
    },
    "rollout_plan_stable": {
        "command": "/usr/local/sbin/kolibri-gomesh-rollout-plan --scope stable-canaries --pretty",
        "timeout_seconds": 320,
        "required": True,
    },
    "rollout_plan_lan": {
        "command": "/usr/local/sbin/kolibri-gomesh-rollout-plan --scope lan --pretty",
        "timeout_seconds": 320,
        "required": True,
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
        return json.loads(response.read().decode("utf-8"))


def parse_json_text(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        return {"ok": False, "parse_error": str(exc), "raw_prefix": value[:500]}
    return parsed if isinstance(parsed, dict) else {"ok": False, "parse_error": "JSON root is not object"}


def command_summary(envelope: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    return {
        "exit_code": envelope.get("exit_code"),
        "duration": envelope.get("duration"),
        "stdout_json_ok": "parse_error" not in parsed,
        "stderr_prefix": str(envelope.get("stderr", ""))[:240],
    }


def scrub_oneshot(parsed: dict[str, Any], include_sensitive: bool) -> dict[str, Any]:
    plan = dict((parsed.get("plan") or {}))
    if not include_sensitive:
        for key in ("route", "url", "routeros_fetch_import_command"):
            if key in plan:
                plan[key] = "<redacted>"
    return {
        "ok": parsed.get("ok"),
        "serving_started": parsed.get("serving_started"),
        "plan": {
            "mode": plan.get("mode"),
            "bind": plan.get("bind"),
            "port": plan.get("port"),
            "ttl_seconds": plan.get("ttl_seconds"),
            "source_file": plan.get("source_file"),
            "route": plan.get("route"),
            "url": plan.get("url"),
            "dst_path": plan.get("dst_path"),
            "routeros_fetch_import_command": plan.get("routeros_fetch_import_command"),
            "live_changes_made_by_helper": plan.get("live_changes_made_by_helper"),
        },
    }


def rollout_summary(parsed: dict[str, Any]) -> dict[str, Any]:
    plan = parsed.get("plan") or {}
    apply_steps = plan.get("apply_steps") or []
    verify_steps = plan.get("verify_steps") or []
    rollback_steps = plan.get("rollback_steps") or []
    return {
        "ok": parsed.get("ok"),
        "scope": parsed.get("scope") or plan.get("scope"),
        "preflight_summary": parsed.get("preflight_summary", {}),
        "apply_step_count": len(apply_steps),
        "verify_step_count": len(verify_steps),
        "rollback_step_count": len(rollback_steps),
        "apply_commands": [item.get("command") for item in apply_steps if isinstance(item, dict)],
        "rollback_commands": [item.get("command") for item in rollback_steps if isinstance(item, dict)],
        "safety_notes": parsed.get("safety_notes", []),
    }


def build_summary(
    output_dir: Path,
    command_specs: dict[str, dict[str, Any]],
    envelopes: dict[str, dict[str, Any]],
    parsed: dict[str, dict[str, Any]],
    include_sensitive: bool,
) -> dict[str, Any]:
    bundle = parsed.get("bundle_verify", {})
    routeros = parsed.get("routeros_live", {})
    routeros_access = routeros.get("access", {}) or {}
    routeros_dump = routeros.get("dump_audit", {}) or {}
    dump_status = parsed.get("dump_status", {})
    commands_file = dump_status.get("commands_file", {}) or {}
    dump_file = dump_status.get("dump_file", {}) or {}
    preflight = parsed.get("rollout_preflight", {})
    rollout = preflight.get("rollout", {}) or {}
    return {
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "read_only_routeros_verification_package",
        "evidence_dir": str(output_dir),
        "live_changes_made_by_package": False,
        "commands": {
            name: command_summary(envelopes[name], parsed.get(name, {}))
            for name in command_specs
            if name in envelopes
        },
        "api_bundle": {
            "ok": bundle.get("ok"),
            "live_changes_made": bundle.get("live_changes_made"),
            "password_printed": (bundle.get("checks", {}) or {}).get("password_printed"),
            "password_matches_create_command": (bundle.get("checks", {}) or {}).get("password_matches_create_command"),
            "password_file_mode": (bundle.get("files", {}) or {}).get("password_file", {}).get("mode"),
            "create_command_file_mode": (bundle.get("files", {}) or {}).get("create_command_file", {}).get("mode"),
            "remove_command_file_mode": (bundle.get("files", {}) or {}).get("remove_command_file", {}).get("mode"),
            "blocker_count": len(bundle.get("blockers", [])),
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
            "api_login_ok": (routeros_access.get("api_probe", {}) or {}).get("login_ok"),
            "api_user": (routeros_access.get("api_probe", {}) or {}).get("user"),
            "ssh_batch_ok": (routeros_access.get("ssh_batch_probe", {}) or {}).get("ok"),
            "manual_live_dump_required": routeros_access.get("manual_live_dump_required"),
            "live_config_verified": routeros_dump.get("live_config_verified"),
            "dump_blockers": routeros_dump.get("blockers", []),
        },
        "oneshot_create_dry": scrub_oneshot(parsed.get("oneshot_create_dry", {}), include_sensitive),
        "dump_kit": {
            "prepare_ok": parsed.get("dump_prepare", {}).get("ok"),
            "status_ok": dump_status.get("ok"),
            "commands_file_exists": commands_file.get("exists"),
            "commands_file_path": commands_file.get("path"),
            "dump_file_exists": dump_file.get("exists"),
            "dump_file_path": dump_file.get("path"),
        },
        "rollout_preflight": {
            "ok": preflight.get("ok"),
            "observationally_ready": rollout.get("observationally_ready"),
            "next_group_allowed": rollout.get("next_group_allowed"),
            "whole_lan_allowed": rollout.get("whole_lan_allowed"),
            "current_endpoint": rollout.get("current_endpoint"),
            "current_health": rollout.get("current_health"),
            "safety_blockers": rollout.get("safety_blockers", []),
            "locks": rollout.get("locks", {}),
        },
        "rollout_plans": {
            "stable_canaries": rollout_summary(parsed.get("rollout_plan_stable", {})),
            "lan": rollout_summary(parsed.get("rollout_plan_lan", {})),
        },
    }


def write_text(path: Path, value: str) -> None:
    path.write_text(value, encoding="utf-8")


def write_latest(output_root: Path, output_dir: Path, full: dict[str, Any], summary: dict[str, Any]) -> None:
    (output_root / "gomesh-routeros-verification-package-latest.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_root / "gomesh-routeros-verification-package-summary-latest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_root / "gomesh-routeros-verification-package-latest-dir").write_text(str(output_dir) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--include-sensitive-fetch-command", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    token = load_token(args.env_file)
    output_dir = args.output_root / f"gomesh-routeros-verification-package-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    output_dir.mkdir(parents=True, exist_ok=False)

    envelopes: dict[str, dict[str, Any]] = {}
    parsed: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    for name, spec in COMMANDS.items():
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

    summary = build_summary(output_dir, COMMANDS, envelopes, parsed, args.include_sensitive_fetch_command)
    routeros_summary = summary["routeros_live"]
    summary["required_failures"] = failures
    summary["ok"] = (
        not failures
        and bool(summary["api_bundle"]["ok"])
        and bool(routeros_summary["ok"])
        and bool(routeros_summary["api_login_ok"])
        and bool(routeros_summary["live_config_verified"])
    )
    full = {
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "read_only_routeros_verification_package_full",
        "evidence_dir": str(output_dir),
        "live_changes_made_by_package": False,
        "commands": envelopes,
        "parsed": parsed,
        "summary": summary,
    }
    write_text(output_dir / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2))
    write_text(output_dir / "full.json", json.dumps(full, ensure_ascii=False, indent=2))
    write_latest(args.output_root, output_dir, full, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
