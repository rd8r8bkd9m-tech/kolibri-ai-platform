# Actions

- Added `ops/kolibri_home_screen.py` with panes for overview, tasks, agents, PR/CI, logs, blockers and owner instructions.
- Added `ops/kolibri-home-screen` wrapper.
- Added reversible user service `ops/systemd/kolibri-home-screen.service`.
- Added non-secret env example `ops/systemd/kolibri-home-screen.env.example`.
- Added focused tests in `tests/test_kolibri_home_screen.py`.

Owner command after deployment on Home:

```bash
tmux attach -t kolibri-factory-screen
```

Rollback:

```bash
ops/kolibri-home-screen stop
systemctl --user stop kolibri-home-screen.service
systemctl --user disable kolibri-home-screen.service
```
