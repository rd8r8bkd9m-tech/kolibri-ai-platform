# Next

Next exact task:

`P0_INSTALL_GH_AND_RUN_RELEASE_TRAIN_BOT_DRY_RUN_2026_07_02`

Task command:

```bash
sudo apt-get update && sudo apt-get install -y gh && gh auth status
python3 ops/github_release_train_bot.py --repo /opt/kolibri-ai-platform --update-bodies
```

If the dry run is clean and owner approval is explicit, apply only the allowed
release-train mutations:

```bash
python3 ops/github_release_train_bot.py --repo /opt/kolibri-ai-platform --apply --update-bodies --repair-task-mode artifact
```

Do not merge, approve, mark ready, close PRs, force push, or push to `main`.

