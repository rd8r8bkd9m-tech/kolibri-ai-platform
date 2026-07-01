# Server Inventory From Local Repo

Task ID: `2026-06-30-project-intelligence-all-branches`

Этот файл фиксирует только то, что локальная Mac-копия знает о серверах из README, `infra/network/config.json`, `ops/systemd/*`, `ops/kolibri-dispatch`, `backend/pipeline.py`, `backend/main.py`, `ops/mesh_control_bridge.py`, `ops/orchestrator_roster.py` и `ops/orchestrator_memory.py`.

Это не live-аудит серверов. Live-аудит должен выполнить server-side Control Plane task.

## Known Classic Mesh Servers

| Server | Public IP | VPN IP | SSH alias | Role from repo | Ports / URLs from repo | Expected responsibilities |
| --- | --- | --- | --- | --- | --- | --- |
| `home` | `178.207.11.90` | `10.99.0.1` | `kolibri-home` | training hub, Redis, network gateway | SSH `2222`; Redis `6379`; mesh coord `8080`; mesh chat `8082` | training, data generation, fine-tuning, Redis/state, mesh coordination, proxy jump |
| `main` | `104.253.43.117` | `10.99.0.2` | `kolibri-main` | API gateway, frontend, routing, control node candidate | HTTP `80`; backend `8000`; Control Plane `9101` | FastAPI gateway, frontend, nginx, Control Plane, Telegram gateway, mesh bridge |
| `uiap` | `31.57.26.151` | `10.99.0.3` | `kolibri-uiap` | RAG engine | RAG `8002`; backend proxy target `/rag` | ChromaDB/embeddings/knowledge-base |
| `qjns` | `217.60.63.97` | `10.99.0.4` | `kolibri-qjns` | agent executor | Agent `8003`; backend proxy target `/agent` | code execution, tool calling, planning; currently marked quarantined/reserve in roster |
| `9fts` | `94.183.235.154` | `10.99.0.5` | `kolibri-9fts` | inference, implementation worker | Inference `8001`; backend proxy target `/inference` | model inference, llama.cpp/GGUF, implementation worker, Agent Host |

## Additional Factory Nodes Mentioned In Code

| Node ID | Where found | Known access | Local interpretation | Must verify remotely |
| --- | --- | --- | --- | --- |
| `new` | `ops/kolibri-dispatch`, `ops/orchestrator_roster.py`, tests | `root@109.248.161.39` via `kolibri-home` proxy jump | independent reviewer node | hostname, VPN IP, Agent Host status, repo path, disk/RAM, review capability |
| `primary-candidate` | `ops/telegram_gateway.py`, `backend/factory_status.py`, tests | not defined in static inventory | director/default Telegram chat/image target | whether this is a real node, branch, server, or logical role |
| `home-live` | `ops/mesh_control_bridge.py`, tests | not defined in static inventory | default mesh executor | whether this maps to `home`, another server, or a mesh-only node |
| `mesh-*` | `ops/mesh_control_bridge.py` | synthetic Control Plane shadow nodes | bridge-created node records from mesh coordinator | all currently registered shadow nodes and source mesh node ids |

## Service Placement Expected From Repo

| Service | Expected host / node | Evidence |
| --- | --- | --- |
| `kolibri-factory-control.service` | control node, likely `main` / `10.99.0.2` | `ops/systemd/kolibri-factory-control.service`; `KOLIBRI_FACTORY_CONTROL_URL=http://10.99.0.2:9101` in other units |
| `kolibri-telegram-gateway.service` | control node, likely `main` | `ops/systemd/kolibri-telegram-gateway.service`; uses `/etc/kolibri/telegram.env` and `10.99.0.2:9101` |
| `kolibri-mesh-control-bridge.service` | control node / bridge host | `ops/systemd/kolibri-mesh-control-bridge.service`; reads mesh from `10.99.0.1`, posts to `10.99.0.2` |
| `kolibri-agent-host.service` | worker nodes | `ops/systemd/kolibri-agent-host.service`; memory says stable on `9fts` and `new` |
| `kolibri-ai` | `main` | `scripts/deploy.sh`; restarted after frontend build |
| `nginx` | `main` | `infra/network/nginx.conf`; `scripts/deploy.sh` |
| `kolibri-network` | `uiap`, `qjns`, possibly `9fts` | `scripts/deploy.sh` deploys `infra/network/api.py` and restarts service |
| `kolibri-inference` | `9fts` | `scripts/deploy.sh` references `infra/inference/api.py`, but that path is not present in current local tree |

