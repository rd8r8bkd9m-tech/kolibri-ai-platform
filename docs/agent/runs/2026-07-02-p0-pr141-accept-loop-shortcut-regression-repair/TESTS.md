# Tests

Remote server verification on `primary-candidate`:

```text
python3 -m pytest tests/test_factory_capacity_controls.py -q
27 passed
```

```text
python3 -m pytest tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_control_runtime_import_path.py -q
18 passed
```

```text
python3 -m py_compile ops/factory_control.py
passed
```

```text
git diff --check
passed
```

Not run in this task:

- runtime deploy
- staged live canary `20/50/100/250/500/1000`
- PR #119 release gate
- MIMO/FormulaLM requeue

