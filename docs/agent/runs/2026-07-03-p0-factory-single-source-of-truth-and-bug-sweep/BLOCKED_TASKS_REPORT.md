# Blocked Tasks Report

Observed live blocked count: 9 from `/v1/tasks?summary=1&compact=1&limit=20`.

## Categories

- Envelope normalization candidates: alias mismatches such as `home-live` vs `home` when safe.
- Node repair candidates: stale `qjns` and `uiap` records with active work.
- Runner installation candidates: tasks requiring `runner:codex` or `runner:mimo` where the node lacks real runner capability.
- Safety-blocked tasks: tasks with restricted `allowed_nodes`, blocked runner auth, or drained target.

Do not repair by deleting queues or by adding fake capabilities.

