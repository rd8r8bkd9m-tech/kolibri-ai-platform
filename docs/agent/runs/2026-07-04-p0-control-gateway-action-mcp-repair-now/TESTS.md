# TESTS

Passed:

```bash
python3 -m py_compile ops/chatgpt_action_gateway.py
python3 -m pytest -q tests/test_chatgpt_action_gateway.py
```

Result:

```text
9 passed in 0.09s
```

Passed wider requested suite:

```bash
python3 -m py_compile ops/chatgpt_action_gateway.py ops/factory_control.py ops/agent_host.py ops/kolibri-dispatch
python3 -m pytest -q tests/test_fabric_control.py tests/test_factory_runtime.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime_queue_contracts.py
```

Result:

```text
31 passed in 0.17s
```

OpenAPI YAML:

```bash
python3 - <<'PY'
import yaml
data = yaml.safe_load(open("docs/agent/runs/2026-07-04-p0-control-gateway-action-mcp-repair-now/CHATGPT_ACTION_OPENAPI.yaml"))
print(data["openapi"], len(data["paths"]))
PY
```

Result: OpenAPI `3.1.0`, 10 paths.

Note: `ruby` is not installed on this host, so Ruby YAML validation could not be used.
