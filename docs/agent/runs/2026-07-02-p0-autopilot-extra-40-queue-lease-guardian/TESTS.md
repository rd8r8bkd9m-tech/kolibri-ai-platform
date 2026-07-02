# Queue Lease Guardian Tests

Commands run:

```bash
pytest tests/test_factory_runtime_queue_contracts.py tests/test_factory_runtime.py -q
```

Result: `13 passed in 0.13s`.

```bash
python3 -m py_compile ops/factory_control.py ops/kolibri-dispatch
```

Result: passed.

```bash
python3 ops/kolibri-dispatch guardian --help
```

Result: passed and showed `--create-repair-tasks`.

Note: `python` is not installed in this worker PATH; checks were rerun with `python3`.

