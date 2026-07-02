# Tests

Executed verification:

- `python3 -m py_compile backend/main.py backend/factory_status.py`
  - Result: passed.
- `.venv/bin/python -m py_compile backend/main.py backend/factory_status.py`
  - Result: passed.
- `.venv/bin/python -m pytest tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py tests/test_factory_panel_proxy_contract.py -q`
  - Result: passed, `11 passed in 1.28s`.
- `bash -n scripts/deploy.sh`
  - Result: passed.
- `curl -k -sS -o /tmp/kolibri-factory-status-after.json -w '%{http_code}\n' https://kolibriai.ru/api/factory/status`
  - Result: HTTP `400` from current public edge. This confirms production has not yet received this branch/config change.
- `curl -k -sS -o /tmp/kolibri-panel-after.html -w '%{http_code}\n' 'https://kolibriai.ru/?telegram=1'`
  - Result: HTTP `200`.

Notes:

- The worker image did not have backend dependencies or pytest installed. A temporary local `.venv` was created for verification, then removed before final status.
