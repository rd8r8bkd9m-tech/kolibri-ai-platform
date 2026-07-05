# Tests

Server-side verification reported by
`P0_PR89_TELEGRAM_SUPERFACTORY_CANONICAL_ARTIFACTS_2026_07_01`:

- `python3 -m pytest tests/test_telegram_superfactory_miniapp.py`:
  `2 passed`.
- Related Telegram/factory subset:
  `55 passed`.
- `python3 -m py_compile $(rg --files -g '*.py')`:
  passed.
- `git diff --check`:
  passed.
- Branch push:
  `5b93b0c..041ea9c` to
  `p0/telegram-superfactory-bot-miniapp-2026-07-01`.

GitHub verification:

- Commit `5b93b0c1ecef23324d3bb78657ab7eec25dd7ea5`:
  `Kolibri CI` run `28492581310`, conclusion `success`.
- Commit `041ea9ca5e27f6826450ff20b340c018b474eeed`:
  `Kolibri CI` run `28493020282`, conclusion `success`.

Known blocker:

- A broader server-side suite that included factory status tests could not
  collect because `httpx` was not installed in that server environment. The
  task classified this as an environment dependency blocker, not a Telegram
  runtime regression.

Mac-local heavy tests were not run. The Mac acted only as a thin dispatcher and
artifact relay.
