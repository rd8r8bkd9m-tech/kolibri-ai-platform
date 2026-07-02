# Home Visibility Recovery Diagnostic Tests

## Probes Run

| Probe | Result | Evidence |
| --- | --- | --- |
| Server execution identity | Passed | `hostname=kolibri`, `user=root`, `kernel=Linux 6.8.0-36-generic x86_64`, worktree under `/var/lib/kolibri-agent/logical-workers/...` |
| Local GitHub origin read | Passed | `git ls-remote --exit-code origin HEAD` returned `f7ac32c70406432a52752ca45d87e35d9f1facd3` |
| Short SSH alias `home` | Config present | `ssh -G home` resolves `user ladik`, `hostname 10.99.0.1`, public-key auth, identity paths redacted |
| Short SSH alias `kolibri-home` | Config present | `ssh -G kolibri-home` resolves `user ladik`, `hostname 10.99.0.1`, public-key auth, identity paths redacted |
| SSH to `home` | Blocked | `Connection timed out during banner exchange`; no Home runtime command executed |
| SSH to `kolibri-main` | Blocked | `ssh: connect to host 104.253.43.117 port 22: Connection timed out` |
| Bounded SSH topology probe | Blocked/degraded | First five direct aliases timed out before global timeout: `kolibri-main`, `kolibri-uiap`, `kolibri-qjns`, `kolibri-9fts`, `kolibri-new` |
| Control Plane health | Passed | `http://10.99.0.10:9101/health` returned completed health envelope, `fabric_api_version=2026-07-01`, `redis=PONG`, `node=main` |
| Control Plane node visibility | Degraded | `/v1/nodes` returned `total=53`, `online=25`, `fresh=25`, `stale=26`, `degraded=2` |
| Home node card | Degraded but fresh heartbeat | `home`: `health=degraded`, `freshness=degraded`, `reported_health=online`, `hostname=plastilin`, heartbeat age about `53s` at probe time |
| Home Live node card | Degraded but fresh heartbeat | `home-live`: `health=degraded`, `freshness=degraded`, `reported_health=online`, `hostname=plastilin`, heartbeat age about `49s` at probe time |
| Mesh Home card | Stale | `mesh-home`: `health=stale`, heartbeat age about `1703s` at probe time |
| Local factory status | Passed | `http://127.0.0.1:8000/api/factory/status` returned JSON `status=ok`, `mode=v13`, `version=3.0.0` |
| Prior wallboard task state | Failed on clone/auth | `P0_HOME_FACTORY_TERMINAL_UI_RU_2026_07_01` failed with `git clone git@github.com:rd8r8bkd9m-tech/kolibri-ai-platform.git ... rc=128` |

## Commands

```bash
hostname
id -un
uname -srm
git branch --show-current
git rev-parse --short=12 HEAD
git remote -v
git ls-remote --exit-code origin HEAD
ssh -G home
ssh -G kolibri-home
ssh -o BatchMode=yes -o ConnectTimeout=8 home '<read-only runtime probe>'
ssh -o BatchMode=yes -o ConnectTimeout=6 kolibri-main '<read-only service probe>'
bash docs/agent/dispatcher/ssh/probe_kolibri_ssh_topology.sh
curl -fsS http://10.99.0.10:9101/health
curl -fsS http://10.99.0.10:9101/v1/nodes
curl -fsS http://127.0.0.1:8000/api/factory/status
curl -fsS http://10.99.0.10:9101/v1/tasks/P0_HOME_FACTORY_TERMINAL_UI_RU_2026_07_01
```

All outputs included in this artifact are redacted for secret-like fields and key paths.

