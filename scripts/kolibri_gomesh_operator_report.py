#!/usr/bin/env python3
"""Operator handoff report for the Kolibri GoMesh home gateway rollout."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OBJECTIVE = Path("/usr/local/sbin/kolibri-gomesh-objective-audit")
DEFAULT_LIVE_AUDIT = Path("/usr/local/sbin/kolibri-gomesh-routeros-live-audit")
DEFAULT_ROLLOUT_PREFLIGHT = Path("/usr/local/sbin/kolibri-gomesh-rollout-preflight")
DEFAULT_ROLLOUT_WINDOW = Path("/usr/local/sbin/kolibri-gomesh-rollout-window")
DEFAULT_DUMP_KIT = Path("/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit")
DEFAULT_BUNDLE_VERIFY = Path("/usr/local/sbin/kolibri-gomesh-routeros-api-bundle-verify")
DEFAULT_MANIFEST = Path("/etc/kolibri-gomesh/exits.json")
REPO_MANIFEST = Path("/opt/kolibri/repo/ops/kolibri-gomesh-exits.json")
REPO_RUN_DIR = Path("/opt/kolibri/repo/.run")
DEFAULT_HOME_LIVE_SUMMARY = REPO_RUN_DIR / "gomesh-home-live-latest.json"
DEFAULT_ROUTEROS_PACKAGE_SUMMARY = REPO_RUN_DIR / "gomesh-routeros-verification-package-summary-latest.json"


def run(argv: list[str], timeout: int) -> dict[str, Any]:
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
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "exit_code": 124,
            "stdout": (exc.stdout or "").strip() if isinstance(exc.stdout, str) else "",
            "stderr": "timeout",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }


def skipped(reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "exit_code": 0,
        "stdout": "",
        "stderr": reason,
        "duration_ms": 0,
        "skipped": True,
    }


def parse_json(stdout: str) -> dict[str, Any]:
    if not stdout:
        return {}
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "parse_error": str(exc), "raw_stdout_prefix": stdout[:500]}
    return value if isinstance(value, dict) else {"ok": False, "parse_error": "JSON root is not object"}


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def command_json(argv: list[str], timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    result = run(argv, timeout=timeout)
    return result, parse_json(result["stdout"])


def command_summary(result: dict[str, Any]) -> dict[str, Any]:
    summary = {key: result[key] for key in ("ok", "exit_code", "duration_ms", "stderr")}
    if "skipped" in result:
        summary["skipped"] = result["skipped"]
    return summary


def load_manifest(path: Path) -> dict[str, Any]:
    actual = path if path.exists() else REPO_MANIFEST
    if not actual.exists():
        return {}
    manifest = json.loads(actual.read_text())
    manifest["_loaded_from"] = str(actual)
    return manifest


def resolve_tool(path: Path, repo_name: str) -> Path:
    if path.exists():
        return path
    repo_path = SCRIPT_DIR / repo_name
    return repo_path if repo_path.exists() else path


def detect_node_context(manifest: dict[str, Any], objective: dict[str, Any]) -> dict[str, Any]:
    audit_context = (objective.get("audit") or {}).get("node_context")
    if isinstance(audit_context, dict) and audit_context.get("role"):
        return audit_context

    home = manifest.get("home_gateway", {})
    hostname = socket.gethostname()
    addresses_result = run(["hostname", "-I"], timeout=5)
    addresses = addresses_result["stdout"].split() if addresses_result["ok"] else []
    client_tun = str(home.get("client_tun", "kgmhome0"))
    home_matches = {
        "hostname": bool(home.get("hostname") and hostname == home.get("hostname")),
        "lan_ip": bool(home.get("lan_ip") and home.get("lan_ip") in addresses),
        "mesh_ip": bool(home.get("mesh_ip") and home.get("mesh_ip") in addresses),
        "client_tun": Path("/sys/class/net", client_tun).exists(),
    }
    role = "home" if any(home_matches.values()) else "non-home"
    return {
        "role": role,
        "auto_role": role,
        "hostname": hostname,
        "addresses": addresses,
        "home_matches": home_matches,
        "home_runtime_checks_local": role == "home",
    }


def completion_percent(objective: dict[str, Any]) -> int:
    audit = objective.get("audit", {})
    statuses = {
        key: value.get("status")
        for key, value in (audit.get("requirements") or {}).items()
        if isinstance(value, dict)
    }
    if not statuses:
        return 0
    weights = {
        "documented_architecture": 10,
        "controlled_country_exits": 15,
        "home_dataplane_gateway": 15,
        "mikrotik_central_gateway_profile": 10,
        "mikrotik_live_state": 15,
        "service_access_policy": 10,
        "canary_clients_routed": 10,
        "rollout_gate": 5,
        "whole_lan_or_all_home_clients": 10,
    }
    score = 0
    total = 0
    for key, weight in weights.items():
        total += weight
        status = statuses.get(key)
        if status == "passed":
            score += weight
        elif status == "staged":
            score += int(weight * 0.7)
    return int(round((score / total) * 100)) if total else 0


def requirement_statuses(objective: dict[str, Any]) -> dict[str, str]:
    audit = objective.get("audit") or {}
    statuses = {
        key: value.get("status")
        for key, value in (audit.get("requirements") or {}).items()
        if isinstance(value, dict)
    }
    return {key: value for key, value in statuses.items() if isinstance(value, str)}


def expand_routeros_live_summary(summary: dict[str, Any], api_bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    if not summary:
        return {}
    api_bundle = api_bundle or {}
    tcp_ports = summary.get("tcp_open_ports") or []
    return {
        "access": {
            "router_host": summary.get("router_host"),
            "tcp_checks": [{"port": port, "ok": True} for port in tcp_ports],
            "ssh_batch_probe": {"ok": summary.get("ssh_batch_ok")},
            "api_probe": {
                "login_ok": summary.get("api_login_ok"),
                "user": summary.get("api_user"),
            },
            "api_bootstrap_bundle": {
                "ok": summary.get("api_bootstrap_bundle_ready", api_bundle.get("ok")),
                "summary": api_bundle,
            },
            "manual_live_dump_required": summary.get("manual_live_dump_required"),
        },
        "dump_audit": {
            "live_config_verified": summary.get("live_config_verified"),
            "blockers": summary.get("dump_blockers", []),
        },
        "expected_scope": summary.get("expected_scope"),
    }


def build_next_actions(
    objective: dict[str, Any],
    live: dict[str, Any],
    dump_status: dict[str, Any],
    rollout_window: dict[str, Any],
    rollout_preflight: dict[str, Any] | None = None,
) -> list[str]:
    actions: list[str] = []
    statuses = requirement_statuses(objective)
    objective_audit = objective.get("audit") or {}
    rollout_preflight = rollout_preflight or {}
    live_access = live.get("access", {})
    live_verified = bool((live.get("dump_audit") or {}).get("live_config_verified")) or (
        bool((live_access.get("api_probe") or {}).get("login_ok"))
        and live_access.get("manual_live_dump_required") is False
    )
    if statuses.get("mikrotik_live_state") == "passed":
        live_verified = True

    if not live:
        if (
            statuses.get("home_dataplane_gateway") == "passed"
            and statuses.get("service_access_policy") == "passed"
            and statuses.get("canary_clients_routed") == "passed"
            and statuses.get("mikrotik_live_state") == "unverified"
        ):
            actions.append("Home dataplane and canaries are verified; close the remaining RouterOS live gate by importing the prepared read-only API user or by providing a WinBox dump.")
            actions.append("Use verification_handoff.routeros_api_path or verification_handoff.routeros_manual_dump_path; keep rollout window closed until that audit is green.")
            return actions
        actions.append("Run kolibri-gomesh-operator-report on Home, or provide a RouterOS live dump, to verify Home/MikroTik runtime state.")
        actions.append("Do not open the rollout window from a non-Home node.")
        return actions

    if live_verified:
        lock = rollout_window.get("lock", {})
        if lock.get("effective_present"):
            actions.append("A rollout window is open; close it immediately after apply, verification, or rollback.")
        if (
            statuses.get("whole_lan_or_all_home_clients") == "incomplete"
            and objective_audit.get("ready_for_supervised_next_group")
        ):
            actions.append("Choose the next named client group, or explicitly approve a supervised whole-LAN window.")
            actions.append("For that window only, create /etc/kolibri-gomesh/allow-lan-rollout, apply the generated MikroTik plan, verify DNS/YouTube/Xiaomi MiMo/external IP from real clients, then remove the lock.")
            return actions
        if not objective_audit.get("objective_complete"):
            actions.append("MikroTik live verification is green; finish the remaining rollout requirements from objective.remaining_requirements.")
            return actions

    api = live_access.get("api_probe", {})
    bundle = live_access.get("api_bootstrap_bundle", {})
    if not api.get("login_ok"):
        if bundle.get("ok"):
            actions.append("Import the prepared read-only RouterOS API user in WinBox, then rerun kolibri-gomesh-routeros-live-audit --pretty.")
        actions.append("Alternative: paste winbox-dump-commands.txt output into latest-routeros-live-dump.txt and run kolibri-gomesh-routeros-live-dump-kit verify --pretty.")
    if live_access.get("manual_live_dump_required") and not dump_status.get("dump_file", {}).get("exists"):
        actions.append("Manual dump file is still missing on Home.")
    lock = rollout_window.get("lock", {})
    if lock.get("effective_present"):
        actions.append("A rollout window is open; close it after apply or rollback.")
    else:
        actions.append("Keep rollout window closed until live MikroTik verification passes.")
    return actions


def routeros_dump_commands(manifest: dict[str, Any]) -> list[str]:
    mikrotik = manifest.get("mikrotik_gateway", {})
    status_script = mikrotik.get("scripts", {}).get("status", "kolibri-home-gw-status")
    return [
        f"/system/script/run {status_script}",
        '/routing/table/print detail where name="kolibri-home-gw"',
        '/ip/route/print detail where comment~"Kolibri Home gateway" or routing-table="kolibri-home-gw"',
        '/routing/rule/print detail where comment~"Kolibri Home gateway"',
        '/ip/firewall/nat/print detail where comment~"Kolibri DNS redirect"',
        '/system/script/print detail where name~"kolibri-home-gw"',
        '/system/scheduler/print detail where name~"kolibri-home-gw"',
        "/ip/dns/print",
    ]


def verification_handoff(manifest: dict[str, Any], node_context: dict[str, Any]) -> dict[str, Any]:
    home = manifest.get("home_gateway", {})
    mikrotik = manifest.get("mikrotik_gateway", {})
    return {
        "purpose": "Collect the missing Home and MikroTik live evidence without changing routes.",
        "current_node_can_verify_home_runtime": bool(node_context.get("home_runtime_checks_local")),
        "home": {
            "hostname": home.get("hostname"),
            "lan_ip": home.get("lan_ip"),
            "mesh_ip": home.get("mesh_ip"),
            "run_read_only_commands": [
                "/usr/local/sbin/kolibri-gomesh-status --runtime --pretty",
                "/usr/local/sbin/kolibri-gomesh-readiness-audit --pretty",
                "/usr/local/sbin/kolibri-gomesh-objective-audit --pretty",
                "/usr/local/sbin/kolibri-gomesh-operator-report --pretty",
            ],
        },
        "routeros_api_path": {
            "purpose": "Preferred once the prepared read-only RouterOS user is imported in WinBox.",
            "commands_on_home": [
                "/usr/local/sbin/kolibri-gomesh-routeros-api-bundle-verify --pretty",
                "/usr/local/sbin/kolibri-gomesh-routeros-api-oneshot-server --mode create --ttl-seconds 300 --pretty",
                "/usr/local/sbin/kolibri-gomesh-routeros-live-audit --pretty",
            ],
            "winbox_action": (
                "Paste the fetch/import command printed by the one-shot server into WinBox Terminal; "
                "the helper itself makes no RouterOS changes until that command is imported."
            ),
        },
        "routeros_manual_dump_path": {
            "purpose": "Fallback when RouterOS API/SSH is unavailable.",
            "commands_on_home_before_winbox": [
                "/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit prepare --pretty",
                "/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit status --pretty",
            ],
            "winbox_read_only_commands": routeros_dump_commands(manifest),
            "save_combined_output_to": "/etc/kolibri-gomesh/routeros-live-dump/latest-routeros-live-dump.txt",
            "commands_on_home_after_winbox": [
                "/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit verify --dump /etc/kolibri-gomesh/routeros-live-dump/latest-routeros-live-dump.txt --pretty",
                "/usr/local/sbin/kolibri-gomesh-routeros-live-audit --dump /etc/kolibri-gomesh/routeros-live-dump/latest-routeros-live-dump.txt --pretty",
            ],
        },
        "rollout_guardrails": [
            "Do not create /etc/kolibri-gomesh/allow-lan-rollout until Home runtime and RouterOS live audit are green.",
            "Do not create /etc/kolibri-gomesh/allow-selector-apply during client routing rollout.",
            "Keep MikroTik PPPoE/default internet path unchanged until one supervised client group is verified.",
        ],
        "expected_routeros": {
            "model": mikrotik.get("model"),
            "lan_ip": mikrotik.get("lan_ip"),
            "policy_table": mikrotik.get("policy_table"),
            "home_next_hop": mikrotik.get("home_next_hop"),
            "active_canary_count": len(mikrotik.get("active_canaries", [])),
            "disabled_rollout": mikrotik.get("disabled_rollout", {}).get("id"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--objective", type=Path, default=DEFAULT_OBJECTIVE)
    parser.add_argument("--live-audit", type=Path, default=DEFAULT_LIVE_AUDIT)
    parser.add_argument("--rollout-preflight", type=Path, default=DEFAULT_ROLLOUT_PREFLIGHT)
    parser.add_argument("--rollout-window", type=Path, default=DEFAULT_ROLLOUT_WINDOW)
    parser.add_argument("--dump-kit", type=Path, default=DEFAULT_DUMP_KIT)
    parser.add_argument("--bundle-verify", type=Path, default=DEFAULT_BUNDLE_VERIFY)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    objective_path = resolve_tool(args.objective, "kolibri_gomesh_objective_audit.py")
    live_path = resolve_tool(args.live_audit, "kolibri_gomesh_routeros_live_audit.py")
    rollout_preflight_path = resolve_tool(args.rollout_preflight, "kolibri_gomesh_rollout_preflight.py")
    rollout_window_path = resolve_tool(args.rollout_window, "kolibri_gomesh_rollout_window.py")
    dump_kit_path = resolve_tool(args.dump_kit, "kolibri_gomesh_routeros_live_dump_kit.py")
    bundle_verify_path = resolve_tool(args.bundle_verify, "kolibri_gomesh_routeros_api_bundle_verify.py")
    manifest = load_manifest(args.manifest)
    home_live_summary = load_json_file(DEFAULT_HOME_LIVE_SUMMARY)
    routeros_package_summary = load_json_file(DEFAULT_ROUTEROS_PACKAGE_SUMMARY)

    manifest_path = Path(str(manifest.get("_loaded_from", args.manifest)))
    objective_argv = [str(objective_path)]
    if manifest_path.exists():
        objective_argv.extend(["--manifest", str(manifest_path)])
    objective_cmd, objective = command_json(objective_argv, timeout=args.timeout)
    node_context = detect_node_context(manifest, objective)
    if node_context.get("role") == "home":
        live_cmd, live = command_json([str(live_path), "--manifest", str(manifest_path)], timeout=min(args.timeout, 120))
        rollout_cmd, rollout = command_json([str(rollout_preflight_path), "--manifest", str(manifest_path)], timeout=args.timeout)
        window_cmd, window = command_json([str(rollout_window_path), "status"], timeout=60)
        dump_cmd, dump = command_json([str(dump_kit_path), "status"], timeout=60)
        bundle_cmd, bundle = command_json([str(bundle_verify_path)], timeout=60)
    else:
        reason = "skipped: Home runtime and RouterOS live commands must run on Home or from a manual RouterOS dump"
        live_cmd = skipped(reason)
        rollout_cmd = skipped(reason)
        window_cmd = skipped(reason)
        dump_cmd = skipped(reason)
        bundle_cmd = skipped(reason)
        live = {}
        rollout = {}
        window = {}
        dump = {}
        bundle = {}

    objective_audit = objective.get("audit", {})
    package_routeros_live = routeros_package_summary.get("routeros_live", {})
    package_api_bundle = routeros_package_summary.get("api_bundle", {})
    home_routeros_live = home_live_summary.get("routeros_live", {})
    effective_live = live or expand_routeros_live_summary(package_routeros_live, package_api_bundle)
    if not effective_live:
        effective_live = expand_routeros_live_summary(home_routeros_live, package_api_bundle)

    package_rollout = routeros_package_summary.get("rollout_preflight", {})
    home_readiness = home_live_summary.get("readiness", {})
    if rollout:
        rollout_body = rollout.get("rollout", rollout)
    elif package_rollout:
        rollout_body = package_rollout
    elif home_readiness:
        rollout_body = {
            "current_endpoint": home_readiness.get("current_endpoint"),
            "current_health": home_readiness.get("current_health"),
            "active_canary_count": home_readiness.get("active_canary_count"),
            "service_route_policy_ok": home_readiness.get("service_route_policy_ok"),
            "observationally_ready": home_readiness.get("current_canary_state_ok"),
            "next_group_allowed": home_readiness.get("automatic_apply_ready"),
            "whole_lan_allowed": home_readiness.get("whole_lan_rollout_ready"),
            "whole_lan_blockers": home_readiness.get("whole_lan_rollout_blockers", []),
        }
    else:
        rollout_body = {}
    if home_readiness:
        for key in ("active_canary_count", "service_route_policy_ok"):
            if rollout_body.get(key) is None:
                rollout_body[key] = home_readiness.get(key)
        if rollout_body.get("whole_lan_blockers") is None:
            rollout_body["whole_lan_blockers"] = home_readiness.get("whole_lan_rollout_blockers", [])
    if package_rollout and rollout_body.get("next_group_blockers") is None:
        rollout_body["next_group_blockers"] = package_rollout.get("safety_blockers", [])
    if package_rollout and rollout_body.get("whole_lan_blockers") is None:
        rollout_body["whole_lan_blockers"] = package_rollout.get("safety_blockers", [])

    if window:
        effective_window = window
    elif package_rollout.get("locks"):
        effective_window = {"lock": (package_rollout.get("locks") or {}).get("rollout", {})}
    else:
        effective_window = {}

    package_dump = routeros_package_summary.get("dump_kit", {})
    if dump:
        effective_dump = dump
    elif package_dump:
        effective_dump = {
            "commands_file": {
                "exists": package_dump.get("commands_file_exists"),
                "path": package_dump.get("commands_file_path"),
            },
            "dump_file": {
                "exists": package_dump.get("dump_file_exists"),
                "path": package_dump.get("dump_file_path"),
            },
        }
    else:
        effective_dump = {}

    if bundle:
        effective_bundle = bundle
    elif package_api_bundle:
        effective_bundle = {
            "ok": package_api_bundle.get("ok"),
            "checks": {
                "password_printed": package_api_bundle.get("password_printed"),
                "password_matches_create_command": package_api_bundle.get("password_matches_create_command"),
            },
            "blockers": package_api_bundle.get("blockers", []),
        }
    else:
        effective_bundle = {}

    live_access = effective_live.get("access", {})
    report = {
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "read_only_operator_handoff_report",
        "node_context": node_context,
        "evidence_sources": {
            "home_live_summary": str(DEFAULT_HOME_LIVE_SUMMARY) if home_live_summary else None,
            "routeros_verification_package_summary": str(DEFAULT_ROUTEROS_PACKAGE_SUMMARY)
            if routeros_package_summary
            else None,
        },
        "commands": {
            "objective": command_summary(objective_cmd),
            "live_audit": command_summary(live_cmd),
            "rollout_preflight": command_summary(rollout_cmd),
            "rollout_window": command_summary(window_cmd),
            "dump_kit": command_summary(dump_cmd),
            "bundle_verify": command_summary(bundle_cmd),
        },
        "completion_percent_estimate": completion_percent(objective),
        "objective": {
            "complete": bool(objective_audit.get("objective_complete")),
            "ready_for_supervised_next_group": bool(objective_audit.get("ready_for_supervised_next_group")),
            "ready_for_whole_lan": bool(objective_audit.get("ready_for_whole_lan")),
            "requirement_statuses": {
                key: value.get("status")
                for key, value in (objective_audit.get("requirements") or {}).items()
                if isinstance(value, dict)
            },
            "remaining_requirements": objective_audit.get("remaining_requirements", []),
        },
        "mikrotik_live_gate": {
            "expected_scope": effective_live.get("expected_scope"),
            "router_host": live_access.get("router_host"),
            "tcp_open_ports": [item.get("port") for item in live_access.get("tcp_checks", []) if item.get("ok")],
            "ssh_batch_ok": live_access.get("ssh_batch_probe", {}).get("ok"),
            "api_login_ok": live_access.get("api_probe", {}).get("login_ok"),
            "api_bootstrap_bundle_ready": live_access.get("api_bootstrap_bundle", {}).get("ok"),
            "api_bootstrap_bundle_summary": live_access.get("api_bootstrap_bundle", {}).get("summary", {}),
            "manual_live_dump_required": live_access.get("manual_live_dump_required"),
            "live_config_verified": bool((effective_live.get("dump_audit") or {}).get("live_config_verified")),
        },
        "home_runtime": {
            "primary_endpoint": manifest.get("home_gateway", {}).get("failover", {}).get("primary_endpoint"),
            "current_endpoint": rollout_body.get("current_endpoint"),
            "current_health": rollout_body.get("current_health"),
            "active_canary_count": rollout_body.get("active_canary_count"),
            "service_route_policy_ok": rollout_body.get("service_route_policy_ok"),
            "observationally_ready": rollout_body.get("observationally_ready"),
        },
        "rollout_gate": {
            "next_group_allowed": rollout_body.get("next_group_allowed"),
            "next_group_blockers": rollout_body.get("next_group_blockers", []),
            "whole_lan_allowed": rollout_body.get("whole_lan_allowed"),
            "whole_lan_blockers": rollout_body.get("whole_lan_blockers", []),
            "rollout_lock": effective_window.get("lock", {}),
        },
        "manual_paths": {
            "api_create_rsc": "/etc/kolibri-gomesh/routeros-api/create-kolibri-routeros-api-user.rsc",
            "api_remove_rsc": "/etc/kolibri-gomesh/routeros-api/remove-kolibri-routeros-api-user.rsc",
            "dump_commands_file": effective_dump.get("commands_file", {}).get("path"),
            "dump_expected_file": effective_dump.get("dump_file", {}).get("path"),
        },
        "bundle_verify": {
            "ok": effective_bundle.get("ok"),
            "password_printed": effective_bundle.get("checks", {}).get("password_printed"),
            "password_matches_create_command": effective_bundle.get("checks", {}).get("password_matches_create_command"),
            "blockers": effective_bundle.get("blockers", []),
        },
        "verification_handoff": verification_handoff(manifest, node_context),
        "next_actions": build_next_actions(objective, effective_live, effective_dump, effective_window, rollout_body),
        "live_changes_made_by_report": False,
        "ok": bool(objective_cmd["ok"]) and bool(live_cmd["ok"]) and bool(rollout_cmd["ok"]),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
