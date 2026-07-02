# Actions

- Added Agent Host worker-pool readiness for `qjns` and `uiap`.
- Added resource caps:
  - `KOLIBRI_AGENT_MIN_DISK_FREE_GB`, default `5`;
  - `KOLIBRI_AGENT_MIN_MEM_AVAILABLE_MB`, default `512`;
  - `KOLIBRI_MAX_INFLIGHT`, default `1`.
- Added opt-in switches:
  - `KOLIBRI_QJNS_UIAP_WORKER_POOL=1` for qjns/uiap;
  - `KOLIBRI_AGENT_POOL_ENABLED=1` or `KOLIBRI_WORKER_POOL_ENABLED=1` for generic hosts.
- Agent Host now advertises implementation and `runner:*` capabilities only when the pool is ready.
- Control Plane now rejects worker-pool tasks for nodes that explicitly report `worker_pool.ready=false`.
- Added `scripts/preflight-agent-worker-pool.sh` for safe local readiness validation before service restart.
