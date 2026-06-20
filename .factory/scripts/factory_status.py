#!/usr/bin/env python3
"""Print concise Factory v1 status."""

from __future__ import annotations

import json
from pathlib import Path

from common import FACTORY, ROOT, count_task_files, load_json


def main() -> int:
    inventory = load_json(FACTORY / "server_inventory.json")
    backlog = load_json(FACTORY / "backlog" / "prioritized.json")
    registry = load_json(FACTORY / "agents" / "registry.json")
    legacy_state = ROOT / "logs" / "agent-factory" / "state.json"
    durable_state = FACTORY / "runs" / "agent_factory_state.json"

    backlog_counts: dict[str, int] = {}
    for item in backlog.get("items", []):
        backlog_counts[item["state"]] = backlog_counts.get(item["state"], 0) + 1

    output = {
        "factory": {
            "mode": "bootstrap",
            "task_files": count_task_files(),
            "backlog": backlog_counts,
            "durable_state_exists": durable_state.exists(),
            "legacy_state_exists": legacy_state.exists()
        },
        "servers": {
            "total": len(inventory.get("servers", [])),
            "enabled": sum(1 for server in inventory.get("servers", []) if server.get("enabled")),
            "ssh_unknown": sum(1 for server in inventory.get("servers", []) if server.get("ssh_status") == "unknown")
        },
        "roles": {
            "count": len(registry.get("roles", [])),
            "chief": registry.get("chief", {}).get("id")
        },
        "next_gate": "validate schemas and run dry-run canaries before SSH dispatch"
    }
    print(json.dumps(output, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
