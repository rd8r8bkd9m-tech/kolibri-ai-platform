# Tests

Verification run from repository root:

```bash
python3 -m json.tool docs/agent/dispatcher/envelopes/P0_SAFE_REMOTE_AGENT_LAUNCH_WAVE_01_2026_07_02.json >/tmp/kolibri-safe-launch-envelope.json
```

Result: passed.

```bash
python3 -m compileall -q ops backend
```

Result: passed.

```bash
python3 -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_agent_host_permission_contract.py tests/test_agent_host_runner_contract.py
```

Result: passed, `37 passed`.

```bash
git diff --check -- docs/agent/runs/2026-07-02-p0-30min-mesh-agent-03-agent-launch-accelerator docs/agent/intelligence/2026-07-02-mesh-agent-03-agent-launch-accelerator docs/agent/dispatcher/envelopes/P0_SAFE_REMOTE_AGENT_LAUNCH_WAVE_01_2026_07_02.json
```

Result: passed.
