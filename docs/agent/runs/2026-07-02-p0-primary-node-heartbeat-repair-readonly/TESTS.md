# Tests

Commands run:

```bash
pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_agent_host_permission_contract.py
```

Result:

```text
13 passed in 0.17s
```

```bash
pytest -q tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_agent_host_permission_contract.py
```

Result:

```text
25 passed in 0.21s
```

Read-only live probes:

```bash
curl -fsS --max-time 5 http://10.99.0.10:9101/v1/health
curl -fsS --max-time 5 http://10.99.0.10:9101/v1/fabric/health
curl -fsS --max-time 5 http://10.99.0.10:9101/v1/nodes
curl -fsS --max-time 5 'http://10.99.0.10:9101/v1/fleet/route?target_node=primary-candidate'
curl -fsS --max-time 5 'http://10.99.0.10:9101/v1/fleet/route?target_node=primary-candidate&required_capability=generic_implementation'
curl -fsS --max-time 5 http://10.99.0.10:9101/v1/tasks/P0_PRIMARY_NODE_HEARTBEAT_REPAIR_READONLY_2026_07_02
```

No restart validation:

- No `systemctl restart` was run.
- No service mutation command was run.
- No Telegram state was touched.