## Server-Specific Local Notes

### home

Expected to be the training and Redis hub. Repo references it as public SSH entrypoint, WireGuard IP `10.99.0.1`, Redis host, mesh coordinator/chat host, proxy jump, and training destination under `/home/ladik/kolibri-training/`.

Remote audit must verify whether `home` is also running Control Plane dependencies, whether Redis is healthy, and whether training dependencies/model caches are present.

### main

Expected to be the API/frontend/control-facing node: WireGuard IP `10.99.0.2`, public HTTP, backend `8000`, frontend/nginx, Control Plane `9101`, possible Telegram Gateway and Mesh Bridge host.

Remote audit must verify `kolibri-ai`, `nginx`, `kolibri-factory-control`, `kolibri-telegram-gateway`, `kolibri-mesh-control-bridge`, repo branch/commit, frontend build path, and `/opt/kolibri-ai` state.

### uiap

Expected RAG/knowledge node: WireGuard IP `10.99.0.3`, RAG service target `8002`, ChromaDB/embeddings/knowledge-base tasks.

Remote audit must verify actual RAG service, vector storage location, disk pressure, data freshness, and whether it is quarantined/reserve as `ops/orchestrator_roster.py` suggests.

### qjns

Expected agent executor: WireGuard IP `10.99.0.4`, agent service target `8003`, code execution/tool calling/planning.

Remote audit must verify current access/clone/auth/network blockers, Agent Host status, repo path, branch state, and why roster marks it as reserve/quarantined.

### 9fts

Expected inference and implementation worker: WireGuard IP `10.99.0.5`, inference service target `8001`, model inference, llama.cpp/GGUF, default dispatch node for implementation diagnostics.

Remote audit must verify Agent Host, inference service, model files, CPU/GPU capabilities, repo worktrees, artifacts, and GitHub auth state.

### new

Additional reviewer node: mentioned by dispatcher as `root@109.248.161.39` via `kolibri-home`, roster role independent review, memory says Agent Host is stable on `new`.

Remote audit must verify whether `new` is registered in Control Plane, its capabilities, whether it can run tests/reviews, and whether it has safe GitHub review access.

### primary-candidate

Logical node id used as human name `Директор`, default Telegram chat target, default Telegram image target, and test node for factory status.

Remote audit must determine whether `primary-candidate` is a real server node, a branch name, a logical Control Plane role, or stale naming.

## Required Live Per-Server Report

The server-side intelligence task must create:

```text
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/SERVER_INVENTORY.md
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/servers/home.md
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/servers/main.md
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/servers/uiap.md
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/servers/qjns.md
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/servers/9fts.md
docs/agent/intelligence/2026-06-30-project-intelligence-all-branches/servers/new.md
```

If `primary-candidate`, `home-live`, or `mesh-*` nodes exist in Control Plane, create additional files for them.

Each per-server report must include:

- node id and hostname;
- public/VPN/internal IPs known to Control Plane;
- OS and kernel;
- uptime and time sync;
- CPU/RAM/disk;
- mounted volumes relevant to Kolibri;
- running Kolibri services and systemd status;
- listening ports relevant to Kolibri;
- Control Plane registration and heartbeat freshness;
- Agent Host identity, capabilities, active task, draining status;
- repo paths, current branch/commit/dirty status;
- local worktrees and artifact roots, summarized by size/count;
- installed runtimes: Python, Node, npm, git, gh, mimo, llama.cpp, Docker if present;
- model/data locations, summarized only;
- environment variable names relevant to Kolibri, with values redacted;
- recent logs summarized with secrets redacted;
- health endpoints checked;
- current blockers;
- recommended action.

## Safe Server-Side Probe Policy

The live server probe must be read-only unless the owner explicitly authorizes a fix. It may inspect health endpoints, systemd status, disk/memory/uptime, repo status, service ports, runtime versions, and redacted log tails.

It must not print secret values, print full env files, modify services, restart anything, install packages, checkout branches in dirty worktrees, push, reset, clean, or stash.
