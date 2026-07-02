# Next

Exact next task:

`P0_SAFE_REMOTE_AGENT_LAUNCH_WAVE_01_2026_07_02`

Objective:

Submit the prepared read-only launch wave through Control Plane to fresh
healthy Agent Host/control nodes. Each target must report deployed repo/commit,
Agent Host capabilities, Factory Control route health, Telegram receiver
ownership status without mutation, GitHub/tooling readiness, dependency status,
capacity gates, and exact blockers. Do not start services, restart services,
mutate Telegram, merge PRs, rotate credentials, or fan out write-capable tasks.

Prepared envelope:

`docs/agent/dispatcher/envelopes/P0_SAFE_REMOTE_AGENT_LAUNCH_WAVE_01_2026_07_02.json`

Required acceptance:

- Remote execution happens on server/control nodes.
- First-wave work is read-only/probe-only.
- Results include exact five canonical run artifacts.
- Runtime mutation follow-ups are created only as separate gated tasks.
- Any blocker is classified with evidence and without secrets.
