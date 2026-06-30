# Next

Recommended next task:

`P0_RERUN_INTEGRATION_CONTRACT_AUDIT_AFTER_AGENT_HOST_CONTRACT_HARDENING_2026_06_30`

Goal:

Deploy or run this hardened Agent Host contract in the server Control Plane
environment, then rerun the P0 integration contract audit that previously
drifted on artifact paths.

Constraints:

- Use server Control Plane for server-only scans.
- Do not push from no-push/read-only tasks.
- Preserve all dirty runtime diffs into safe artifacts before cleanup.
- Keep PRs split: runner contract hardening must not mix with frontend,
  billing, FormulaLM, Telegram UX, or server credential work.

Suggested acceptance:

- Agent Host reports blocked, not completed, when required audit artifacts are
  missing.
- Required audit artifacts are written to the expected paths.
- `result.json` includes all runner contract fields.
- Control Plane task state and artifact manifest agree.
