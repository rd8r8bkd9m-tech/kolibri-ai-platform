# P0 Package Manager Law Publish PR Gate Tests

Focused checks run from branch `codex/p0_factory_package_manager_law_and_gate_primary_20260703t101100z`:

```text
python3 -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py
python3 -m pytest tests/test_agent_host_runner_contract.py -q
git diff --check
```

Result:

```text
37 passed in 40.87s
```

No packages were installed.
