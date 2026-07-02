# Next

Next exact task:

`P0_REPAIR_RESERVE242_AGENT_HOST_AND_FABRIC_ROUTE_2026_07_02`

Objective:

Restore `reserve242` from degraded/stale to routable execution node.

Required scope:

1. Through a healthy fallback control node, verify whether `reserve242` host is powered, reachable on mesh, and allowed through firewall for Agent/Fabric listener port `9101`.
2. Restart or reinstall only the `reserve242` Agent Host/Fabric listener after preflight confirms the target path and service identity.
3. Register a fresh `reserve242` heartbeat with CPU/disk/RAM telemetry.
4. Repair the Fabric route/detail mismatch so `/v1/fabric/route target=reserve242` does not advertise a `/v1/nodes/reserve242` endpoint that returns 404.
5. Rerun read-only route, listener, heartbeat, and resource probes.

Dispatch guidance:

- Use fallback Fabric API `http://10.99.0.10:9101`.
- Prefer a fresh server-side worker such as `mesh-agent-21` or another healthy `mesh-agent-*`.
- Do not route workload to `reserve242` until the repair task proves fresh heartbeat and resource telemetry.
- Do not print secrets or use destructive git/runtime commands.
