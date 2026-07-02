# Tests

## Commands Run

```bash
python3 -m pytest tests/test_fabric_control.py tests/test_factory_runtime.py -q
```

Result: `14 passed`.

```bash
python3 -m py_compile ops/factory_control.py ops/kolibri-dispatch
```

Result: passed.

```bash
./ops/kolibri-dispatch repair-plan --task-id-prefix P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02 --write-dir docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02
```

Result: live deployed Control Plane returned HTTP 404 for
`/v1/fleet/repair-plan`.

```bash
./ops/kolibri-dispatch repair-plan --local --submit --task-id-prefix P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02 --write-dir docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02
```

Result: generated 20 envelope files and submitted 20 live repair tasks.

```bash
python3 - <<'PY'
import json, urllib.request
nodes=['home','main','uiap','qjns','9fts','new','primary-candidate','agent-01','agent-02','agent-03','agent-04','agent-05','agent-06','agent-07','agent-08','agent-09','highload','paris','reserve242','server-kfrm']
base='http://10.99.0.2:9101/v1/tasks/'
counts={}
missing=[]
for node in nodes:
    suffix=node.upper().replace('-','_')
    tid=f'P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02-{suffix}'
    with urllib.request.urlopen(base+tid, timeout=10) as resp:
        task=json.loads(resp.read().decode())
    counts[task.get('state','unknown')]=counts.get(task.get('state','unknown'),0)+1
    if not task.get('task_id'):
        missing.append(tid)
print(json.dumps({'counts':counts,'missing':missing}, sort_keys=True))
PY
```

Result: `{"counts": {"queued": 20}, "missing": []}`.

## Coverage Added

- Canonical 20 repair-plan coverage.
- Blocked node creates fallback repair envelope and exact command.
- Mesh alias cards are treated as identity repair gaps.
- Dispatcher exposes the new `repair-plan` command.

