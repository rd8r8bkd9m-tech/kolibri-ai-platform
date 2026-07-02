# Actions

Run window: `2026-07-02T00:50:59Z` to `2026-07-02T00:52:05Z`

Repository state:

- Branch: `agent/P0_30MIN_SECOND_WAVE_PRIMARY_RELEASE_GATE_2026_07_02/generic`
- `HEAD`: `f7ac32c70406432a52752ca45d87e35d9f1facd3`
- `origin/main`: `f7ac32c70406432a52752ca45d87e35d9f1facd3`
- Latest commit: `f7ac32c docs: dispatch factory control deploy canary (#104)`
- Initial worktree: clean.

Executed checks:

- Ran broad Python test collection to identify environment blockers.
- Ran focused runtime/factory Python release gate suite.
- Ran `git diff --check`.
- Ran Python bytecode compilation for key runtime modules.
- Ran `scripts/preflight-factory-control-runtime.sh`.
- Ran frontend mobile layout guard.
- Attempted frontend build.
- Attempted frontend generic test script.
- Probed live Factory Control routes:
  - `/health`
  - `/v1/health`
  - `/v1/fabric/health`
  - `/v1/fabric/routes`
  - `/v1/fleet/nodes`
  - `/v1/models`
- Checked non-secret systemd state for:
  - `kolibri-factory-control.service`
  - `kolibri-telegram-gateway.service`
- Computed 30-minute fleet freshness from heartbeat timestamps returned by
  `/v1/fleet/nodes`.

Safety notes:

- No logs containing secrets were read.
- No Telegram Bot API request was made.
- No service was restarted.
- No runtime file was installed.
- No product code was changed.
