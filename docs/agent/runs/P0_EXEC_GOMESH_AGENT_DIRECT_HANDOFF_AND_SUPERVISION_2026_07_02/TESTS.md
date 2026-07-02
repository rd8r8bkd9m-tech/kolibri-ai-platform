# Tests

Verification commands run:

```bash
sed -n '1,240p' /root/.codex/skills/kolibri-gomesh-gateway/SKILL.md
git status --short --branch
rg --files
python3 - <<'PY'
import urllib.request
for url in [
    'http://127.0.0.1:9101/v1/health',
    'http://127.0.0.1:9101/v1/fabric/health',
    'http://127.0.0.1:9101/v1/nodes',
    'http://127.0.0.1:9101/v1/fleet/nodes',
]:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            print(url, r.status)
    except Exception as e:
        print(url, type(e).__name__)
PY
python3 - <<'PY'
import urllib.request
bases = ['http://10.99.0.2:9101', 'http://10.99.0.10:9101', 'http://control.kolibri.internal:9101']
paths = ['/health', '/v1/health', '/v1/fabric/health', '/v1/fleet/nodes', '/v1/fleet/route']
for base in bases:
    for path in paths:
        try:
            with urllib.request.urlopen(base + path, timeout=4) as r:
                print(base + path, r.status)
        except Exception as e:
            print(base + path, type(e).__name__)
PY
python3 -m py_compile ops/factory_control.py ops/agent_host.py
python3 -m pytest tests/test_prompt3_fabric_api_surface.py tests/test_agent_host_direct_mimo.py -q
git diff --check
test -f docs/agent/runs/P0_EXEC_GOMESH_AGENT_DIRECT_HANDOFF_AND_SUPERVISION_2026_07_02/PLAN.md
test -f docs/agent/runs/P0_EXEC_GOMESH_AGENT_DIRECT_HANDOFF_AND_SUPERVISION_2026_07_02/ACTIONS.md
test -f docs/agent/runs/P0_EXEC_GOMESH_AGENT_DIRECT_HANDOFF_AND_SUPERVISION_2026_07_02/TESTS.md
test -f docs/agent/runs/P0_EXEC_GOMESH_AGENT_DIRECT_HANDOFF_AND_SUPERVISION_2026_07_02/RESULT.md
test -f docs/agent/runs/P0_EXEC_GOMESH_AGENT_DIRECT_HANDOFF_AND_SUPERVISION_2026_07_02/NEXT.md
```

Expected live-route result:

- `10.99.0.10:9101` is the usable Fabric API route for this handoff.
- The stale listeners are not suitable for `/v1/agents/tasks` dispatch.

Expected queue result:

- `P0_GOMESH_OWNER_RULES_MONITOR_REVIEW_LOOP_2026_07_02` exists in the control plane.
- It is queued until `primary-candidate:agent-host-primary` leases it.
