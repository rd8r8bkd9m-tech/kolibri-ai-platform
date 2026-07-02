# Runtime Blockers

| Task ID | Node | Status | Exact blocker | Result artifact |
|---|---:|---:|---|---|
| `P0_AUTOPILOT_50PCT_CAPACITY_GOVERNOR_2026_07_02` | `main` | `failed` | Codex runner authentication failed with HTTP 401/token refresh failure on `main`; capacity governor did not become active. | `/var/lib/kolibri-agent/artifacts/P0_AUTOPILOT_50PCT_CAPACITY_GOVERNOR_2026_07_02/P0_AUTOPILOT_50PCT_CAPACITY_GOVERNOR_2026_07_02-attempt-1/result.json` |
| `P0_AUTOPILOT_GUARDIAN_RUNNER_CONTRACT_STEWARD_2026_07_02` | `qjns` | `failed` | Codex executable is not available on `qjns`; runner-contract steward could not execute. | `/var/lib/kolibri-agent/artifacts/P0_AUTOPILOT_GUARDIAN_RUNNER_CONTRACT_STEWARD_2026_07_02/P0_AUTOPILOT_GUARDIAN_RUNNER_CONTRACT_STEWARD_2026_07_02-attempt-1/result.json` |
| `P0_AUTOPILOT_CANONICAL_20_SERVER_READINESS_MATRIX_2026_07_02` | `primary-candidate` | `queued` | Not blocked yet; waiting for lease. | `docs/agent/runs/2026-07-02-p0-autopilot-2h-50pct-launch-orchestrator/status-P0_AUTOPILOT_CANONICAL_20_SERVER_READINESS_MATRIX_2026_07_02.json` |
| `P0_AUTOPILOT_GUARDIAN_CONTROL_PLANE_STEWARD_2026_07_02` | `primary-candidate` | `queued` | Not blocked yet; waiting for lease. | `docs/agent/runs/2026-07-02-p0-autopilot-2h-50pct-launch-orchestrator/status-P0_AUTOPILOT_GUARDIAN_CONTROL_PLANE_STEWARD_2026_07_02.json` |
| `P0_AUTOPILOT_GUARDIAN_PR105_RELEASE_STEWARD_2026_07_02` | `qjns` | `queued` | At risk because qjns just proved runner unavailable for the runner-contract steward. | `docs/agent/runs/2026-07-02-p0-autopilot-2h-50pct-launch-orchestrator/status-P0_AUTOPILOT_GUARDIAN_PR105_RELEASE_STEWARD_2026_07_02.json` |

Decision: stay in `repair_only` until the 50% capacity governor is active or explicitly replaced by an equivalent governor on a healthy Agent Host.
