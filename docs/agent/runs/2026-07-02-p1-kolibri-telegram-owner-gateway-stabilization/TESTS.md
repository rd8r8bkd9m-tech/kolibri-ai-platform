# Tests

Command run:

```bash
pytest -q tests/test_telegram_gateway.py tests/test_agent_host_telegram_chat.py
```

Result:

```text
46 passed in 1.53s
```

Coverage notes:
- Fake Telegram command paths verify `/nodes`, `/agents`, and `/queue` do not expose raw node IDs, agent IDs, task IDs, process IDs, paths, or private queue item IDs.
- Fake Control Plane chat path verifies queue submission exceptions are converted into a redacted Russian owner message.
- Existing Agent Host chat tests verify codex/mimo runner prompt handling, no fixed greeting template, prompt redaction on runner failure, and JSONL response parsing.
