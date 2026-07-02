# Next

Deploy on the Home host by copying the repo update, then run:

```bash
mkdir -p ~/.config/kolibri
cp ops/systemd/kolibri-home-screen.env.example ~/.config/kolibri/home-screen.env
systemctl --user daemon-reload
systemctl --user enable --now kolibri-home-screen.service
tmux attach -t kolibri-factory-screen
```

If user systemd is unavailable, use the direct reversible launcher:

```bash
ops/kolibri-home-screen start
tmux attach -t kolibri-factory-screen
```
