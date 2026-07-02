# Safe Gate And Rollback

Task id: `P0_HOME_WALLBOARD_AUTOPILOT_VISIBILITY_2026_07_02`

Status: `safe_gate_ready`

Lease owner: `mesh-agent-03/autonomous_engineer`

Allowed action:

- Create or refresh a read-only tmux display session for Russian autopilot visibility.

Required safe gate before any live display mutation:

1. Confirm target is Home or approved fallback Agent Host, not Mac.
2. Confirm owner approval for creating/replacing session `kolibri-factory-screen`.
3. Confirm command is exactly read-only:

```bash
python3 /opt/kolibri-ai-platform/ops/home_wallboard_status_ru.py
```

4. Confirm the tmux command does not include `systemctl restart`, `systemctl start`, `systemctl stop`, `curl` to Telegram Bot API, `deleteWebhook`, token rotation, env dumps, or credential reads.
5. Run foreground preview once and check that no secrets are printed.

Approved tmux command after gate:

```bash
tmux new-session -d -s kolibri-factory-screen 'watch -n 10 python3 /opt/kolibri-ai-platform/ops/home_wallboard_status_ru.py'
```

Rollback:

```bash
tmux kill-session -t kolibri-factory-screen
```

Rollback effect:

- Stops only the terminal display session.
- Does not stop, start, or restart Kolibri production services.
- Does not mutate Telegram state.

