# Tests

Passed locally:

```text
python3 -m py_compile ops/factory_control.py tests/test_factory_runtime.py
```

Passed focused harness:

```text
test_control_plane_runner_compatibility_filters_blocked_and_avoided_nodes: ok
test_owner_remote_task_without_runner_still_requires_default_mimo_runner: ok
test_runner_status_available_without_capability_does_not_satisfy_runner_route: ok
test_target_node_mimo_pool_task_only_leases_to_selected_pool_backing_node: ok
```

Passed:

```text
git diff --check
```

Passed in a temporary venv:

```text
/tmp/kolibri-pytest-venv/bin/python -m pytest -q tests/test_factory_runtime.py tests/test_agent_host_runner_contract.py tests/test_agent_host_direct_mimo.py
```

Result:

```text
44 passed in 22.72s
```

Note: the system Python did not have `pytest`; a temporary venv under `/tmp` was
used so the repository environment stayed clean.
