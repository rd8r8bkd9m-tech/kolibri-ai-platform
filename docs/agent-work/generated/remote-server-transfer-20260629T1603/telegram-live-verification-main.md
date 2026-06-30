# Telegram readable formatter rollout gate

Task: `KOL-REMOTE-SERVER-TASK-20260629T1603-002-MAIN-TELEGRAM`

Created: `2026-06-30T12:37:10Z`

Result reference: `docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-live-verification-main.md`

Control Plane annotation: succeeded; task `result_reference` was set to this markdown report while the task state was `running`.

## Implemented gate

- Added executable gate: `scripts/telegram_readable_rollout_gate.py`.
- Gate artifact: `docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-rollout-gate-report.json`.
- Formatter contract: raw JSON task responses are converted to owner-readable text or a safe fallback.
- Telegram transport contract: `sendMessage`, `editMessageText`, and photo captions use `parse_mode=HTML` with bounded escaping.
- Ownership contract: duplicate `getUpdates` HTTP 409 raises `TelegramConflictError`; the gate can run `--check-getupdates` during an exclusive rollout window.
- Rollback contract: pass `--rollback-command` or `TELEGRAM_ROLLBACK_COMMAND`; the gate runs it on failed checks and records the return code in the JSON report.

## Verification commands

- `python3 -m py_compile ops/telegram_gateway.py scripts/telegram_readable_rollout_gate.py`  
  Result: passed.
- `/tmp/kolibri-telegram-gate-venv/bin/python -m pytest -q tests/test_telegram_gateway.py tests/test_telegram_rollout_gate.py`  
  Result: `36 passed in 1.93s`.
- `scripts/telegram_readable_rollout_gate.py --live --report docs/agent-work/generated/remote-server-transfer-20260629T1603/telegram-rollout-gate-report.json`  
  Result: `pass=3 fail=0 skip=1`.
- `/tmp/kolibri-telegram-gate-venv/bin/python -m pytest -q`  
  Result: `65 passed, 1 warning in 7.91s`.
- `npm install` in `frontend/`  
  Result: passed, `found 0 vulnerabilities`; generated install artifacts were removed after verification.
- `npm run build` in `frontend/`  
  Result: passed; Vite reported the existing large chunk warning for a `501.37 kB` minified JS asset.

## Live Telegram fallback

Live Telegram verification could not be executed from this worker because `TELEGRAM_BOT_TOKEN` was not present. The executable gate wrote this fallback agent message into the JSON artifact:

`Telegram live verification unavailable: TELEGRAM_BOT_TOKEN is not present. Fallback artifact report was generated.`

Use this command on the rollout host when Telegram credentials are present and the gateway has an exclusive polling window:

```bash
scripts/telegram_readable_rollout_gate.py --live --check-getupdates --send-message --rollback-command 'systemctl restart kolibri-telegram-gateway'
```

## Residual risks

- The live `getUpdates` ownership probe should only run during an exclusive rollout window; otherwise it is expected to detect the active production poller and block rollout.
- No rollback command was configured in this worker, so rollback execution was prepared and covered by the gate contract but not invoked.
