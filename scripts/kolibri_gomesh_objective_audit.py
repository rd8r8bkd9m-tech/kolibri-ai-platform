#!/usr/bin/env python3
"""Read-only completion audit for the Kolibri GoMesh home-gateway objective.

The audit is intentionally strict about completion, but light enough to run via
mesh-exec. It reuses one rollout preflight for expensive runtime/service-route
evidence and combines it with fast status, systemd, and failover checks.

It does not read PSK files, does not create lock files, and does not change Home
or MikroTik routing.
"""

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
DEFAULT_MANIFESTS = (
    Path("/etc/kolibri-gomesh/exits.json"),
    Path("/opt/kolibri/repo/ops/kolibri-gomesh-exits.json"),
)
DEFAULT_STATUS = Path("/usr/local/sbin/kolibri-gomesh-status")
DEFAULT_ROLLOUT_PREFLIGHT = Path("/usr/local/sbin/kolibri-gomesh-rollout-preflight")
DEFAULT_FAILOVER = Path("/usr/local/sbin/kolibri-gomesh-home-failover")
DEFAULT_ROLLOUT_PLAN = Path("/usr/local/sbin/kolibri-gomesh-rollout-plan")
DEFAULT_ROUTEROS_LIVE_AUDIT = Path("/usr/local/sbin/kolibri-gomesh-routeros-live-audit")
DEFAULT_HOME_COLLECTOR_SUMMARY = Path("/opt/kolibri/repo/.run/gomesh-home-live-latest.json")
DEFAULT_RUNBOOKS = (
    Path("/etc/kolibri-gomesh/docs/kolibri-gomesh-home-gateway-runbook.md"),
    Path("/opt/kolibri/repo/docs/kolibri-gomesh-home-gateway-runbook.md"),
)


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


def load_manifest(path: Path | None) -> tuple[Path, dict[str, Any]]:
    candidates = (path,) if path else DEFAULT_MANIFESTS
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate, json.loads(candidate.read_text())
    searched = ", ".join(str(item) for item in candidates if item)
    raise SystemExit(f"manifest not found; searched: {searched}")


def parse_json(stdout: str) -> dict[str, Any]:
    if not stdout:
        return {}
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "parse_error": str(exc), "raw_stdout_prefix": stdout[:500]}
    return value if isinstance(value, dict) else {"ok": False, "parse_error": "JSON root is not object"}


