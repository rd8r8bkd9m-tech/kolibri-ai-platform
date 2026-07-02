# Tests

Commands run:

```bash
python3 ops/kolibri-dispatch --control-url http://10.99.0.2:9101 status P0_AUTOPILOT_EXTRA_32_HOSTVDS_AGENT_10_READINESS_2026_07_02
python3 ops/kolibri-dispatch --control-url http://10.99.0.2:9101 nodes
python3 ops/kolibri-dispatch --control-url http://10.99.0.2:9101 fabric-route hostvds-agent-10 --required-capability implementation
python3 - <<'PY'
# filtered /v1/nodes probe for hostvds-agent-10, agent-10, mesh-agent-10
PY
python3 - <<'PY'
# /v1/fleet/route probe for hostvds-agent-10, agent-10, mesh-agent-10
PY
python3 ops/kolibri-dispatch --control-url http://10.99.0.2:9101 submit --file <redacted-temp-envelope>
python3 ops/kolibri-dispatch --control-url http://10.99.0.2:9101 status P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02
df -h . /var/lib/kolibri-agent
git status --short
git branch --show-current
git rev-parse --short HEAD
```

Results:

- Current task lease verified on `mesh-agent-32`.
- Live alias `mesh-agent-10` found in the node registry.
- `mesh-agent-10` is fresh, online, not draining, and has no active task before
  the child probe.
- Deployed Fabric route endpoints are not live: `/v1/fabric/route` and
  `/v1/fleet/route` returned `404`.
- Child probe successfully leased to `mesh-agent-10`, proving target Agent Host
  task leasing works.
- Child probe completed with `state=completed` and a result reference under
  `logical-workers/mesh-agent-10/artifacts`.
- Child target-local checks reported:
  - `gh auth status`: blocked because `gh` is not installed.
  - Disk: `/dev/vda1` ext4, `99G` size, `45G` used, `49G` available, `48%`.
  - Runner: no runner systemd unit, no runner process, and no install marker
    found under usual system paths.

No broad product test suite was run because this is a read-only readiness probe
and no product code was changed.
