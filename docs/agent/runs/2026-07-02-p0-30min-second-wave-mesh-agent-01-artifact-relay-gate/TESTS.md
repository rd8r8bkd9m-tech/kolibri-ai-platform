# Tests

Verification command:

```bash
python3 -m pytest tests/test_prompt3_fabric_api_surface.py tests/test_factory_control_runtime_import_path.py tests/test_factory_runtime_queue_contracts.py -q
```

Result:

```text
.............                                                            [100%]
13 passed in 0.44s
```

Coverage rationale:

- `tests/test_prompt3_fabric_api_surface.py` covers Fabric API relay/artifact aliases and task artifact envelope behavior.
- `tests/test_factory_control_runtime_import_path.py` covers the runtime import path repaired before the current relay wave.
- `tests/test_factory_runtime_queue_contracts.py` covers queue/task contract shape used by dispatcher relay tasks.

Not run:

- Full repository test suite. This task is a documentation/artifact release relay gate, and the focused suite covers the changed surface without broad dependency noise.
