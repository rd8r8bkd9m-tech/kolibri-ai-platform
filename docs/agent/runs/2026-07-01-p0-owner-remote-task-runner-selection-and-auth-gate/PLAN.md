# Plan

Task: `P0_OWNER_REMOTE_TASK_RUNNER_SELECTION_AND_AUTH_GATE_2026_07_01`

Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`

PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/83

1. Start from PR #83 head `81daf44dc842dce40d8547275f47b051871a2690`.
2. Inspect Agent Host requested-runner execution, Control Plane node compatibility, and Telegram fallback selection.
3. Implement strict `owner_remote_task` runner dispatch for `mimo` and `codex`.
4. Classify `runner_auth_blocked` and `runner_unavailable` without credential repair or secret output.
5. Mark runner-broken nodes blocked or unavailable for future scheduler leases.
6. Verify focused runner, Agent Host chat/runner, Control Plane, and Telegram gateway suites.
