# Tests

```bash
python3 -m py_compile ops/telegram_gateway.py ops/telegram_failover_guard.py
python3 -m pytest tests/test_telegram_gateway.py tests/test_telegram_failover_guard.py -q
```

Result:

```text
79 passed in 1.51s
```

Focused coverage added:

- `test_run_once_acknowledges_offset_only_after_successful_handling`
- `test_run_once_uses_redis_offset_and_polling_lease`
- `test_notification_spool_survives_send_failure_and_replays`
- `test_redact_secret_text_covers_tokens_assignments_and_redis_urls`
