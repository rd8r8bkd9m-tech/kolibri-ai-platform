# Tests

Remote verification reported:

```text
python3 -m pytest -q tests/test_factory_control_runtime_import_path.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_control_superfactory.py
16 passed

python3 -m py_compile ops/factory_control.py ops/telegram_superfactory.py
git diff --check
bash scripts/preflight-factory-control-runtime.sh "$PWD"
factory_control_runtime_preflight=ok
```

Control Plane wrapper verification also ran:

```text
git diff --check
python3 -m py_compile ops/factory_control.py
python3 -m pytest tests/test_factory_control*.py tests/test_factory_runtime*.py -q
20 passed in 0.39s
```

Wrapper failure:

```text
test -f docs/agent/runs/2026-07-02-p0-factory-control-runtime-import-path-repair/PLAN.md
```

The failure was an exact artifact contract miss, not a focused test failure.

