# Tests

Commands run:

```text
hostname && uname -a
git rev-parse HEAD origin/main && git status --short --branch
systemctl is-active kolibri-telegram-gateway.service kolibri-factory-control.service kolibri-agent-host.service kolibri-mesh-control-bridge.service
systemctl show kolibri-telegram-gateway.service --property=LoadState,ActiveState,SubState,FragmentPath,ExecMainPID,ExecStart,User,WorkingDirectory --no-pager
for base in http://10.99.0.2:9101 http://10.99.0.10:9101 http://127.0.0.1:9101; do for path in /health /v1/health /v1/fabric/health /v1/fabric/routes /v1/fleet/nodes /v1/models; do curl --noproxy '*' -sS -o /tmp/kolibri_probe_body -w 'http=%{http_code}\n' --max-time 3 "$base$path"; done; done
./ops/kolibri-dispatch doctor
python3 -m pip show httpx
python3 -m pip install --user httpx
```

Verification to run after artifact writes:

```text
python3 -m json.tool docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/REMOTE_RESULT.json
git diff --check
test -f docs/agent/runs/2026-07-02-p0-post-merge-remote-canary-execution/NEXT_REMOTE_TASKS.md
test -f docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/PLAN.md
test -f docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/ACTIONS.md
test -f docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/TESTS.md
test -f docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/RESULT.md
test -f docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/NEXT.md
test -f docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/RUNTIME_BLOCKER_REPAIR_MATRIX.md
test -f docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/REMOTE_RESULT.json
rg --no-ignore -n '[0-9]{6,}:[A-Za-z0-9_-]{20,}|[A-Za-z0-9_]*(TOKEN|SECRET|PASSWORD|COOKIE|API_KEY|CHAT_ID)=[^ ]+' docs/agent/runs/2026-07-02-p0-post-merge-remote-canary-execution docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers && exit 1 || true
```

Current result:

- Source canary focused suite: `89 passed in 40.05s`.
- Repair worktree focused suite:
  `89 passed in 34.27s`.
- B3 freshness tests were not rerun successfully because dependency repair was
  blocked by the externally managed Python environment.
