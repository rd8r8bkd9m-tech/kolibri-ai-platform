# P0 Control Plane Task Index Artifact Relay Tests

All commands were run from:

`/var/lib/kolibri-agent/logical-workers/mesh-agent-08/worktrees/P0_CONTROL_PLANE_TASK_INDEX_ARTIFACT_RELAY_MESH08_20260703T091232Z/P0_CONTROL_PLANE_TASK_INDEX_ARTIFACT_RELAY_MESH08_20260703T091232Z-attempt-1/repo`

## Focused Regression

Command:

```bash
python3 -m pytest tests/test_factory_runtime.py -q
```

Result:

```text
.........                                                                [100%]
9 passed in 0.11s
```

## Adjacent Control Plane Contracts

Command:

```bash
python3 -m pytest tests/test_prompt3_fabric_api_surface.py tests/test_factory_control_superfactory.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py -q
```

Result:

```text
................                                                         [100%]
16 passed in 0.16s
```

## Syntax Check

Command:

```bash
python3 -m py_compile ops/factory_control.py
```

Result: passed.

## Whitespace Check

Command:

```bash
git diff --check
```

Result: passed.
