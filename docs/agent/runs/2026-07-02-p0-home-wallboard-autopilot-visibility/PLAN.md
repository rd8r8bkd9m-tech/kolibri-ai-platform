# Plan

Task id: `P0_HOME_WALLBOARD_AUTOPILOT_VISIBILITY_2026_07_02`

Status: `implemented_with_visibility_blocker`

Lease owner: `mesh-agent-03/autonomous_engineer`

Target: server Agent Host `kolibri`; Home remains the preferred display, with this Agent Host as fallback.

Goal: make Russian Home or fallback terminal visibility plan/status for Kolibri Factory autopilot, verify Home-facing services and public status path, and avoid live restarts or Telegram mutation.

Steps:

1. Prove execution is on server Agent Host, not Mac.
2. Add a reusable read-only Russian terminal status renderer for Home/fallback tmux.
3. Verify control-plane health, node/task routes, service state, and public status path.
4. Record a safe gate and rollback for any future live wallboard attachment.
5. Record artifacts, blockers, and next action without printing secrets.

Safety:

- No `systemctl restart/start/stop` was run.
- No Telegram Bot API calls or Telegram state mutations were run.
- No secrets, tokens, cookies, private keys, or environment values are printed in artifacts.
- No push to `main`, no force push, no destructive git.

