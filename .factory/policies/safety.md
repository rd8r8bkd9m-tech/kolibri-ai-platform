# Safety Policy

- Do not put API keys, passwords, SSH keys, VPN credentials, provider tokens, or
  auth databases into prompts, Git, logs, reports, or artifacts.
- Do not read `.env`, `.ssh`, `.mimocode`, `auth.json`, token stores, or private
  provider config unless a dedicated human-approved security task requires it.
- Do not use `--dangerously-skip-permissions`.
- Do not run broad process kills: `pkill -f python`, `pkill -f formulalm`,
  `killall python`, or equivalent broad targets.
- Do not run `rm -rf` outside a task-owned run directory.
- Do not mutate source datasets.
- Do not restart production, edit firewall, SSH, IAM, DNS, billing, or deploy
  without explicit human approval.
- Long-running tasks must write an exact PID file:
  `/dev/shm/<factory_run_id>_<task_id>.pid`.
- To stop a task, verify the PID command line contains the exact task id before
  sending SIGTERM. Use SIGKILL only for that exact PID after SIGTERM fails.
