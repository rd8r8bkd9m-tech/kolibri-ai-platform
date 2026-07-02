# TESTS

Verification commands run:

```bash
python3 -m json.tool docs/agent/dispatcher/envelopes/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02.json >/dev/null
python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_29_HOSTVDS_AGENT_07_READINESS_2026_07_02
python3 ops/kolibri-dispatch nodes
python3 ops/kolibri-dispatch fabric-route mesh-agent-07 --required-capability read_only_probe
python3 ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02.json
python3 ops/kolibri-dispatch status P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02
```

Results:

- JSON envelope validation: passed.
- Parent exact task status query: passed; task is running under `mesh-agent-29:agent-host-mesh-agent-29`.
- Node card query: passed; `mesh-agent-07` is online/fresh.
- Fabric route endpoint: failed with HTTP 404 on `/v1/fabric/route`; route endpoint is not available on this live Control Plane.
- Direct SSH alias probe: failed with timeout to `46.8.225.34:22`; non-blocking for API/mesh work, but a blocker for manual SSH repair.
- Child task submit: passed; task accepted by Control Plane.
- Child task lease: passed; leased to `mesh-agent-07:agent-host-mesh-agent-07`.
- Child result: completed. Result reference: `/var/lib/kolibri-agent/logical-workers/mesh-agent-07/artifacts/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02-attempt-1/result.json`.
- Child target checks: `gh` missing, `codex` present, `kolibri-agent-host.service` active/enabled, `kolibri-factory-control.service` active/enabled, route reachable on `10.99.0.10:9101`, localhost `127.0.0.1:9101` not answering.

No product test suite was run because this was a read-only readiness probe, not a code change.
