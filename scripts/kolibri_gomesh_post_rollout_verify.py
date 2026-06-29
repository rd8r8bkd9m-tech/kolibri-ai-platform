#!/usr/bin/env python3
"""Read-only post-rollout verifier for Kolibri GoMesh MikroTik changes.

Run this immediately after a supervised MikroTik apply step. It verifies the
expected RouterOS scope, Home health, service route policy, rollout lock state,
optional client route simulations, and public kolibriai.ru health. It emits a
clear verdict:

- PASS: post-apply evidence is consistent with the requested scope.
- ROLLBACK_REQUIRED: run the generated rollback commands before continuing.

The verifier does not create rollout locks, does not execute RouterOS commands,
and does not change Home or MikroTik routing.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_AGENT_URL = "http://10.99.0.1:8081"
DEFAULT_ENV_FILE = Path("/etc/kolibri/mesh-agent.env")
DEFAULT_OUTPUT_ROOT = Path("/opt/kolibri/repo/.run")
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


def parse_key_values(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in value.splitlines():
        key, sep, val = line.partition("=")
        if sep:
            result[key.strip()] = val.strip()
    return result


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
        except Exception as exc:  # noqa: BLE001 - verifier should include reason.
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


def command_summary(envelope: dict[str, Any], parsed: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = {
        "ok": bool(envelope.get("ok")),
        "exit_code": envelope.get("exit_code"),
        "duration_ms": envelope.get("duration_ms"),
        "stderr_prefix": str(envelope.get("stderr", ""))[:240],
    }
    if parsed is not None:
        summary["stdout_json_ok"] = "parse_error" not in parsed
    return summary


def expected_scope(scope: str) -> str:
    return "lan" if scope == "lan" else "stable-canaries"


def rollback_commands(scope: str) -> list[str]:
    if scope == "lan":
        return [
            "/system/script/run kolibri-home-gw-disable-lan",
            "/system/script/run kolibri-home-gw-disable-all",
        ]
    return ["/system/script/run kolibri-home-gw-disable-all"]


def verifier_commands(scope: str, clients: list[str]) -> dict[str, dict[str, Any]]:
    expected = expected_scope(scope)
    commands: dict[str, dict[str, Any]] = {
        "routeros_live": {
            "command": f"/usr/local/sbin/kolibri-gomesh-routeros-live-audit --expected-scope {expected} --pretty",
            "timeout": 120,
        },
        "rollout_window": {
            "command": "/usr/local/sbin/kolibri-gomesh-rollout-window --pretty status",
            "timeout": 30,
        },
        "home_failover": {
            "command": "/usr/local/sbin/kolibri-gomesh-home-failover status",
            "timeout": 30,
        },
        "readiness": {
            "command": "/usr/local/sbin/kolibri-gomesh-readiness-audit --pretty",
            "timeout": 260,
        },
        "service_route": {
            "command": "/usr/local/sbin/kolibri-gomesh-service-route-audit --pretty",
            "timeout": 260,
        },
        "objective": {
            "command": f"/usr/local/sbin/kolibri-gomesh-objective-audit --expected-scope {expected} --pretty",
            "timeout": 180,
        },
    }
    for index, client in enumerate(clients, start=1):
        commands[f"client_{index}"] = {
            "command": f"/usr/local/sbin/kolibri-gomesh-client-verify --client {client} --pretty",
            "timeout": 80,
            "client": client,
        }
    return commands


def evaluate(scope: str, parsed: dict[str, dict[str, Any]], domain: dict[str, Any], require_lock_open: bool) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []

    routeros = parsed.get("routeros_live", {})
    routeros_dump = routeros.get("dump_audit") or {}
    if not bool(routeros.get("ok")) or not bool(routeros_dump.get("live_config_verified")):
        blockers.append("RouterOS live state does not match expected scope")

    failover = parse_key_values(str(parsed.get("home_failover_raw", {}).get("stdout", "")))
    if failover.get("health") != "ok":
        blockers.append("Home failover health is not ok")

    readiness = parsed.get("readiness", {})
    readiness_body = readiness.get("readiness", {}) if isinstance(readiness.get("readiness"), dict) else readiness
    if not bool(readiness_body.get("current_canary_state_ok", readiness_body.get("automatic_apply_ready"))):
        blockers.append("Home readiness is not healthy")

    service = parsed.get("service_route", {})
    if service.get("ok") is False or service.get("blockers"):
        blockers.append("service route policy has blockers")

    window = parsed.get("rollout_window", {})
    lock = (window.get("lock") or {})
    if require_lock_open and not bool(lock.get("effective_present")):
        blockers.append("rollout lock is not open during post-rollout verification")
    if lock.get("expired"):
        blockers.append("rollout lock is expired")

    objective = parsed.get("objective", {})
    objective_audit = objective.get("audit", {})
    if not objective.get("ok"):
        warnings.append("objective audit did not return ok")
    if scope == "lan" and objective_audit.get("objective_complete"):
        warnings.append("objective already reports complete; verify real client evidence was captured")

    client_results = [
        item
        for key, item in parsed.items()
        if key.startswith("client_") and isinstance(item, dict)
    ]
    for item in client_results:
        summary = item.get("summary", {})
        if not (summary.get("ok_currently_routed") or summary.get("ok_for_supervised_apply")):
            blockers.append(f"client verification failed for {item.get('client', {}).get('id')}")

    if not domain.get("ok"):
        blockers.append("public kolibriai.ru health check failed")

    return {
        "verdict": "PASS" if not blockers else "ROLLBACK_REQUIRED",
        "blockers": blockers,
        "warnings": warnings,
        "rollback_commands": rollback_commands(scope),
        "ok": not blockers,
    }


def write_outputs(output_root: Path, result: dict[str, Any]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    output_dir = output_root / f"gomesh-post-rollout-verify-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    output_dir.mkdir(parents=True, exist_ok=False)
    result["evidence_dir"] = str(output_dir)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (output_dir / "post-rollout-verify.json").write_text(payload, encoding="utf-8")
    (output_root / "gomesh-post-rollout-verify-latest.json").write_text(payload, encoding="utf-8")
    (output_root / "gomesh-post-rollout-verify-latest-dir").write_text(str(output_dir) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("stable-canaries", "lan"), default="lan")
    parser.add_argument("--client", action="append", default=[])
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--domain", default=DEFAULT_DOMAIN)
    parser.add_argument("--require-lock-open", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    token = load_token(args.env_file)
    envelopes: dict[str, dict[str, Any]] = {}
    parsed: dict[str, dict[str, Any]] = {}
    for name, spec in verifier_commands(args.scope, args.client).items():
        envelope, body = run_home(args.agent_url, token, str(spec["command"]), timeout=int(spec["timeout"]))
        envelopes[name] = envelope
        parsed[name] = body
        if name == "home_failover":
            parsed["home_failover_raw"] = envelope

    domain = domain_check(args.domain, timeout=15)
    evaluation = evaluate(args.scope, parsed, domain, require_lock_open=args.require_lock_open)
    result = {
        "timestamp_utc": iso_now(),
        "mode": "read_only_post_rollout_verify",
        "scope": args.scope,
        "expected_scope": expected_scope(args.scope),
        "custom_clients": args.client,
        "live_changes_made_by_verifier": False,
        "commands": {
            name: command_summary(envelopes[name], parsed.get(name))
            for name in envelopes
        },
        "routeros_live": {
            "ok": parsed.get("routeros_live", {}).get("ok"),
            "expected_scope": parsed.get("routeros_live", {}).get("expected_scope"),
            "live_config_verified": (parsed.get("routeros_live", {}).get("dump_audit") or {}).get("live_config_verified"),
            "blockers": (parsed.get("routeros_live", {}).get("dump_audit") or {}).get("blockers", []),
        },
        "rollout_window": parsed.get("rollout_window", {}),
        "home_failover": parse_key_values(str(envelopes.get("home_failover", {}).get("stdout", ""))),
        "readiness_summary": parsed.get("readiness", {}).get("readiness", parsed.get("readiness", {})),
        "service_route_summary": {
            "ok": parsed.get("service_route", {}).get("ok"),
            "blockers": parsed.get("service_route", {}).get("blockers", []),
            "action_counts": parsed.get("service_route", {}).get("action_counts", {}),
        },
        "objective_summary": {
            "ok": parsed.get("objective", {}).get("ok"),
            "objective_complete": (parsed.get("objective", {}).get("audit") or {}).get("objective_complete"),
            "ready_for_supervised_next_group": (parsed.get("objective", {}).get("audit") or {}).get("ready_for_supervised_next_group"),
            "ready_for_whole_lan": (parsed.get("objective", {}).get("audit") or {}).get("ready_for_whole_lan"),
            "remaining_requirements": (parsed.get("objective", {}).get("audit") or {}).get("remaining_requirements", []),
        },
        "client_results": {
            name: parsed[name]
            for name in sorted(parsed)
            if name.startswith("client_")
        },
        "domain": domain,
        "evaluation": evaluation,
        "ok": bool(evaluation["ok"]),
    }
    write_outputs(args.output_root, result)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
