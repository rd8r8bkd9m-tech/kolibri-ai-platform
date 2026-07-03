# Next

After merge, deploy the Agent Host update through the normal controlled path and restart the managed service from the host supervisor environment.

Recommended follow-up checks:

- Submit a small `owner_remote_task` with an empty assigned worktree and a required artifact under `docs/agent/runs/...`.
- Confirm the runner prompt names the exact required path.
- Confirm completion includes `required_artifacts_present` and no `required_artifacts_missing`.
- Confirm no run artifacts are written at repository root.
