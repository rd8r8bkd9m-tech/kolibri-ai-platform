#!/usr/bin/env python3
"""Build Kolibri fleet repair envelopes from reachability sweep evidence."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FALLBACK_NODES = ["main", "server-kfrm", "kolibri-9fts", "kolibri-new", "kolibri-uiap", "kolibri-qjns"]
DEFAULT_ALLOWED_NODES = ["main", "server-kfrm", "kolibri-9fts", "kolibri-new", "kolibri-uiap", "kolibri-qjns"]
HOSTVDS_CANONICAL = {
    "hostvds-agent-10": {
        "server_name": "kolibri-hk-edge-load",
        "address": "217.60.38.191",
        "role": "hk-edge-load",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    return "".join(ch.upper() if ch.isalnum() else "_" for ch in value).strip("_")


def parse_sweep_line(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split("|")
    if len(parts) >= 2 and parts[1] == "ssh_failed":
        return {"alias": parts[0], "reachable": False, "status": "ssh_failed"}
    if len(parts) < 3 or parts[1] != "ok":
        return {"alias": parts[0], "reachable": False, "status": "malformed_sweep_line", "raw": line}

    row: dict[str, Any] = {"alias": parts[0], "reachable": True, "status": "ok", "hostname": parts[2]}
    for item in parts[3:]:
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        row[key] = value
    return row


def parse_sweep_lines(text: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        row = parse_sweep_line(line)
        if row:
            rows.append(row)
    return rows


def node_metadata(alias: str, inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = dict(HOSTVDS_CANONICAL.get(alias, {}))
    if not inventory:
        return metadata
    servers = inventory.get("observed_inventory", {}).get("servers", [])
    for server in servers:
        if server.get("name") == metadata.get("server_name") or server.get("address") == metadata.get("address"):
            metadata.update(server)
            metadata.setdefault("server_name", server.get("name"))
            return metadata
    return metadata


def classify_repair_issue(row: dict[str, Any]) -> dict[str, str] | None:
    if not row.get("reachable"):
        return {
            "kind": "repair_fleet_node_route",
            "reason": "api_unreachable",
            "condition": str(row.get("status") or "unreachable"),
            "priority": "P0",
            "action": "run read-only network, provider status, firewall, and Agent Host diagnostics through a reachable relay",
        }
    if row.get("repo") == "no":
        return {
            "kind": "repair_project_context",
            "reason": "project_context_missing",
            "condition": "repo_missing",
            "priority": "P0",
            "action": "restore /srv/kolibri-ai-platform and rerun fleet project-context bootstrap",
        }
    if row.get("agent") != "active":
        return {
            "kind": "repair_agent_host",
            "reason": "agent_host_down",
            "condition": str(row.get("agent") or "unknown"),
            "priority": "P0",
            "action": "inspect kolibri-agent-host.service, restore Control Plane URLs, and restart Agent Host",
        }
    if row.get("sync") != "active":
        return {
            "kind": "repair_project_sync",
            "reason": "project_sync_down",
            "condition": str(row.get("sync") or "unknown"),
            "priority": "P1",
            "action": "restore kolibri-project-sync.timer or node-specific sync timer",
        }
    if row.get("loopback") != "yes" or str(row.get("http")) not in {"401", "403"}:
        return {
            "kind": "repair_mimocode_loopback",
            "reason": "mimocode_loopback_down",
            "condition": f"loopback={row.get('loopback')} http={row.get('http')}",
            "priority": "P1",
            "action": "restore loopback-only MiMo Code service with local authentication",
        }
    if row.get("public_mimo") == "yes":
        return {
            "kind": "repair_public_mimocode_listener",
            "reason": "public_mimocode_listener",
            "condition": "public_mimo=yes",
            "priority": "P0",
            "action": "disable legacy public MiMo services and keep only loopback MiMo Code",
        }
    if str(row.get("agent_project_env")) not in {"2", "2\n"}:
        return {
            "kind": "repair_agent_project_context",
            "reason": "agent_project_context_missing",
            "condition": f"agent_project_env={row.get('agent_project_env')}",
            "priority": "P1",
            "action": "restart Agent Host with KOLIBRI_OWNER_PROJECT_PATH and KOLIBRI_RUNTIME_REPO",
        }
    return None


def repair_task_id(alias: str, reason: str, *, date_slug: str) -> str:
    return f"P0_REPAIR_{slug(alias)}_{slug(reason)}_{date_slug}"


def blocked_status(row: dict[str, Any], issue: dict[str, str], task_id: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "node": row["alias"],
        "target_node": row["alias"],
        "reason": issue["reason"],
        "condition": issue["condition"],
        "fallback_nodes": DEFAULT_FALLBACK_NODES,
        "fallback_route": {"type": "fabric_api_relay", "endpoint": "/v1/fabric/relay"},
        "can_continue_elsewhere": True,
        "repair_task": task_id,
        "next_action": issue["action"],
    }


def build_repair_envelope(
    row: dict[str, Any],
    issue: dict[str, str],
    *,
    observed_at: str,
    date_slug: str,
    inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = node_metadata(row["alias"], inventory)
    task_id = repair_task_id(row["alias"], issue["reason"], date_slug=date_slug)
    status = blocked_status(row, issue, task_id)
    address = metadata.get("address")
    server_name = metadata.get("server_name") or metadata.get("name") or row.get("hostname") or row["alias"]
    branch = f"codex/{task_id.lower().replace('_', '-')}"
    run_dir = f"docs/agent/runs/{date_slug.replace('_', '-')}-{task_id.lower().replace('_', '-')}"
    return {
        "task_id": task_id,
        "idempotency_key": f"fleet-repair:{row['alias']}:{issue['reason']}:{date_slug}",
        "kind": "owner_remote_task",
        "priority": issue["priority"],
        "branch": branch,
        "base_ref": "main",
        "required_capability": "orchestrator",
        "runner": "mimo",
        "agent_type": "fleet_repair_operator",
        "agent_display_name": "Fleet Repair Operator",
        "target_node": "main",
        "preferred_nodes": DEFAULT_FALLBACK_NODES[:4],
        "allowed_nodes": DEFAULT_ALLOWED_NODES,
        "max_retries": 1,
        "goal": f"Restore Kolibri fleet route for {row['alias']} without blocking owner work.",
        "objective": (
            f"Use read-only diagnostics from healthy fallback nodes to restore the protected Fabric/API route "
            f"for {row['alias']} ({server_name}{' / ' + address if address else ''}). Do not perform paid "
            "provider actions or expose secrets. Keep owner work routed through fallback nodes while this repair runs."
        ),
        "constraints": {
            "read_only_required": True,
            "no_paid_actions": True,
            "do_not_create_servers": True,
            "do_not_delete_servers": True,
            "do_not_change_billing": True,
            "secrets_redaction_required": True,
            "budget_limit_usd": 200,
        },
        "write_scope": [
            f"{run_dir}/**",
            "docs/ops/hostvds/**",
        ],
        "verification_commands": [
            "test -s RESULT.md",
            "test -s NEXT.md",
        ],
        "blocked_status": status,
        "repair": {
            "kind": issue["kind"],
            "reason": issue["reason"],
            "condition": issue["condition"],
            "node_alias": row["alias"],
            "server_name": server_name,
            "address": address,
            "observed_at": observed_at,
            "evidence": row,
            "fallback_nodes": DEFAULT_FALLBACK_NODES,
            "action": issue["action"],
        },
        "acceptance": [
            "Structured blocked status is recorded with fallback nodes and can_continue_elsewhere=true.",
            "Read-only diagnostics identify whether the blocker is host down, firewall, provider route, SSH, or Agent Host.",
            "No paid provider action, billing change, server creation, server deletion, or credential exposure is performed.",
            "If the node becomes reachable, rerun fleet project-context bootstrap and verify repo, memory, sync, Agent Host, and loopback MiMo Code.",
            "Owner work remains routed through healthy fallback nodes while repair is pending.",
        ],
        "source": {
            "kind": "fleet_repair_sweep",
            "created_at": observed_at,
        },
    }


def build_repair_envelopes(
    rows: list[dict[str, Any]],
    *,
    observed_at: str | None = None,
    date_slug: str | None = None,
    inventory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    observed_at = observed_at or utc_now()
    date_slug = date_slug or observed_at[:10].replace("-", "_")
    envelopes = []
    for row in rows:
        issue = classify_repair_issue(row)
        if issue:
            envelopes.append(build_repair_envelope(row, issue, observed_at=observed_at, date_slug=date_slug, inventory=inventory))
    return envelopes


def load_inventory(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_envelopes(envelopes: list[dict[str, Any]], output_dir: Path) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for envelope in envelopes:
        path = output_dir / f"{envelope['task_id']}.json"
        path.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        paths.append(str(path))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep-lines", help="Path to pipe-delimited fleet sweep output. Reads stdin when omitted.")
    parser.add_argument("--inventory", help="Optional HostVDS inventory envelope for node metadata.")
    parser.add_argument("--output-dir", help="Write one repair envelope JSON per issue.")
    parser.add_argument("--observed-at", default=utc_now())
    parser.add_argument("--date-slug", default="")
    args = parser.parse_args()

    text = Path(args.sweep_lines).read_text(encoding="utf-8") if args.sweep_lines else sys.stdin.read()
    rows = parse_sweep_lines(text)
    envelopes = build_repair_envelopes(
        rows,
        observed_at=args.observed_at,
        date_slug=args.date_slug or None,
        inventory=load_inventory(args.inventory),
    )
    written = write_envelopes(envelopes, Path(args.output_dir)) if args.output_dir else []
    print(json.dumps({"repair_count": len(envelopes), "written": written, "repair_tasks": envelopes}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
