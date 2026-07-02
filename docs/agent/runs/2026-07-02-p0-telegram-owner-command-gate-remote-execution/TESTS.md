# Tests

Commands run:

```bash
hostname && uname -a && python3 --version
```

Result: passed. Node reported `kolibri`, Linux server kernel, Python 3.12.3.

```bash
python3 - <<'PY'
# Inline fake Agent Host execution probe.
# Uses fake Control Plane post(), fake Telegram source metadata, and fake runner output.
PY
```

Result: passed. Probe summary:

```json
{"blockers": [], "node_id": "kolibri-server-agent-host", "state": "completed"}
```

Final verification commands:

```bash
python3 -m py_compile ops/agent_host.py ops/factory_control.py ops/telegram_gateway.py
python3 -m pytest tests/test_agent_host_runner_contract.py tests/test_agent_host_telegram_chat.py tests/test_telegram_gateway.py -q
test -f docs/agent/runs/2026-07-02-p0-telegram-owner-command-gate-remote-execution/PLAN.md
test -f docs/agent/runs/2026-07-02-p0-telegram-owner-command-gate-remote-execution/ACTIONS.md
test -f docs/agent/runs/2026-07-02-p0-telegram-owner-command-gate-remote-execution/TESTS.md
test -f docs/agent/runs/2026-07-02-p0-telegram-owner-command-gate-remote-execution/RESULT.md
test -f docs/agent/runs/2026-07-02-p0-telegram-owner-command-gate-remote-execution/NEXT.md
test -f docs/agent/runs/2026-07-02-p0-telegram-owner-command-gate-remote-execution/REMOTE_RESULT.json
rg --no-ignore -n '[0-9]{6,}:[A-Za-z0-9_-]{20,}|[A-Za-z0-9_]*(TOKEN|SECRET|PASSWORD|COOKIE|API_KEY|CHAT_ID)=[^ ]+' docs/agent/runs/2026-07-02-p0-telegram-owner-command-gate-remote-execution && exit 1 || true
```

Results:

- `python3 -m py_compile ops/agent_host.py ops/factory_control.py ops/telegram_gateway.py`: passed.
- `python3 -m pytest tests/test_agent_host_runner_contract.py tests/test_agent_host_telegram_chat.py tests/test_telegram_gateway.py -q`: 75 passed in 34.00s.
- Exact artifact existence checks: passed.
- Secret-pattern scan over this run directory: passed.
- `git diff --check`: passed.
