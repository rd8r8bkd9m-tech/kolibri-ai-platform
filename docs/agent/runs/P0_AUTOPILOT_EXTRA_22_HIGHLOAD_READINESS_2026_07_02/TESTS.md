# Verification

Commands run:

```bash
python3 ops/kolibri-dispatch doctor
python3 ops/kolibri-dispatch nodes
python3 ops/kolibri-dispatch fabric-route hostvds-highload --required-capability node_worker_capacity_probe
curl -sS -i --max-time 10 http://10.99.0.2:9101/v1/fleet/nodes
curl -sS --max-time 25 http://10.99.0.2:9101/v1/nodes -o /tmp/kolibri_nodes.json
python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_22_HIGHLOAD_READINESS_2026_07_02
python3 - <<'PY'
import json, urllib.request
for tid in [
    "KOL-CLUSTER-CHECK-mesh-highload-20260630",
    "KOL-CLUSTER-NODE-highload-CHK-20260630",
    "KOL-HOME-CLUSTER-20260629-141939-111-MESH_HIGHLOAD-MIMO",
]:
    d = json.load(urllib.request.urlopen(f"http://10.99.0.2:9101/v1/tasks/{tid}", timeout=10))
    print(tid, d.get("state"), d.get("lease_owner"))
PY
```

Results:

- Control Plane health: `status=ok`, Redis `PONG`.
- Assigned worker proof: task `P0_AUTOPILOT_EXTRA_22_HIGHLOAD_READINESS_2026_07_02` is `running` with lease owner `mesh-agent-22:agent-host-mesh-agent-22`.
- Node inventory API: available through `/v1/nodes`.
- Canonical/fallback route API surface on the live sidecar: unavailable, HTTP 404 for `/v1/fleet/route`, `/v1/fabric/routes`, `/v1/fabric/route`, `/v1/fabric/relay`, and `/v1/agents/tasks`.
- Secret scan of this artifact directory:

```bash
rg --no-ignore -n '[0-9]{6,}:[A-Za-z0-9_-]{20,}|[A-Za-z0-9_]*(TOKEN|SECRET|PASSWORD|COOKIE|API_KEY|CHAT_ID)=[^ ]+' docs/agent/runs/P0_AUTOPILOT_EXTRA_22_HIGHLOAD_READINESS_2026_07_02
```

Expected result: no matches.

