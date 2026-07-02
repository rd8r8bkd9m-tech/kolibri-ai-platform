# Result

Implemented the production-facing task/artifact agent API repair in `ops/factory_control.py`.

Owner-visible behavior now works as follows:
- `POST /v1/agents/tasks` still creates a legacy-compatible queued task through the existing Redis-backed control plane.
- `GET /v1/agents/status/{task_id}` returns a canonical envelope with stable UI fields including task state, terminal flag, attempt, lease owner, timestamps, result reference, PR/preview links, and artifact count.
- `GET /v1/agents/artifacts/{task_id}` returns a canonical artifact envelope with recursively collected safe artifact references from task result manifests.
- `POST /v1/agents/cancel/{task_id}` cancels queued/running tasks, remains idempotent for already-cancelled tasks, and does not rewrite completed or failed history.

No secrets were printed or added. No destructive Git commands were used.
