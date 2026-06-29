#!/usr/bin/env python3
"""Build a read-only supervised rollout packet for Kolibri GoMesh.

The packet is an operator handoff artifact for the next MikroTik rollout
window. It gathers current Home/RouterOS evidence through the Home mesh-agent,
includes exact apply and rollback commands from the generated rollout plan, and
writes JSON plus a short Markdown checklist under .run.

It does not create rollout locks, does not execute RouterOS commands, and does
not change Home or MikroTik routing.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_AGENT_URL = "http://10.99.0.1:8081"
DEFAULT_ENV_FILE = Path("/etc/kolibri/mesh-agent.env")
DEFAULT_OUTPUT_ROOT = Path("/opt/kolibri/repo/.run")
DEFAULT_OBJECTIVE = Path("/opt/kolibri/repo/scripts/kolibri_gomesh_objective_audit.py")
DEFAULT_OPERATOR = Path("/opt/kolibri/repo/scripts/kolibri_gomesh_operator_report.py")
DEFAULT_DOMAIN = "https://kolibriai.ru"


def iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


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


def parse_json_text(value: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        return {"ok": False, "parse_error": str(exc), "raw_prefix": value[:500]}
    return parsed if isinstance(parsed, dict) else {"ok": False, "parse_error": "JSON root is not object"}


def command_summary(result: dict[str, Any], parsed: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = {
        "ok": bool(result.get("ok", result.get("exit_code") == 0)),
        "exit_code": result.get("exit_code"),
        "duration_ms": result.get("duration_ms"),
        "stderr_prefix": str(result.get("stderr", ""))[:240],
    }
    if parsed is not None:
        summary["stdout_json_ok"] = "parse_error" not in parsed
    return summary


def run_local(argv: list[str], timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        result = {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except FileNotFoundError as exc:
        result = {
            "ok": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "exit_code": 124,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": "timeout",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    return result, parse_json_text(str(result.get("stdout", "")))


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


def run_home(agent_url: str, token: str, command: str, timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.monotonic()
    try:
        envelope = request_exec(agent_url, token, command, timeout)
        envelope.setdefault("duration_ms", int((time.monotonic() - started) * 1000))
        envelope["ok"] = int(envelope.get("exit_code", 1)) == 0
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        envelope = {
            "ok": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    return envelope, parse_json_text(str(envelope.get("stdout", "")))


def domain_check(base_url: str, timeout: int) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for path in ("/", "/api/health"):
        url = base_url.rstrip("/") + path
        started = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                body = response.read(600).decode("utf-8", errors="replace")
                status = response.getcode()
                content_type = response.headers.get("content-type", "")
                error = ""
        except Exception as exc:  # noqa: BLE001 - packet should include reason.
            body = ""
            status = 0
            content_type = ""
            error = f"{type(exc).__name__}: {exc}"
        parsed = parse_json_text(body) if path == "/api/health" and body else {}
        checks.append(
            {
                "url": url,
                "http_status": status,
                "ok": status == 200 and (path != "/api/health" or parsed.get("status") == "ok"),
                "content_type": content_type,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "json": parsed if path == "/api/health" else {},
                "error": error,
            }
        )
    return {
        "base_url": base_url,
        "checks": checks,
        "ok": all(item["ok"] for item in checks),
    }


def rollout_plan_command(scope: str, clients: list[str]) -> str:
    command = [
        "/usr/local/sbin/kolibri-gomesh-rollout-plan",
        "--scope",
        scope,
        "--pretty",
    ]
    for client in clients:
        command.extend(["--client", client])
    return " ".join(shlex.quote(item) for item in command)


def extract_plan_steps(plan: dict[str, Any], key: str) -> list[dict[str, Any]]:
    steps = ((plan.get("plan") or {}).get(key) or [])
    return [item for item in steps if isinstance(item, dict)]


def script_command_lines(steps: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("command", "")) for item in steps if item.get("command")]


def unique_commands(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for command in commands:
        if not command or command in seen:
            continue
        seen.add(command)
        result.append(command)
    return result


def open_lock_command(scope: str, ttl_minutes: int) -> str:
    lock_scope = "lan" if scope == "lan" else "next-group"
    command = [
        "/usr/local/sbin/kolibri-gomesh-rollout-window",
        "--pretty",
        "open",
        "--scope",
        lock_scope,
        "--ttl-minutes",
        str(ttl_minutes),
        "--reason",
        f"supervised {scope} rollout",
    ]
    if scope == "lan":
        command.append("--allow-whole-lan")
    return " ".join(shlex.quote(item) for item in command)


def close_lock_command() -> str:
    return "/usr/local/sbin/kolibri-gomesh-rollout-window --pretty close --reason supervised-rollout-finished"


def post_apply_routeros_live_audit_command(scope: str) -> str:
    expected_scope = "lan" if scope == "lan" else "stable-canaries"
    return f"/usr/local/sbin/kolibri-gomesh-routeros-live-audit --expected-scope {expected_scope} --pretty"


def post_rollout_verify_command(scope: str) -> str:
    return f"python3 /opt/kolibri/repo/scripts/kolibri_gomesh_post_rollout_verify.py --scope {scope} --pretty"


def build_markdown(packet: dict[str, Any]) -> str:
    scope = packet["scope"]
    plan = packet["rollout_plan"]
    preflight = packet["preflight_summary"]
    routeros = packet["routeros_live"]
    objective = packet["objective_summary"]
    apply_commands = script_command_lines(extract_plan_steps(plan, "apply_steps"))
    rollback_commands = script_command_lines(extract_plan_steps(plan, "rollback_steps"))
    verify_commands = unique_commands([
        packet["operator_commands"]["post_apply_routeros_live_audit"],
        *script_command_lines(extract_plan_steps(plan, "verify_steps")),
    ])
    domain = packet["domain"]

    def block(commands: list[str]) -> str:
        if not commands:
            return "```text\n(no commands)\n```"
        return "```text\n" + "\n".join(commands) + "\n```"

    lines = [
        f"# Kolibri GoMesh supervised rollout packet: {scope}",
        "",
        f"Generated: `{packet['timestamp_utc']}`",
        f"Live changes made by packet: `{str(packet['live_changes_made_by_packet']).lower()}`",
        "",
        "## Current gates",
        "",
        f"- Objective complete: `{str(objective.get('objective_complete')).lower()}`",
        f"- Ready for supervised next group: `{str(objective.get('ready_for_supervised_next_group')).lower()}`",
        f"- Ready for whole LAN: `{str(objective.get('ready_for_whole_lan')).lower()}`",
        f"- RouterOS live config verified: `{str(routeros.get('live_config_verified')).lower()}`",
        f"- RouterOS API login OK: `{str(routeros.get('api_login_ok')).lower()}`",
        f"- Current endpoint: `{preflight.get('current_endpoint')}`",
        f"- Current health: `{preflight.get('current_health')}`",
        f"- Rollout lock present: `{str((preflight.get('locks', {}).get('rollout', {}) or {}).get('present')).lower()}`",
        f"- Domain OK: `{str(domain.get('ok')).lower()}`",
        "",
        "## Window commands",
        "",
        "Open the lock only when the operator is watching real clients:",
        "",
        block([packet["operator_commands"]["open_lock"]]),
        "",
        "Close the lock immediately after apply, verification, or rollback:",
        "",
        block([packet["operator_commands"]["close_lock"]]),
        "",
        "## Apply in WinBox Terminal",
        "",
        block(apply_commands),
        "",
        "## Verify",
        "",
        block(verify_commands),
        "",
        "Manual client checks after apply:",
        "",
        "- DNS resolves normally on the real client.",
        "- YouTube opens on the real client.",
        "- Xiaomi MiMo opens where required.",
        "- External IP matches the selected Kolibri exit.",
        "",
        "Run the post-rollout verifier from the primary server immediately after apply:",
        "",
        block([packet["operator_commands"]["post_rollout_verify"]]),
        "",
        "If the verifier returns `ROLLBACK_REQUIRED`, run rollback before continuing.",
        "",
        "## Rollback",
        "",
        "Run rollback first if any client loses DNS or internet access:",
        "",
        block(rollback_commands),
        "",
    ]
    return "\n".join(lines)


def write_outputs(output_root: Path, packet: dict[str, Any], markdown: str) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_dir = output_root / f"gomesh-supervised-rollout-packet-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    output_dir.mkdir(parents=True, exist_ok=False)
    packet["evidence_dir"] = str(output_dir)
    packet_json = json.dumps(packet, ensure_ascii=False, indent=2) + "\n"
    (output_dir / "packet.json").write_text(packet_json, encoding="utf-8")
    (output_dir / "packet.md").write_text(markdown, encoding="utf-8")
    (output_root / "gomesh-supervised-rollout-packet-latest.json").write_text(packet_json, encoding="utf-8")
    (output_root / "gomesh-supervised-rollout-packet-latest.md").write_text(markdown, encoding="utf-8")
    (output_root / "gomesh-supervised-rollout-packet-latest-dir").write_text(str(output_dir) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("stable-canaries", "disabled-canaries", "custom", "lan"), default="lan")
    parser.add_argument("--client", action="append", default=[])
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--lock-ttl-minutes", type=int, default=15)
    parser.add_argument("--timeout", type=int, default=320)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    token = load_token(args.env_file)
    commands = {
        "routeros_live": "/usr/local/sbin/kolibri-gomesh-routeros-live-audit --pretty",
        "rollout_window": "/usr/local/sbin/kolibri-gomesh-rollout-window --pretty status",
        "rollout_preflight": "/usr/local/sbin/kolibri-gomesh-rollout-preflight --pretty",
        "rollout_plan": rollout_plan_command(args.scope, args.client),
    }
    home_results: dict[str, dict[str, Any]] = {}
    home_parsed: dict[str, dict[str, Any]] = {}
    for name, command in commands.items():
        timeout = args.timeout if name in {"rollout_preflight", "rollout_plan"} else 120
        result, parsed = run_home(args.agent_url, token, command, timeout=timeout)
        home_results[name] = result
        home_parsed[name] = parsed

    objective_cmd, objective = run_local(["python3", str(DEFAULT_OBJECTIVE), "--pretty"], timeout=120)
    operator_cmd, operator = run_local(["python3", str(DEFAULT_OPERATOR), "--pretty"], timeout=120)
    domain = domain_check(args.domain, timeout=15)

    routeros_access = home_parsed.get("routeros_live", {}).get("access", {}) or {}
    routeros_dump = home_parsed.get("routeros_live", {}).get("dump_audit", {}) or {}
    preflight = home_parsed.get("rollout_preflight", {}).get("rollout", {}) or {}
    rollout_plan = home_parsed.get("rollout_plan", {})
    objective_audit = objective.get("audit", {})
    operator_objective = operator.get("objective", {})
    live_verified = bool(routeros_dump.get("live_config_verified"))
    scope_needs_lock = args.scope in {"lan", "disabled-canaries", "custom"}
    lock = preflight.get("locks", {}).get("rollout", {}) or {}

    blockers: list[str] = []
    if not live_verified:
        blockers.append("RouterOS live config is not verified")
    if not preflight.get("observationally_ready"):
        blockers.append("Home/canary observation is not ready")
    if args.scope == "lan" and objective_audit.get("ready_for_whole_lan"):
        # This should normally stay false until a supervised lock is open.
        pass
    if scope_needs_lock and lock.get("effective_present"):
        blockers.append("rollout lock is already open; verify this is intentional before any apply")
    if args.scope == "custom" and not args.client:
        blockers.append("custom scope requires at least one --client id,ip,label")
    if not domain.get("ok"):
        blockers.append("public kolibriai.ru smoke check failed")

    packet = {
        "timestamp_utc": iso_now(),
        "mode": "read_only_supervised_rollout_packet",
        "scope": args.scope,
        "custom_clients": args.client,
        "live_changes_made_by_packet": False,
        "commands": {
            **{
                name: command_summary(home_results[name], home_parsed[name])
                for name in commands
            },
            "objective": command_summary(objective_cmd, objective),
            "operator": command_summary(operator_cmd, operator),
        },
        "routeros_live": {
            "ok": home_parsed.get("routeros_live", {}).get("ok"),
            "router_host": routeros_access.get("router_host"),
            "tcp_open_ports": [
                item.get("port")
                for item in routeros_access.get("tcp_checks", [])
                if item.get("ok")
            ],
            "api_login_ok": (routeros_access.get("api_probe", {}) or {}).get("login_ok"),
            "api_user": (routeros_access.get("api_probe", {}) or {}).get("user"),
            "manual_live_dump_required": routeros_access.get("manual_live_dump_required"),
            "live_config_verified": live_verified,
        },
        "preflight_summary": {
            "observationally_ready": preflight.get("observationally_ready"),
            "next_group_allowed": preflight.get("next_group_allowed"),
            "whole_lan_allowed": preflight.get("whole_lan_allowed"),
            "current_endpoint": preflight.get("current_endpoint"),
            "current_health": preflight.get("current_health"),
            "safety_blockers": preflight.get("safety_blockers", []),
            "locks": preflight.get("locks", {}),
            "selector_history": preflight.get("selector_history", {}),
        },
        "objective_summary": {
            "objective_complete": objective_audit.get("objective_complete", operator_objective.get("complete")),
            "ready_for_supervised_next_group": objective_audit.get(
                "ready_for_supervised_next_group",
                operator_objective.get("ready_for_supervised_next_group"),
            ),
            "ready_for_whole_lan": objective_audit.get("ready_for_whole_lan", operator_objective.get("ready_for_whole_lan")),
            "remaining_requirements": objective_audit.get("remaining_requirements", operator_objective.get("remaining_requirements", [])),
        },
        "domain": domain,
        "rollout_plan": rollout_plan,
        "operator_commands": {
            "open_lock": open_lock_command(args.scope, args.lock_ttl_minutes),
            "close_lock": close_lock_command(),
            "post_apply_routeros_live_audit": post_apply_routeros_live_audit_command(args.scope),
            "post_rollout_verify": post_rollout_verify_command(args.scope),
        },
        "blockers_for_live_window": blockers,
        "ready_for_supervised_window_packet": not blockers,
        "ok": all(bool(home_results[name].get("ok")) for name in commands)
        and bool(objective_cmd.get("ok"))
        and bool(operator_cmd.get("ok"))
        and bool(rollout_plan.get("ok"))
        and live_verified
        and bool(domain.get("ok")),
    }
    markdown = build_markdown(packet)
    write_outputs(args.output_root, packet, markdown)
    print(json.dumps(packet, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if packet["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
