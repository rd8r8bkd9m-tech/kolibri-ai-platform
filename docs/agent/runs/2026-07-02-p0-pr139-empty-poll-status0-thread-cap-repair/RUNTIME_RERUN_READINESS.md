# RUNTIME RERUN READINESS

Ready for runtime rerun only after GitHub CI is green.

Rerun requirements:

- Backup live `/opt/kolibri-ai-platform/ops/factory_control.py` before deploy.
- Deploy only `ops/factory_control.py` from this branch.
- Run `python3 -m py_compile` on the deployed file.
- Restart `kolibri-factory-control.service`.
- Verify `/health` before the canary.
- Run strict stages: `20`, `50`, `100`, `250`, `500`, `1000`.

Strict pass criteria:

- `created_tasks == leased_tasks` at every stage.
- No lease `status 0`.
- No empty-poll `status 0`.
- No `5xx` statuses.
- Complete result JSON with all six stages and `completed_at`.
- Runtime FD/thread counts remain bounded.

Rollback criteria:

- Any `status 0` in lease or empty poll summaries.
- Any `5xx`.
- Any incomplete canary result.
- Any service health failure after deploy.
