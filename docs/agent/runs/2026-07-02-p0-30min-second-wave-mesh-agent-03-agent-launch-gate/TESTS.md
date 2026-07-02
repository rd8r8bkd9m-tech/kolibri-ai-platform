# Tests

Task id: `P0_30MIN_SECOND_WAVE_MESH_AGENT_03_AGENT_LAUNCH_GATE_2026_07_02`

## Control Plane Checks

```bash
python3 ops/kolibri-dispatch --control-url http://10.99.0.2:9101 doctor
```

Result: passed for repository, binaries and Control Plane health. Control Plane
reported `status=ok`, Redis `PONG`. `gh` was not installed, and legacy direct
SSH probes for `9fts` and `new` timed out; those were classified as node/tooling
limitations, not launch approvals.

```bash
python3 ops/kolibri-dispatch --control-url http://10.99.0.2:9101 nodes
```

Result: passed. `mesh-agent-03` was fresh/online and leased to this task.
Fresh target classification was recorded in `RESULT.md` and
`SAFE_AGENT_LAUNCH_WAVE.md`.

```bash
python3 ops/kolibri-dispatch --control-url http://10.99.0.2:9101 status P0_30MIN_SECOND_WAVE_MESH_AGENT_03_AGENT_LAUNCH_GATE_2026_07_02
```

Result: passed. Task state was `running`, lease owner was
`mesh-agent-03:agent-host-mesh-agent-03`.

## Artifact Checks

```bash
git diff --check
```

Result: passed.

```bash
for f in PLAN.md ACTIONS.md RESULT.md NEXT.md SAFE_AGENT_LAUNCH_WAVE.md REMOTE_RESULT.json; do
  test -f "docs/agent/runs/2026-07-02-p0-30min-second-wave-mesh-agent-03-agent-launch-gate/$f" || exit 1
done
```

Result: passed.

```bash
python3 -m json.tool docs/agent/runs/2026-07-02-p0-30min-second-wave-mesh-agent-03-agent-launch-gate/REMOTE_RESULT.json >/dev/null
```

Result: passed.

## Secret-Pattern Scan

```bash
rg -n -i "(token|secret|password|passwd|api[_-]?key|authorization|bearer|cookie|private key|owner_chat|chat_id)" docs/agent/runs/2026-07-02-p0-30min-second-wave-mesh-agent-03-agent-launch-gate || true
```

Result: policy-word matches only. No secret values, tokens, keys, cookies, raw
environment output, or owner chat ids were present.
