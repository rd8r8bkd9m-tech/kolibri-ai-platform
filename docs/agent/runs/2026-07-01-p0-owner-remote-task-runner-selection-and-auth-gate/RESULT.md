# Result

Status: implemented and verified.

Changed behavior:

- `owner_remote_task` is now supported by Agent Host.
- Requested `runner=mimo` invokes MIMO or returns structured `runner_auth_blocked` / `runner_unavailable`.
- Requested `runner=codex` invokes Codex or returns structured `runner_auth_blocked` / `runner_unavailable`.
- No silent MIMO-to-Codex fallback is present.
- Runner auth failures redact sensitive stderr/stdout content before persisted failure artifacts are written.
- Control Plane routes runner tasks only to nodes advertising the requested runner capability and not marked blocked, degraded, unavailable, or explicitly avoided.
- Telegram fallback node selection follows the same online and requested-runner capability gate.

Changed files:

- `ops/agent_host.py`
- `ops/factory_control.py`
- `ops/telegram_gateway.py`
- `tests/test_agent_host_runner_contract.py`
- `tests/test_factory_runtime.py`
- `tests/test_telegram_gateway.py`
- `docs/agent/AGENT_RUNNER_CONTRACT.md`
- `docs/agent/runs/2026-07-01-p0-owner-remote-task-runner-selection-and-auth-gate/`

Risks:

- Runner auth health is classified after a real runner execution failure; there is no credential probing, login, token refresh, or credential repair.
- Nodes without explicit `runner:<name>` capability will no longer lease requested-runner owner tasks.
