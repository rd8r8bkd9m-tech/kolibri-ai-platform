# PR85 API Fabric Gate Tests

Commands run on node `kolibri`:

```bash
git diff --check origin/main...origin/p0/api-first-full-control-fabric-2026-07-01
```

Result: passed, no whitespace errors.

```bash
python3 -m py_compile ops/factory_control.py ops/kolibri-dispatch backend/main.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_agent_host_direct_mimo.py
```

Result: passed.

```bash
python3 -m pytest tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_agent_host_direct_mimo.py -q
```

Result: passed, `14 passed in 0.19s`.

```bash
python3 -m pytest -q
```

Result: blocked during collection by missing worker dependencies, not by the Fabric gate:

- `ModuleNotFoundError: No module named 'pydantic'`
- `ModuleNotFoundError: No module named 'httpx'`

Classification:

- Focused PR #85 Fabric/API surface tests: green.
- PR #91 direct MIMO dependency regression tests: green.
- Full-suite result: environment dependency blocker on this worker.
