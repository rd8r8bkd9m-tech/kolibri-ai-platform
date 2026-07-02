#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(pwd)}"
NODE_ID="${KOLIBRI_NODE_ID:-qjns}"

if [[ ! -f "${ROOT}/ops/agent_host.py" ]]; then
  echo "agent_host_missing:${ROOT}/ops/agent_host.py" >&2
  exit 1
fi

KOLIBRI_REPO_ROOT="${ROOT}" KOLIBRI_NODE_ID="${NODE_ID}" python3 - <<'PY'
import argparse
import importlib.util
import json
import os
from pathlib import Path

root = Path(os.environ["KOLIBRI_REPO_ROOT"])
spec = importlib.util.spec_from_file_location("agent_host_preflight", root / "ops" / "agent_host.py")
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)

node_id = os.environ.get("KOLIBRI_NODE_ID", "qjns")
args = argparse.Namespace(
    control_url="http://127.0.0.1:9101",
    control_urls="http://127.0.0.1:9101",
    node_id=node_id,
    agent_id=f"preflight-{node_id}",
    capabilities=os.environ.get("KOLIBRI_AGENT_CAPABILITIES", "read_only_probe"),
    repo_url=os.environ.get("KOLIBRI_REPO_URL", "https://example.invalid/repo.git"),
    work_root=os.environ.get("KOLIBRI_AGENT_WORK_ROOT", "/tmp/kolibri-agent-preflight/work"),
    artifact_root=os.environ.get("KOLIBRI_AGENT_ARTIFACT_ROOT", "/tmp/kolibri-agent-preflight/artifacts"),
    heartbeat_interval=int(os.environ.get("KOLIBRI_HEARTBEAT_INTERVAL", "10")),
    lease_refresh=int(os.environ.get("KOLIBRI_LEASE_REFRESH", "20")),
    max_inflight=int(os.environ.get("KOLIBRI_MAX_INFLIGHT", "1")),
)
host = module.AgentHost(args)
payload = {
    "node_id": host.node_id,
    "worker_pool": host.worker_pool,
    "capabilities": host.capabilities,
    "runners": {
        name: {"status": state.get("status"), "checked_at": state.get("checked_at")}
        for name, state in host.runner_status.items()
    },
}
print(json.dumps(payload, sort_keys=True))
raise SystemExit(0 if host.worker_pool.get("ready") else 2)
PY
