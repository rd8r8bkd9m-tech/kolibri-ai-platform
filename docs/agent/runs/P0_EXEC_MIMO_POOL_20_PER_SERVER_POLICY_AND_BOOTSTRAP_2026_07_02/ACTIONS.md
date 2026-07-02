# Actions

- Added `ops/mimo_pool_policy.py` as the reusable policy source for max agents, resource caps, scheduler gates and external API guardrails.
- Updated `ops/agent_host.py` to clamp oversized `KOLIBRI_MAX_INFLIGHT` values to the policy cap and include `agent_pool`/`pool_policy` in register, heartbeat and lease calls.
- Updated `ops/factory_control.py` so `/v1/nodes`, Fabric fleet views, `/v1/fabric/policy`, and bootstrap metadata expose MIMO pool policy and per-node pool status.
- Updated `backend/factory_status.py` to expose per-node `agent_pool` plus aggregate `mimo_capacity`; made `httpx` optional for pure normalization tests.
- Added `ops/systemd/kolibri-agent-host@.service` for reversible slot-based Agent Host instances with CPU, memory, task and file descriptor caps.
- Added resource caps and default pool environment to `ops/systemd/kolibri-agent-host.service`.
- Added `ops/kolibri-agent-pool` helper for `start|stop|restart|status` over 1 to 20 template slots.
- Added tests in `tests/test_mimo_pool_policy.py` and extended `tests/test_factory_status.py`.

No live service restart, deploy, credential rotation, destructive git command, force push or push to `main` was performed.
