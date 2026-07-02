# PR83 Agent Host Deploy Gate And Runtime Canary

Date: 2026-07-02

This is the exact deployment path for the PR #83 Agent Host runner contract.
It turns the checked-in contract into a canaryable runtime handoff for
`kolibri-agent-host.service`.

## Merge Gate

Run these before owner-approved merge or before deploying an already-merged
`main` checkout:

```bash
python3 -m py_compile ops/agent_host.py
python3 -m pytest tests/test_agent_host_runner_contract.py -q
bash scripts/preflight-agent-host-runtime.sh .
```

Required result:

- `tests/test_agent_host_runner_contract.py`: all tests pass.
- `scripts/preflight-agent-host-runtime.sh`: prints
  `agent_host_pr83_runtime_preflight=ok`.
- No secrets are printed.
- No push to `main`, force push, auto-merge, or service restart happens during
  this merge gate.

## Canary Deploy

Deploy one Agent Host canary node only:

```bash
AGENT_HOST_TARGET=kolibri-main ./scripts/deploy.sh agent-host
```

Optional overrides:

```bash
AGENT_HOST_REPO=/opt/kolibri-ai-platform
AGENT_HOST_LAUNCHER=/usr/local/bin/kolibri-agent-host
AGENT_HOST_SERVICE=kolibri-agent-host.service
```

The deploy target performs this sequence on the remote host:

1. Fast-forward `main` in `AGENT_HOST_REPO`.
2. Run `./scripts/preflight-agent-host-runtime.sh "$AGENT_HOST_REPO"` against
   the source tree.
3. Back up the existing launcher under
   `/var/backups/kolibri-agent-host/<utc timestamp>/kolibri-agent-host`.
4. Install `ops/agent_host.py` to `AGENT_HOST_LAUNCHER`.
5. Run the preflight again with
   `KOLIBRI_AGENT_HOST_REQUIRE_LAUNCHER=1`, proving the installed launcher has
   the PR #83 contract.
6. Restart `kolibri-agent-host.service`.
7. Require `systemctl is-active --quiet kolibri-agent-host.service`.
8. Run the launcher-required preflight once more after restart.

The deploy command prints `agent_host_backup:<backup_dir>` on success.

## Rollback

Automatic rollback is installed for deploy failures after backup creation. If a
manual rollback is needed, use the backup path printed by the deploy command:

```bash
sudo cp /var/backups/kolibri-agent-host/<utc timestamp>/kolibri-agent-host /usr/local/bin/kolibri-agent-host
sudo chmod 0755 /usr/local/bin/kolibri-agent-host
sudo systemctl restart kolibri-agent-host.service
sudo systemctl is-active --quiet kolibri-agent-host.service
```

Then rerun:

```bash
KOLIBRI_AGENT_HOST_REQUIRE_LAUNCHER=1 \
KOLIBRI_AGENT_HOST_LAUNCHER=/usr/local/bin/kolibri-agent-host \
bash /opt/kolibri-ai-platform/scripts/preflight-agent-host-runtime.sh /opt/kolibri-ai-platform
```

## Runtime Canary Meaning

The canary imports the source Agent Host and, when required, the installed
launcher. It verifies that:

- all required Control Plane runner result fields exist;
- `git_push_forbidden`, `no_push`, and `read_only` block publishing;
- `AgentHost.git_push_after_contract_verification` exists;
- a missing required artifact produces `status=blocked` with
  `push_attempted=false`;
- a valid `no_push` task can complete while reporting `push_blocked=true`.

After this passes on the canary node, the owner can repeat
`./scripts/deploy.sh agent-host` for the next Agent Host node under the same
backup and rollback procedure.
