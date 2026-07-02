# Next

- Deploy this branch to `qjns` and `uiap`, then run `scripts/preflight-agent-worker-pool.sh /opt/kolibri-ai-platform` on each host before restart.
- Keep `uiap` capped at light worker use unless the RAG resource owners approve higher CPU, memory and disk budgets.
- Add UI rendering for `worker_pool.ready` and `worker_pool.reasons` if the owner wants the Mini App fleet screen to expose these blockers directly.
- If a host reports `mimo_unavailable`, repair MIMO installation/auth on that host or keep the pool disabled.
