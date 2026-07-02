# Next

Run:

`P0_REPAIR_HOSTVDS_HIGHLOAD_AGENT_HOST_AND_ROUTE_SURFACE_2026_07_02`

Repair steps:

1. From a reachable server-side control node, diagnose `hostvds-highload` Agent Host service without printing secrets.
2. Restore the Agent Host under the correct node identity: `highload` or the intended canonical replacement for `mesh-highload`.
3. Verify fresh heartbeat, stable `agent_id`, and CPU/RAM/disk telemetry in `/v1/nodes`.
4. Submit or unblock a read-only probe and confirm highload acquires a lease.
5. Deploy or restart the current Control Plane route surface so `/v1/fleet/route`, `/v1/fabric/route`, `/v1/fabric/relay`, and `/v1/agents/tasks` are available.
6. Re-run highload readiness classification and only then add highload capacity back to scheduler pools.

