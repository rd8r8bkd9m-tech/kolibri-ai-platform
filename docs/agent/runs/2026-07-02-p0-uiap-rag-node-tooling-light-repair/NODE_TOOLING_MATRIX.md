# Node Tooling Matrix

Task id: `P0_UIAP_RAG_NODE_TOOLING_LIGHT_REPAIR_2026_07_02`

Observed server execution node:

| Field | Value |
| --- | --- |
| Host | `kolibri` |
| Platform | Ubuntu 24.04 LTS on KVM |
| Kernel | `Linux 6.8.0-36-generic` |
| Architecture | `x86-64` |
| Current branch | `agent/P0_UIAP_RAG_NODE_TOOLING_LIGHT_REPAIR_2026_07_02/generic` |
| Current commit | `f7ac32c70406432a52752ca45d87e35d9f1facd3` |
| Remote `HEAD` | `refs/heads/main` at `f7ac32c70406432a52752ca45d87e35d9f1facd3` |
| Task branch on remote | Not present; `git ls-remote --heads` returned no matching head |
| Worktree dirty before artifacts | Clean |
| Disk | `/dev/vda1`, 99G total, 45G used, 50G available, 48% used |
| Agent Host service | loaded, enabled, active, running |
| Agent Host unit path | `/etc/systemd/system/kolibri-agent-host.service` |

Tooling:

| Tool | State |
| --- | --- |
| `git` | present, `git version 2.43.0` |
| `python3` | present, `Python 3.12.3` |
| `node` | present, `v18.19.1` |
| `npm` | present, `9.2.0` |
| `codex` | present, `codex-cli 0.142.2` |
| `redis-cli` | present |
| `gh` | missing from `PATH` |

Repo catalog classification for `uiap`:

| Field | Value |
| --- | --- |
| `node_id` | `uiap` |
| `display_name` | `Знания` |
| `role` | `knowledge_model_node` |

Classification:

- `uiap` remains suitable for light CPU-only RAG/knowledge tasks, docs indexing
  contracts, skills registry probes, and small verification jobs.
- Heavy builds, large batch indexing, GPU/model-serving assumptions, secret
  storage, direct production exposure, and git pushes remain out of scope for
  `uiap` until explicitly revalidated.
- Current server node tooling is sufficient for repo-local classification and
  Agent Host contract verification.
- The only local tooling gap observed is missing `gh`; this blocks GitHub PR
  metadata operations from this node but does not block read-only git remote
  probes.

