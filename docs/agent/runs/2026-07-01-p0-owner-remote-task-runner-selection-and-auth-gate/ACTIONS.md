# Actions

- Aligned the local branch to PR #83 head `81daf44dc842dce40d8547275f47b051871a2690` before editing.
- Added `owner_remote_task` support to `ops/agent_host.py`.
- Centralized AI runner command construction so requested `runner=mimo` invokes MIMO and requested `runner=codex` invokes Codex.
- Added structured `runner_auth_blocked` and `runner_unavailable` failures with redaction of sensitive runner output.
- Added Agent Host runner health metadata in node register, heartbeat, and lease requests.
- Added Control Plane compatibility checks for `runner:<name>` capabilities, avoided nodes, and blocked/degraded runner state.
- Added Control Plane node runner-state updates on runner auth/unavailable failures.
- Added Telegram fallback node selection that only targets online, non-draining nodes advertising the requested runner capability.
- Updated `docs/agent/AGENT_RUNNER_CONTRACT.md` to document strict owner task runner behavior.
