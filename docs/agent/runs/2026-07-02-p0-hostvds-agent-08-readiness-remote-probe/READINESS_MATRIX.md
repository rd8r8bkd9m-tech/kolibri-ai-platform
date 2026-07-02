# Readiness Matrix

| Check | Status | Evidence |
| --- | --- | --- |
| Remote execution | Passed | Child task leased by `mesh-agent-08:agent-host-mesh-agent-08`; worktree under `/var/lib/kolibri-agent/logical-workers/mesh-agent-08/...`. |
| Node identity | Passed | Expected `hostvds-agent-08 / mesh-agent-08`; observed hostname `kolibri`. |
| Disk | Passed | `/dev/vda1` at 48% used, about 49G available during remote probe. |
| Codex runner | Passed with note | `codex` available, version `codex-cli 0.142.2`, auth classified configured/provider reachable; only terminal capability note. |
| MIMO runner | Partial | `mimo` binary available, version `0.2.1`; auth not probed because config/quota checks may expose account or credential details. |
| GitHub auth status | Blocked | `gh` binary missing, so `gh auth status` cannot run. |
| API route | Blocked | `kolibri-factory-control` service active, but expected local route `127.0.0.1:9101` refused `/health`, `/v1/health`, `/v1/fabric/health`, and `/v1/fabric/routes`. |
| Persistent Agent Host | Blocked | `agent-host` service inactive in remote probe. |
| Product code changes | Passed | None. |
| Secret handling | Passed | No tokens, env, private keys, or credential values were printed. |

