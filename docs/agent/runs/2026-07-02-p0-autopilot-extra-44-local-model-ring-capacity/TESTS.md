# Tests

Verification commands run or planned for this docs-only inventory:

```bash
hostname
whoami
date -u +%Y-%m-%dT%H:%M:%SZ
```

Result:

- `hostname`: `kolibri`
- `whoami`: `root`
- timestamp captured: `2026-07-02T02:55:43Z`

```bash
curl -fsS --max-time 3 http://127.0.0.1:8080/v1/fabric/health || curl -fsS --max-time 3 http://127.0.0.1:8000/v1/fabric/health || true
curl -fsS --max-time 3 http://127.0.0.1:8080/v1/nodes || curl -fsS --max-time 3 http://127.0.0.1:8000/v1/nodes || true
```

Result:

- `127.0.0.1:8080`: connection refused.
- `127.0.0.1:8000`: `404` for both checked paths.
- No secret-bearing endpoint or environment dump was used.

Final artifact checks:

```bash
test -f docs/agent/runs/2026-07-02-p0-autopilot-extra-44-local-model-ring-capacity/PLAN.md
test -f docs/agent/runs/2026-07-02-p0-autopilot-extra-44-local-model-ring-capacity/ACTIONS.md
test -f docs/agent/runs/2026-07-02-p0-autopilot-extra-44-local-model-ring-capacity/LOCAL_MODEL_RING_CAPACITY.md
test -f docs/agent/runs/2026-07-02-p0-autopilot-extra-44-local-model-ring-capacity/TESTS.md
test -f docs/agent/runs/2026-07-02-p0-autopilot-extra-44-local-model-ring-capacity/RESULT.md
test -f docs/agent/runs/2026-07-02-p0-autopilot-extra-44-local-model-ring-capacity/NEXT.md
git diff --check -- docs/agent/runs/2026-07-02-p0-autopilot-extra-44-local-model-ring-capacity
```

