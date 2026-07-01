# P0 Telegram Fleet Receiver Discovery Tests

## Verification Commands Run

```bash
python3 ops/kolibri-dispatch nodes
python3 ops/kolibri-dispatch status P0_TELEGRAM_FLEET_RECEIVER_DISCOVERY_2026_07_01
python3 ops/kolibri-dispatch status
systemctl show kolibri-telegram-gateway.service -p LoadState -p ActiveState -p SubState -p UnitFileState -p FragmentPath -p MainPID -p ExecMainPID -p ExecMainStatus -p ExecMainStartTimestamp --no-pager
ps -eo pid,ppid,user,stat,lstart,cmd --sort=pid
find /var/lib/kolibri-agent/artifacts /home/ladik/.kolibri-agent/artifacts -maxdepth 4
ssh root@10.99.0.2 '<safe receiver metadata probe>'
ssh root@10.99.0.10 '<safe receiver metadata probe>'
ssh root@10.99.0.5 '<safe receiver metadata probe>'
timeout 12s ssh root@31.57.27.128 'hostname; true'
timeout 12s ssh root@213.232.204.223 '<safe receiver metadata probe>'
timeout 12s ssh root@188.130.206.204 '<safe receiver metadata probe>'
python3 - <<'PY'
# redacted getWebhookInfo for local token
PY
ssh root@10.99.0.2 python3 - <<'PY'
# redacted getWebhookInfo for main token
PY
```

The broad `status` command produced a very large Control Plane task list; only
targeted task summaries are used in `ACTIONS.md` and `RESULT.md`.

## Required Artifact Checks

```bash
test -f docs/agent/runs/2026-07-01-p0-telegram-fleet-receiver-discovery/PLAN.md
test -f docs/agent/runs/2026-07-01-p0-telegram-fleet-receiver-discovery/ACTIONS.md
test -f docs/agent/runs/2026-07-01-p0-telegram-fleet-receiver-discovery/TESTS.md
test -f docs/agent/runs/2026-07-01-p0-telegram-fleet-receiver-discovery/RESULT.md
test -f docs/agent/runs/2026-07-01-p0-telegram-fleet-receiver-discovery/NEXT.md
git diff --check
git status --short
```

## Safety Verification

- No command invoked Telegram update consumption.
- No command invoked webhook mutation.
- No command invoked token rotation.
- No command deleted pending updates.
- No command stopped or restarted a service.
- No command printed token values, owner chat IDs, or private message text.
- The only file edits are the five required docs under the task write scope.

## Probe Results Summary

- `main` has a live `kolibri-telegram-gateway` process and a fresh state file.
- `home` / `home-live` has no visible active gateway process and no state file.
- `primary-candidate` was not directly accessible by SSH in this run; recent
  predecessor task evidence says the gateway was inactive/disabled.
- `mesh-9fts` has no gateway service or gateway state file.
- `mesh-agent-01` was inaccessible by SSH.
- `mesh-agent-02` and `mesh-agent-03` timed out on bounded SSH probes.