def parse_key_values(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            values[key.strip()] = value.strip()
    return values


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def load_home_collector_summary(path: Path, max_age_minutes: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "usable": False,
            "reason": "summary file is missing",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "path": str(path),
            "exists": True,
            "usable": False,
            "reason": f"summary file is not valid JSON: {exc}",
        }
    timestamp = parse_time(str(data.get("timestamp_utc", "")))
    age_seconds = None
    stale = True
    if timestamp:
        age_seconds = max(0, int((datetime.now(UTC) - timestamp).total_seconds()))
        stale = age_seconds > max_age_minutes * 60
    data["_collector_meta"] = {
        "path": str(path),
        "exists": True,
        "timestamp_utc": timestamp.isoformat(timespec="seconds") if timestamp else "",
        "age_seconds": age_seconds,
        "max_age_minutes": max_age_minutes,
        "stale": stale,
        "usable": bool(data.get("ok")) and not stale,
        "reason": "" if bool(data.get("ok")) and not stale else ("summary is stale or not ok"),
    }
    return data


def command_json(argv: list[str], timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    result = run(argv, timeout=timeout)
    return result, parse_json(result["stdout"])


def summarize_command(result: dict[str, Any]) -> dict[str, Any]:
    summary = {key: result[key] for key in ("ok", "exit_code", "duration_ms", "stderr")}
    if "skipped" in result:
        summary["skipped"] = result["skipped"]
    return summary


def bool_all(items: list[dict[str, Any]]) -> bool:
    return all(bool(item.get("ok")) for item in items)


def first_existing(paths: tuple[Path, ...]) -> str:
    for path in paths:
        if path.exists():
            return str(path)
    return ""


def requirement(status: str, evidence: dict[str, Any], blockers: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "evidence": evidence,
        "blockers": blockers or [],
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


def resolve_tool(path: Path, repo_name: str) -> Path:
    if path.exists():
        return path
    repo_path = SCRIPT_DIR / repo_name
    return repo_path if repo_path.exists() else path


def local_addresses() -> list[str]:
    result = run(["hostname", "-I"], timeout=5)
    if not result["ok"]:
        return []
    return [item for item in result["stdout"].split() if item]


def detect_node_context(manifest: dict[str, Any], explicit_role: str) -> dict[str, Any]:
    home = manifest.get("home_gateway", {})
    hostname = socket.gethostname()
    addresses = local_addresses()
    client_tun = str(home.get("client_tun", "kgmhome0"))
    tun_present = Path("/sys/class/net", client_tun).exists()
    home_matches = {
        "hostname": bool(home.get("hostname") and hostname == home.get("hostname")),
        "lan_ip": bool(home.get("lan_ip") and home.get("lan_ip") in addresses),
        "mesh_ip": bool(home.get("mesh_ip") and home.get("mesh_ip") in addresses),
        "client_tun": tun_present,
    }
    auto_role = "home" if any(home_matches.values()) else "non-home"
    role = auto_role if explicit_role == "auto" else explicit_role
    return {
        "role": role,
        "auto_role": auto_role,
        "hostname": hostname,
        "addresses": addresses,
        "home_matches": home_matches,
        "home_runtime_checks_local": role == "home",
    }


def service_profile_expected(home: dict[str, Any]) -> dict[str, str]:
    profile = home.get("carrier_profile", {})
    expected: dict[str, str] = {}
    if profile.get("mode"):
        expected["carrier"] = f"--carrier {profile['mode']}"
    if profile.get("dial_timeout"):
        expected["timeout"] = f"--timeout {profile['dial_timeout']}"
    if profile.get("queue_size"):
        expected["queue_size"] = f"--queue-size {profile['queue_size']}"
    if profile.get("tun_mtu"):
        expected["tun_mtu"] = f"--tun-mtu {profile['tun_mtu']}"
    return expected


def service_profile_summary(home: dict[str, Any], service_cat: dict[str, Any]) -> dict[str, Any]:
    expected = service_profile_expected(home)
    stdout = service_cat.get("stdout", "")
    missing = [label for label, needle in expected.items() if needle not in stdout]
    return {
        "ok": bool(service_cat.get("ok")) and not missing,
        "expected": expected,
        "missing": missing,
    }


def build_audit(
    manifest_path: Path,
    manifest: dict[str, Any],
    node_context: dict[str, Any],
    home_collector: dict[str, Any],
    status: dict[str, Any],
    rollout_preflight: dict[str, Any],
    failover_values: dict[str, str],
    client_service: dict[str, Any],
    health_timer: dict[str, Any],
    service_profile: dict[str, Any],
    routeros_live: dict[str, Any],
    expected_scope: str,
    rollout_plan_path: Path,
    runbook_path: str,
) -> dict[str, Any]:
    rollout = rollout_preflight.get("rollout", {})
    home_gateway = manifest.get("home_gateway", {})
    mikrotik = manifest.get("mikrotik_gateway", {})
    active_canaries = mikrotik.get("active_canaries", [])
    disabled_canaries = mikrotik.get("disabled_canaries", [])
    disabled_rollout = mikrotik.get("disabled_rollout", {})
    routeros_audit = rollout.get("routeros_profile_audit", {})
    if not routeros_audit:
        profile_last = mikrotik.get("profile_audit", {}).get("last_verified_result", {})
        if profile_last:
            routeros_audit = {
                "ok": bool(profile_last.get("ok")),
                "source": "manifest_profile_audit_last_verified_result",
                "profile": mikrotik.get("profile_audit", {}).get("home_profile_path", ""),
                "blockers": profile_last.get("blockers", []),
                "warnings": profile_last.get("warnings", []),
                "expected": profile_last.get("expected", {}),
                "observed": profile_last.get("observed", {}),
                "last_verified_utc": mikrotik.get("profile_audit", {}).get("last_verified_utc", ""),
            }
    selector_history = rollout.get("selector_history", {})
    locks = rollout.get("locks", {})
    rollout_lock = locks.get("rollout", {})
    selector_apply_lock = locks.get("selector_apply", {})
    service_actions = rollout.get("service_route_actions", {})

    tcp_checks = status.get("tcp_checks", [])
    is_home_node = node_context.get("role") == "home"
    collector_meta = home_collector.get("_collector_meta", {})
    collector_usable = bool(collector_meta.get("usable"))
    collector_home = home_collector.get("home_runtime", {}) if collector_usable else {}
    collector_readiness = home_collector.get("readiness", {}) if collector_usable else {}
    collector_objective = home_collector.get("objective", {}) if collector_usable else {}
    collector_routeros = home_collector.get("routeros_live", {}) if collector_usable else {}
    multi_exit_ok = (
        bool(status.get("ok"))
        and int(status.get("active_exit_count", 0)) >= 2
        and len(status.get("countries", [])) >= 2
        and bool_all(tcp_checks)
    )
    profile = service_profile_summary(home_gateway, service_profile)
    home_ok = (
        bool(client_service.get("ok"))
        and client_service.get("stdout") == "active"
        and bool(health_timer.get("ok"))
        and health_timer.get("stdout") == "active"
        and profile["ok"]
        and failover_values.get("health") == "ok"
    )
    if not is_home_node and collector_usable:
        collector_routes = collector_home.get("canary_routes", [])
        home_ok = (
            bool(collector_home.get("status_ok"))
            and collector_home.get("client_service") == "active"
            and collector_home.get("health_timer") == "active"
            and bool(collector_home.get("service_profile_ok"))
            and bool(collector_home.get("external_ip"))
        )
    routeros_ok = bool(routeros_audit.get("ok"))
    service_ok = bool(rollout.get("service_route_policy_ok"))
    if not is_home_node and collector_usable:
        service_ok = bool(collector_readiness.get("service_route_policy_ok"))
    routeros_live_dump = routeros_live.get("dump_audit") or {}
    routeros_live_access = routeros_live.get("access") or {}
    routeros_api_bundle = routeros_live_access.get("api_bootstrap_bundle") or {}
    routeros_scope = str(routeros_live.get("expected_scope") or "pre-rollout")
    routeros_live_verified = bool(routeros_live_dump.get("live_config_verified")) and routeros_scope == expected_scope
    if not is_home_node and collector_usable:
        collector_scope = str(collector_routeros.get("expected_scope") or "pre-rollout")
        if expected_scope in {"pre-rollout", "stable-canaries"} and not collector_routeros.get("expected_scope"):
            collector_scope = expected_scope
        routeros_live_verified = bool(collector_routeros.get("live_config_verified")) and collector_scope == expected_scope
    effective_routeros_host = routeros_live_access.get("router_host")
    effective_routeros_tcp_ports = [
        item.get("port")
        for item in routeros_live_access.get("tcp_checks", [])
        if item.get("ok")
    ]
    effective_routeros_ssh_ok = routeros_live_access.get("ssh_batch_probe", {}).get("ok")
    effective_routeros_api_ok = routeros_live_access.get("api_probe", {}).get("login_ok")
    effective_routeros_bundle_ok = routeros_api_bundle.get("ok")
    effective_routeros_manual_dump_required = routeros_live_access.get("manual_live_dump_required")
    effective_routeros_dump_blockers = routeros_live_dump.get("blockers", [])
    if not is_home_node and collector_usable and collector_routeros:
        effective_routeros_host = collector_routeros.get("router_host")
        effective_routeros_tcp_ports = collector_routeros.get("tcp_open_ports", [])
        effective_routeros_ssh_ok = collector_routeros.get("ssh_batch_ok")
        effective_routeros_api_ok = collector_routeros.get("api_login_ok")
        effective_routeros_bundle_ok = collector_routeros.get("api_bootstrap_bundle_ready")
        effective_routeros_manual_dump_required = collector_routeros.get("manual_live_dump_required")
        effective_routeros_dump_blockers = collector_routeros.get("dump_blockers", [])
    canary_ok = bool(rollout.get("observationally_ready")) and int(rollout.get("active_canary_count", 0)) >= 2
    observation_ok = bool(rollout.get("observationally_ready"))
    if not is_home_node and collector_usable:
        collector_routes = collector_home.get("canary_routes", [])
        canary_ok = (
            bool(collector_readiness.get("current_canary_state_ok"))
            and int(collector_readiness.get("active_canary_count") or 0) >= 2
            and bool(collector_routes)
            and all(bool(item.get("ok")) for item in collector_routes)
        )
        observation_ok = bool(collector_readiness.get("current_canary_state_ok"))
    next_group_ready = observation_ok and not bool(selector_apply_lock.get("present"))
    if not is_home_node and collector_usable:
        next_group_ready = bool(collector_objective.get("ready_for_supervised_next_group"))
    next_group_allowed = bool(rollout.get("next_group_allowed"))
    whole_lan_allowed = bool(rollout.get("whole_lan_allowed"))
    if not is_home_node and collector_usable:
        next_group_allowed = False
        whole_lan_allowed = bool(collector_objective.get("ready_for_whole_lan"))

    home_status = "passed" if home_ok else ("failed" if is_home_node else "unverified")
    home_blockers = (
        []
        if home_ok
        else (
            ["Home Kolibri dataplane is not fully healthy"]
            if is_home_node
            else ["Home runtime is not verified from this node; run this audit on Home or collect the Home operator report."]
        )
    )
    service_status = "passed" if service_ok else ("failed" if is_home_node else "unverified")
    service_blockers = (
        []
        if service_ok
        else (
            ["service route policy is not ok"]
            if is_home_node
            else ["service route policy requires Home kgmhome0 runtime probes; not verified from this node."]
        )
    )
    canary_status = "passed" if canary_ok else ("failed" if is_home_node else "unverified")
    canary_blockers = (
        []
        if canary_ok
        else (
            ["active canary client routing is not proven stable"]
            if is_home_node
            else ["active canary routing must be verified on Home/MikroTik live state; not verified from this node."]
        )
    )
    routeros_live_blocker = (
        "RouterOS live config is not verified; capture kolibri-home-gw-status dump or enable read-only RouterOS API/SSH access"
        if is_home_node
        else "RouterOS live config must be verified from Home or a manual WinBox dump; not verified from this node"
    )

    requirements = {
        "documented_architecture": requirement(
            "passed" if runbook_path else "missing",
            {
                "manifest": str(manifest_path),
                "runbook": runbook_path,
                "shape": "clients -> MikroTik -> Home/Linux Kolibri TUN -> country exit -> internet",
                "lan_cidr": home_gateway.get("lan_cidr"),
            },
            [] if runbook_path else ["runbook file is missing"],
        ),
        "controlled_country_exits": requirement(
            "passed" if multi_exit_ok else "failed",
            {
                "active_exit_count": status.get("active_exit_count", 0),
                "countries": status.get("countries", []),
                "tcp_checks": [
                    {
                        "id": item.get("id"),
                        "role": item.get("role"),
                        "country": item.get("country"),
                        "endpoint": item.get("endpoint"),
                        "ok": item.get("ok"),
                        "duration_ms": item.get("duration_ms"),
                    }
                    for item in tcp_checks
                ],
            },
            [] if multi_exit_ok else ["need at least two healthy controlled country exits"],
        ),
        "home_dataplane_gateway": requirement(
            home_status,
            {
                "hostname": home_gateway.get("hostname"),
                "lan_ip": home_gateway.get("lan_ip"),
                "mesh_ip": home_gateway.get("mesh_ip"),
                "node_context": node_context,
                "home_collector": collector_meta,
                "client_service_state": client_service.get("stdout"),
                "health_timer_state": health_timer.get("stdout"),
                "service_profile": profile,
                "current_endpoint": failover_values.get("endpoint", ""),
                "current_health": failover_values.get("health", ""),
                "collector_runtime": {
                    "client_service": collector_home.get("client_service"),
                    "health_timer": collector_home.get("health_timer"),
                    "external_ip": collector_home.get("external_ip"),
                    "status_ok": collector_home.get("status_ok"),
                    "service_profile_ok": collector_home.get("service_profile_ok"),
                },
                "last_primary_runtime_verified_utc": home_gateway.get("failover", {}).get("last_primary_runtime_verified_utc", ""),
                "last_primary_runtime_verified_result": home_gateway.get("failover", {}).get("last_primary_runtime_verified_result", {}),
            },
            home_blockers,
        ),
        "mikrotik_central_gateway_profile": requirement(
            "passed" if routeros_ok else "failed",
            {
                "model": mikrotik.get("model"),
                "lan_ip": mikrotik.get("lan_ip"),
                "policy_table": mikrotik.get("policy_table"),
                "home_next_hop": mikrotik.get("home_next_hop"),
                "audit": routeros_audit,
            },
            [] if routeros_ok else routeros_audit.get("blockers", ["RouterOS profile audit failed"]),
        ),
        "mikrotik_live_state": requirement(
            "passed" if routeros_live_verified else "unverified",
            {
                "live_config_verified": routeros_live_verified,
                "expected_scope": expected_scope,
                "observed_scope": collector_routeros.get("expected_scope") or routeros_live.get("expected_scope") or "pre-rollout",
                "router_host": effective_routeros_host,
                "tcp_open_ports": effective_routeros_tcp_ports,
                "ssh_batch_ok": effective_routeros_ssh_ok,
                "api_login_ok": effective_routeros_api_ok,
                "api_bootstrap_bundle_ready": effective_routeros_bundle_ok,
                "api_bootstrap_bundle_summary": routeros_api_bundle.get("summary", {}),
                "collector_routeros": collector_routeros,
                "manual_live_dump_required": effective_routeros_manual_dump_required,
                "dump_blockers": effective_routeros_dump_blockers,
            },
            []
            if routeros_live_verified
            else [routeros_live_blocker],
        ),
        "service_access_policy": requirement(
            service_status,
            {
                "service_route_policy_ok": service_ok,
                "policy_actions": service_actions,
                "current_endpoint": rollout.get("current_endpoint"),
                "current_health": rollout.get("current_health"),
                "collector_readiness": {
                    "current_endpoint": collector_readiness.get("current_endpoint"),
                    "current_health": collector_readiness.get("current_health"),
                    "service_route_policy_ok": collector_readiness.get("service_route_policy_ok"),
                    "target_checks": collector_home.get("target_checks", []),
                },
                "last_readiness_verified_utc": home_gateway.get("failover", {}).get("readiness_audit", {}).get("last_verified_utc", ""),
                "last_readiness_verified_result": home_gateway.get("failover", {}).get("readiness_audit", {}).get("last_verified_result", {}),
            },
            service_blockers,
        ),
        "canary_clients_routed": requirement(
            canary_status,
            {
                "active_canary_count": rollout.get("active_canary_count", 0),
                "active_canaries": active_canaries,
                "observationally_ready": observation_ok,
                "observation_blockers": rollout.get("observation_blockers", []),
                "collector_canary_routes": collector_home.get("canary_routes", []),
                "last_canary_route_verified_utc": mikrotik.get("last_canary_route_verified_utc", ""),
            },
            canary_blockers,
        ),
        "rollout_gate": requirement(
            "staged" if next_group_ready else "blocked",
            {
                "observationally_ready": observation_ok,
                "next_group_ready_for_supervised_window": next_group_ready,
                "next_group_allowed_now": next_group_allowed,
                "whole_lan_allowed_now": whole_lan_allowed,
                "rollout_lock_present": bool(rollout_lock.get("present")),
                "selector_apply_lock_present": bool(selector_apply_lock.get("present")),
                "selector_history": selector_history,
                "rollout_plan_available": rollout_plan_path.exists(),
            },
            rollout.get("next_group_blockers", []),
        ),
        "whole_lan_or_all_home_clients": requirement(
            "incomplete",
            {
                "disabled_rollout": disabled_rollout,
                "disabled_canaries": disabled_canaries,
                "whole_lan_allowed_now": whole_lan_allowed,
                "rollout_lock_present": bool(rollout_lock.get("present")),
            },
            [
                "whole-LAN routing remains disabled until a separate supervised MikroTik change window",
                "next client group has not been selected, applied, and verified",
                "MacBook canary remains disabled by user request",
            ],
        ),
    }

    complete = (
        all(
            item["status"] == "passed"
            for key, item in requirements.items()
            if key not in {"rollout_gate", "whole_lan_or_all_home_clients"}
        )
        and next_group_allowed
        and whole_lan_allowed
    )
    remaining: list[str] = []
    if not complete:
        if not routeros_live_verified:
            remaining.append(
                "capture and audit live MikroTik status with kolibri-gomesh-routeros-live-audit --dump, or enable read-only RouterOS API/SSH access for live audit"
            )
        if not next_group_ready:
            remaining.append("wait until canary observation is stable enough for the next supervised group")
        remaining.extend(
            [
                "choose the next client group or explicitly approve a supervised rollout window",
                "create /etc/kolibri-gomesh/allow-lan-rollout only for that window",
                "apply the generated MikroTik plan for the chosen clients",
                "verify DNS, YouTube, Xiaomi MiMo, external IP, and rollback from the real clients",
                "remove the rollout lock after apply or rollback",
            ]
        )

    return {
        "objective": (
            "Configure and document Kolibri GoMesh through controlled country exits, "
            "with MikroTik/Home as central gateway for home clients, without breaking current internet/services."
        ),
        "node_context": node_context,
        "objective_complete": complete,
        "ready_for_supervised_next_group": next_group_ready,
        "ready_for_whole_lan": whole_lan_allowed,
        "requirements": requirements,
        "remaining_requirements": [] if complete else remaining,
        "safety_summary": {
            "live_changes_made_by_this_audit": False,
            "rollout_lock_present": bool(rollout_lock.get("present")),
            "selector_apply_lock_present": bool(selector_apply_lock.get("present")),
            "lan_rollout_enabled": False,
            "macbook_disabled_by_user_request": bool(disabled_canaries),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--rollout-preflight", type=Path, default=DEFAULT_ROLLOUT_PREFLIGHT)
    parser.add_argument("--failover", type=Path, default=DEFAULT_FAILOVER)
    parser.add_argument("--rollout-plan", type=Path, default=DEFAULT_ROLLOUT_PLAN)
    parser.add_argument("--routeros-live-audit", type=Path, default=DEFAULT_ROUTEROS_LIVE_AUDIT)
    parser.add_argument("--expected-scope", choices=("pre-rollout", "stable-canaries", "lan"), default="pre-rollout")
    parser.add_argument("--home-collector-summary", type=Path, default=DEFAULT_HOME_COLLECTOR_SUMMARY)
    parser.add_argument("--home-collector-max-age-minutes", type=int, default=60)
    parser.add_argument("--node-role", choices=("auto", "home", "non-home"), default="auto")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--fail-if-incomplete", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    manifest_path, manifest = load_manifest(args.manifest)
    status_path = resolve_tool(args.status, "kolibri_gomesh_status.py")
    rollout_preflight_path = resolve_tool(args.rollout_preflight, "kolibri_gomesh_rollout_preflight.py")
    failover_path = resolve_tool(args.failover, "kolibri_gomesh_home_failover.sh")
    rollout_plan_path = resolve_tool(args.rollout_plan, "kolibri_gomesh_rollout_plan.py")
    routeros_live_path = resolve_tool(args.routeros_live_audit, "kolibri_gomesh_routeros_live_audit.py")
    node_context = detect_node_context(manifest, args.node_role)
    home_collector = load_home_collector_summary(args.home_collector_summary, args.home_collector_max_age_minutes)
    is_home_node = node_context["role"] == "home"
    home_gateway = manifest.get("home_gateway", {})
    client_service_name = str(home_gateway.get("client_service", "kolibri-gomesh-home-client.service"))
    health_timer_name = str(
        home_gateway.get("failover", {}).get("healthcheck_timer", "kolibri-gomesh-home-healthcheck.timer")
    )

    status_command, status = command_json(
        [str(status_path), "--manifest", str(manifest_path)],
        timeout=min(args.timeout, 60),
    )
    if is_home_node:
        rollout_command, rollout_preflight = command_json(
            [str(rollout_preflight_path), "--manifest", str(manifest_path)],
            timeout=args.timeout,
        )
        failover_command = run([str(failover_path), "status"], timeout=30)
        client_service = run(["systemctl", "is-active", client_service_name], timeout=10)
        health_timer = run(["systemctl", "is-active", health_timer_name], timeout=10)
        service_profile = run(["systemctl", "cat", client_service_name], timeout=10)
        routeros_live_command, routeros_live = command_json(
            [str(routeros_live_path), "--manifest", str(manifest_path), "--expected-scope", args.expected_scope],
            timeout=min(args.timeout, 45),
        )
    else:
        reason = "skipped: Home runtime and RouterOS live checks must run on Home or from a manual RouterOS dump"
        rollout_command = skipped(reason)
        rollout_preflight = {}
        failover_command = skipped(reason)
        client_service = skipped(reason)
        health_timer = skipped(reason)
        service_profile = skipped(reason)
        routeros_live_command = skipped(reason)
        routeros_live = {}
    failover_values = parse_key_values(failover_command["stdout"])
    runbook_path = first_existing(DEFAULT_RUNBOOKS)

    objective_audit = build_audit(
        manifest_path=manifest_path,
        manifest=manifest,
        node_context=node_context,
        home_collector=home_collector,
        status=status,
        rollout_preflight=rollout_preflight,
        failover_values=failover_values,
        client_service=client_service,
        health_timer=health_timer,
        service_profile=service_profile,
        routeros_live=routeros_live,
        expected_scope=args.expected_scope,
        rollout_plan_path=rollout_plan_path,
        runbook_path=runbook_path,
    )
    commands_ok = all(
        bool(item["ok"])
        for item in (
            status_command,
            rollout_command,
            failover_command,
            client_service,
            health_timer,
            service_profile,
            routeros_live_command,
        )
    )
    result = {
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "manifest": str(manifest_path),
        "mode": "read_only_objective_completion_audit",
        "commands": {
            "status": summarize_command(status_command),
            "rollout_preflight": summarize_command(rollout_command),
            "failover": summarize_command(failover_command),
            "client_service": summarize_command(client_service),
            "health_timer": summarize_command(health_timer),
            "service_profile": summarize_command(service_profile),
            "routeros_live": summarize_command(routeros_live_command),
        },
        "commands_ok": commands_ok,
        "audit": objective_audit,
        "ok": commands_ok and objective_audit["ready_for_supervised_next_group"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    if args.fail_if_incomplete and not objective_audit["objective_complete"]:
        return 2
    return 0 if commands_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
