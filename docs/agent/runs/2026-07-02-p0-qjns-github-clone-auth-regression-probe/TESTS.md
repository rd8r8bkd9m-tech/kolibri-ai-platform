# Tests And Probes

Commands/probes run:

```bash
hostname && uname -a && git branch --show-current
```

Result: server host `kolibri`, branch `agent/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02/generic`.

```bash
python3 - <<'PY'
# GET http://10.99.0.10:9101/v1/health
# GET http://10.99.0.10:9101/v1/nodes
# GET http://10.99.0.10:9101/v1/fleet/route?target_node=qjns&required_capability=review
PY
```

Result:

- Control Plane health: `completed`, Redis `PONG`.
- qjns node card: `health=online`, `freshness=fresh`, `agent_id=agent-host-qjns`, `active_task=null`.
- qjns disk: `disk_free_bytes=4868214784`, `disk_total_bytes=20109631488`.
- qjns route: `status=completed`, route data `status=ok`, target endpoint `/v1/nodes/qjns`.

```bash
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false \
  timeout 20 git ls-remote --heads git@github.com:rd8r8bkd9m-tech/kolibri-ai-platform.git main
```

Result: `rc=0` on command node only.

```bash
GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/bin/false SSH_ASKPASS=/bin/false \
  timeout 20 git ls-remote --heads https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git main
```

Result: `rc=0` on command node only.

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 qjns ...
ssh -o BatchMode=yes -o ConnectTimeout=5 kolibri-qjns ...
ssh -o BatchMode=yes -o ConnectTimeout=5 10.99.0.4 ...
```

Result: public aliases timed out; mesh IP rejected available key. No secrets printed.

Control Plane qjns read-only probe:

```text
POST /v1/agents/tasks
task_id=P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_READONLY_HOST_PROBE
kind=read_only_probe
target_node=qjns
required_capability=read_only_probe
```

Result: `completed`, result reference exists in task metadata.

Control Plane qjns clone-phase canary:

```text
POST /v1/agents/tasks
task_id=P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_CLONE_PHASE_CANARY
kind=review_pr
target_node=qjns
required_capability=review
branch=__kolibri_probe_missing_ref_20260702_no_checkout__
```

Result: `failed` with `runtime_error` at `git fetch origin __kolibri_probe_missing_ref_20260702_no_checkout__`. This is the expected canary outcome proving qjns passed the preceding `git clone` phase.

Artifact verification:

```bash
test -f docs/agent/runs/2026-07-02-p0-qjns-github-clone-auth-regression-probe/RESULT.md
test -f docs/agent/runs/2026-07-02-p0-qjns-github-clone-auth-regression-probe/NEXT.md
git diff --check -- docs/agent/runs/2026-07-02-p0-qjns-github-clone-auth-regression-probe
```
