# Next

Task id: `P0_HOME_WALLBOARD_AUTOPILOT_VISIBILITY_2026_07_02`

Status: `next_action_required`

Lease owner: `mesh-agent-03/autonomous_engineer`

Next exact action:

1. Decide display target: Home preferred, fallback Agent Host `kolibri` acceptable.
2. On the selected target, confirm repo path exists and contains `ops/home_wallboard_status_ru.py`.
3. Run one foreground preview:

```bash
python3 /opt/kolibri-ai-platform/ops/home_wallboard_status_ru.py
```

4. If preview is clean and owner approves a terminal display session, create or refresh tmux session:

```bash
tmux new-session -d -s kolibri-factory-screen 'watch -n 10 python3 /opt/kolibri-ai-platform/ops/home_wallboard_status_ru.py'
tmux attach -t kolibri-factory-screen
```

Follow-up engineering task:

- Repair the public status adapter so `/api/factory/status` exposes live control-plane node/task totals instead of zero totals when the control plane is available.

Do not do next:

- Do not restart production services for this visibility-only task.
- Do not mutate Telegram webhook, polling, command menu, BotFather, chat, or token state.
- Do not print environment files or secrets.

