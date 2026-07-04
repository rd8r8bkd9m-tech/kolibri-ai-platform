# Tests

Required tests for this branch:

```bash
python3 -m py_compile ops/factory_control.py ops/agent_host.py ops/kolibri-dispatch ops/chatgpt_action_gateway.py
python3 -m pytest -q tests/test_fabric_control.py tests/test_factory_runtime.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime_queue_contracts.py tests/test_chatgpt_action_gateway.py
```

Observed result:

- `py_compile`: passed.
- Required pytest subset: `28 passed in 0.26s`.

FormulaLM parallel verification:

- Report: `/srv/kolibri/formulalm-tests/reports/formulalm_repro_eval_v1.json`.
- Questions: `10`.
- Aggregate score: `0.066391`.
- Exact: `0/10`.
- Contains: `0/10`.
