# Telegram Live Verification Main

- generated_at: `2026-06-29T16:28:06.584930+00:00`
- status: `PASS`
- task_id: `KOL-REMOTE-SERVER-TASK-20260629T1603-002B-MAIN-TELEGRAM-IMPLEMENTATION`
- result_reference: `/var/lib/kolibri-agent/worktrees/KOL-REMOTE-SERVER-TASK-20260629T1603-002B-MAIN-TELEGRAM-IMPLEMENTATION/KOL-REMOTE-SERVER-TASK-20260629T1603-002B-MAIN-TELEGRAM-IMPLEMENTATION-attempt-1/repo/docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md`

## Verification Commands

- `python3 ops/telegram_rollout_gate.py --report docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md --task-id KOL-REMOTE-SERVER-TASK-20260629T1603-002B-MAIN-TELEGRAM-IMPLEMENTATION --live-telegram`
- `git diff --check` -> `PASS` rc=0
- `git status --short` -> `PASS` rc=0
- `test -f docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md` -> `PASS` rc=0
- `python3 -m compileall -q ops tests` -> `PASS` rc=0
- `python3 -m pytest -q tests/test_telegram_gateway.py tests/test_agent_host_telegram_chat.py` -> `PASS` rc=0

## Gate Checks

- `no raw JSON in readable formatter`: `PASS`
  - formatted_message: Готово <b>безопасно</b> & понятно.
- `HTML escaping at Telegram payload boundary`: `PASS`
  - escaped_text: `5 &lt; 7 &amp; &lt;b&gt;raw&lt;/b&gt;`
- `duplicate getUpdates 409 ownership`: `PASS`
  - ownership_error: `telegram getUpdates conflict: another gateway instance owns the bot long poll`
- `rollback contract present`: `PASS`

## Telegram Availability

- status: `FALLBACK`
- reason: `TELEGRAM_BOT_TOKEN is not set`
- fallback_agent_message: Telegram is unavailable in this environment; use this artifact as the fallback agent-message/report.

## Control Plane Result Reference

- status: `PASS`
- result_reference: `/var/lib/kolibri-agent/worktrees/KOL-REMOTE-SERVER-TASK-20260629T1603-002B-MAIN-TELEGRAM-IMPLEMENTATION/KOL-REMOTE-SERVER-TASK-20260629T1603-002B-MAIN-TELEGRAM-IMPLEMENTATION-attempt-1/repo/docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md`

## Rollback

- `sudo systemctl stop kolibri-telegram-gateway.service`
- `cd /opt/kolibri-ai-platform && sudo git checkout HEAD~1 -- ops/telegram_gateway.py`
- `sudo install -m 0755 /opt/kolibri-ai-platform/ops/telegram_gateway.py /usr/local/bin/kolibri-telegram-gateway`
- `sudo systemctl start kolibri-telegram-gateway.service`
- `sudo journalctl -u kolibri-telegram-gateway.service -n 80 --no-pager`

## Command Output Tails

### git diff --check

- status: `PASS`

### git status --short

- status: `PASS`

```text
M ops/telegram_gateway.py
 M tests/test_telegram_gateway.py
?? docs/
?? ops/telegram_rollout_gate.py
```

### test -f docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md

- status: `PASS`

### python3 -m compileall -q ops tests

- status: `PASS`

### python3 -m pytest -q tests/test_telegram_gateway.py tests/test_agent_host_telegram_chat.py

- status: `PASS`

```text
......................................                                   [100%]
38 passed in 2.09s
```
