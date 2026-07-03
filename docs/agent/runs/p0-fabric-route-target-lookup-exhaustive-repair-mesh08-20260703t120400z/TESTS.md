# Tests

- `python3 -m py_compile ops/factory_control.py` passed.
- `python3 -m pytest -q tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py` passed: 15 passed.
- `python3 -m pytest -q` on the system interpreter was blocked during collection by missing dependencies: `pydantic` and `httpx`.
- Created a local `.test-venv`, installed `backend/requirements.txt` plus `pytest`, and reran full pytest.
- `.test-venv/bin/python -m pytest -q` passed: 172 passed, 1 warning in 41.77s.
