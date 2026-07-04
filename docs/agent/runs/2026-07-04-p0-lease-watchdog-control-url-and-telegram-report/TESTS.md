# Tests

Commands:

```bash
python3 -m py_compile ops/kfm_queue_steward.py
python3 -m pytest -q tests/test_kfm_queue_steward.py
KOLIBRI_FACTORY_CONTROL_URLS='http://10.99.0.2:9101,http://10.99.0.10:9101,http://10.99.0.1:9101' \
  KOLIBRI_KFM_STEWARD_TIMEOUT=4 \
  KOLIBRI_KFM_STEWARD_STATE_DIR=/tmp/kolibri-kfm-steward-smoke \
  python3 ops/kfm_queue_steward.py --diagnose-only
```

Observed:

- `py_compile`: passed.
- Unit tests: `6 passed in 0.08s`.
- Diagnose-only smoke: passed on retry.
- Queue mutation: none in smoke; `--diagnose-only` does not call `POST /v1/tasks`.
- Telegram mutation: none in smoke; `--notify` was not used.
