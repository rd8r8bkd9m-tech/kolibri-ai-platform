# Kolibri Thin-Client Dispatcher

Purpose: make this Mac a thin intelligent dispatcher for Kolibri Factory.

Operating rule:
- Mac thinks, plans, writes envelopes, submits tasks, watches status, collects
  artifacts, and summarizes results.
- Remote Factory executes implementation, heavy tests, validation, MIMO/API
  agents, server checks, and GitHub branch work.

Forbidden on Mac:
- Product implementation.
- Local feature development.
- Heavy test runs.
- Long-running workers or production local model jobs.
- Claims of remote completion without task ID, status, and artifacts.

Allowed on Mac:
- Read context and artifacts.
- Prepare task envelopes.
- Submit tasks through Control Plane or SSH-to-control-node.
- Maintain this command ledger.
- Record blockers and next dispatch commands.

Agent naming:
- Owner-facing agents must use Russian human names plus roles.
- Technical IDs remain audit metadata, not the primary display identity.

Current first remote task:
- `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30`
