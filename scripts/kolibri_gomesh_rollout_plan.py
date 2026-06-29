#!/usr/bin/env python3
"""Generate a read-only supervised rollout change plan for Kolibri GoMesh.

The plan contains exact operator commands and rollback steps. It does not touch
MikroTik, does not create lock files, and does not change Home routing.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


DEFAULT_MANIFESTS = (
    Path("/etc/kolibri-gomesh/exits.json"),
    Path("/opt/kolibri/repo/ops/kolibri-gomesh-exits.json"),
)
DEFAULT_PREFLIGHT = Path("/usr/local/sbin/kolibri-gomesh-rollout-preflight")


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


def preflight_json(preflight: Path, manifest: Path, timeout: int) -> tuple[dict[str, Any], dict[str, Any]]:
    result = run([str(preflight), "--manifest", str(manifest)], timeout=timeout)
    return result, parse_json(result["stdout"])


def routeros_script(name: str, purpose: str) -> dict[str, str]:
    return {
        "purpose": purpose,
        "command": f"/system/script/run {name}",
    }


def routeros_custom_enable(client: dict[str, str], table: str) -> list[dict[str, str]]:
    label = client["label"]
    ip = client["ip"]
    comment = f"Kolibri Home gateway custom {label}"
    dns_comment = f"Kolibri DNS redirect custom {label}"
    return [
        {
            "purpose": f"Add or update routing rule for custom client {label}",
            "command": (
                f'/routing/rule/remove [find comment="{comment}"]; '
                f'/routing/rule/add src-address={ip}/32 action=lookup-only-in-table table={table} comment="{comment}"'
            ),
        },
        {
            "purpose": f"Add UDP DNS redirect for custom client {label}",
            "command": (
                f'/ip/firewall/nat/remove [find comment="{dns_comment} UDP"]; '
                f'/ip/firewall/nat/add chain=dstnat action=redirect to-ports=53 protocol=udp '
                f'src-address={ip} dst-port=53 comment="{dns_comment} UDP"'
            ),
        },
        {
            "purpose": f"Add TCP DNS redirect for custom client {label}",
            "command": (
                f'/ip/firewall/nat/remove [find comment="{dns_comment} TCP"]; '
                f'/ip/firewall/nat/add chain=dstnat action=redirect to-ports=53 protocol=tcp '
                f'src-address={ip} dst-port=53 comment="{dns_comment} TCP"'
            ),
        },
    ]


def routeros_custom_disable(client: dict[str, str]) -> list[dict[str, str]]:
    label = client["label"]
    return [
        {
            "purpose": f"Disable custom client {label} routing and DNS redirects",
            "command": (
                f'/routing/rule/disable [find comment="Kolibri Home gateway custom {label}"]; '
                f'/ip/firewall/nat/disable [find comment~"Kolibri DNS redirect custom {label}"]'
            ),
        }
    ]


def parse_client(value: str) -> dict[str, str]:
    # Accepted forms:
    #   id=tv2,ip=192.168.88.25,label=BedroomTV
    #   tv2,192.168.88.25,BedroomTV
    if "=" in value:
        parts = {}
        for item in value.split(","):
            key, sep, val = item.partition("=")
            if not sep:
                raise SystemExit(f"invalid --client segment: {item}")
            parts[key.strip()] = val.strip()
        client_id = parts.get("id") or parts.get("label") or parts.get("ip")
        ip = parts.get("ip")
        label = parts.get("label") or str(client_id).replace(" ", "-")
    else:
        fields = [item.strip() for item in value.split(",")]
        if len(fields) != 3:
            raise SystemExit("--client must be id,ip,label or id=...,ip=...,label=...")
        client_id, ip, label = fields
    if not client_id or not ip or not label:
        raise SystemExit(f"invalid --client: {value}")
    return {"id": str(client_id), "ip": str(ip), "label": str(label).replace('"', "").replace(" ", "-")}


def verification_commands(scope: str) -> list[dict[str, str]]:
    expected_scope = "lan" if scope == "lan" else "stable-canaries"
    commands = [
        {
            "purpose": "Show MikroTik Kolibri policy state after the change",
            "command": "/system/script/run kolibri-home-gw-status",
        },
        {
            "purpose": f"Verify RouterOS live state after the change expects {expected_scope}",
            "command": f"/usr/local/sbin/kolibri-gomesh-routeros-live-audit --expected-scope {expected_scope} --pretty",
        },
        {
            "purpose": "Verify Home endpoint and health",
            "command": "/usr/local/sbin/kolibri-gomesh-home-failover status",
        },
        {
            "purpose": "Run full Home readiness audit",
            "command": "/usr/local/sbin/kolibri-gomesh-readiness-audit --pretty",
        },
        {
            "purpose": "Run service route policy audit",
            "command": "/usr/local/sbin/kolibri-gomesh-service-route-audit --pretty",
        },
    ]
    return commands


def build_scope_plan(
    manifest: dict[str, Any],
    scope: str,
    clients: list[dict[str, str]],
) -> dict[str, Any]:
    mikrotik = manifest.get("mikrotik_gateway", {})
    scripts = mikrotik.get("scripts", {})
    table = str(mikrotik.get("policy_table", "kolibri-home-gw"))

    if scope == "stable-canaries":
        apply_steps = [
            routeros_script(
                str(scripts.get("enable_stable_canaries", "kolibri-home-gw-enable-stable-canaries")),
                "Enable only the known stable LG/Galaxy canaries",
            )
        ]
        rollback_steps = [
            routeros_script(str(scripts.get("disable_all", "kolibri-home-gw-disable-all")), "Emergency rollback all Kolibri client routing"),
        ]
    elif scope == "disabled-canaries":
        disabled = mikrotik.get("disabled_canaries", [])
        apply_steps = []
        rollback_steps = []
        for item in disabled:
            hostname = str(item.get("hostname") or item.get("id"))
            if hostname.lower() == "macbook":
                script_suffix = "macbook"
            else:
                script_suffix = hostname.lower().replace(" ", "-")
            apply_steps.append(
                routeros_script(
                    f"kolibri-home-gw-enable-{script_suffix}",
                    f"Enable disabled canary {hostname}; requires explicit user approval",
                )
            )
            rollback_steps.append(
                routeros_script(f"kolibri-home-gw-disable-{script_suffix}", f"Rollback disabled canary {hostname}")
            )
        if not apply_steps:
            apply_steps.append({"purpose": "No disabled canaries are listed in manifest", "command": "noop"})
    elif scope == "custom":
        apply_steps = [step for client in clients for step in routeros_custom_enable(client, table)]
        rollback_steps = [step for client in clients for step in routeros_custom_disable(client)]
        if not clients:
            apply_steps.append({"purpose": "No custom clients supplied", "command": "blocked: pass --client id,ip,label"})
    elif scope == "lan":
        apply_steps = [
            routeros_script(str(scripts.get("enable_lan", "kolibri-home-gw-enable-lan")), "Enable whole-LAN Kolibri policy route")
        ]
        rollback_steps = [
            routeros_script(str(scripts.get("disable_lan", "kolibri-home-gw-disable-lan")), "Rollback whole-LAN Kolibri policy route"),
            routeros_script(str(scripts.get("disable_all", "kolibri-home-gw-disable-all")), "Emergency rollback all Kolibri client routing"),
        ]
    else:
        raise SystemExit(f"unsupported scope: {scope}")

    return {
        "scope": scope,
        "custom_clients": clients,
        "apply_steps": apply_steps,
        "verify_steps": verification_commands(scope),
        "rollback_steps": rollback_steps,
    }


def safety_notes(scope: str, preflight: dict[str, Any]) -> list[str]:
    rollout = preflight.get("rollout", {})
    notes = [
        "This is a read-only plan; it does not execute MikroTik commands.",
        "Create /etc/kolibri-gomesh/allow-lan-rollout only inside a supervised rollout window.",
        "Remove /etc/kolibri-gomesh/allow-lan-rollout immediately after apply or rollback.",
        "Do not create /etc/kolibri-gomesh/allow-selector-apply during client routing rollout.",
        "Run rollback first if any client loses DNS or internet access.",
    ]
    if scope == "lan":
        notes.append("Whole-LAN rollout remains a separate high-risk change window even when observation is ready.")
    if rollout.get("locks", {}).get("rollout", {}).get("present"):
        notes.append("Rollout lock is currently present; verify this is intentional before executing any RouterOS command.")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--preflight", type=Path, default=DEFAULT_PREFLIGHT)
    parser.add_argument("--scope", choices=["stable-canaries", "disabled-canaries", "custom", "lan"], default="custom")
    parser.add_argument("--client", action="append", default=[], help="Custom client: id,ip,label or id=...,ip=...,label=...")
    parser.add_argument("--timeout", type=int, default=320)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    manifest_path, manifest = load_manifest(args.manifest)
    preflight_command, preflight = preflight_json(args.preflight, manifest_path, args.timeout)
    clients = [parse_client(item) for item in args.client]
    scope_plan = build_scope_plan(manifest, args.scope, clients)
    rollout = preflight.get("rollout", {})
    result = {
        "timestamp_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "manifest": str(manifest_path),
        "mode": "read_only_rollout_change_plan",
        "scope": args.scope,
        "commands": {
            "preflight": {key: preflight_command[key] for key in ("ok", "exit_code", "duration_ms", "stderr")},
        },
        "preflight_summary": {
            "observationally_ready": bool(rollout.get("observationally_ready")),
            "next_group_allowed": bool(rollout.get("next_group_allowed")),
            "whole_lan_allowed": bool(rollout.get("whole_lan_allowed")),
            "safety_blockers": rollout.get("safety_blockers", []),
            "current_endpoint": rollout.get("current_endpoint", ""),
            "current_health": rollout.get("current_health", ""),
            "selector_history": rollout.get("selector_history", {}),
            "locks": rollout.get("locks", {}),
        },
        "plan": scope_plan,
        "safety_notes": safety_notes(args.scope, preflight),
        "ok": bool(preflight_command["ok"]) and bool(rollout.get("observationally_ready")),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if preflight_command["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
