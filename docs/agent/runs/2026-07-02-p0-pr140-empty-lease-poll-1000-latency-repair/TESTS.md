# TESTS

Passed on `primary-candidate`:

- `python3 -m pytest tests/test_factory_capacity_controls.py` -> `22 passed`
- `python3 -m pytest tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_control_runtime_import_path.py tests/test_factory_control_superfactory.py` -> `20 passed`
- `bash scripts/preflight-factory-control-runtime.sh` -> `factory_control_runtime_preflight=ok`

Blocked/non-gating:

- `python3 -m pytest` stopped during collection because this environment lacks optional backend dependencies:
  - `pydantic` for `backend/tests/test_estimate_document_pdf_engines.py`
  - `httpx` for `backend/tests/test_factory_status_fast_health.py` and `tests/test_factory_status.py`

Notes:

- `python` is not installed; verification used `python3`.
- Runtime canary was not run.
- Runtime deployment was not performed.
