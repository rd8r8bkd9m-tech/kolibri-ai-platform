# STRICT CANARY DECISION

Decision: `repair_needed_runtime_canary_pending`

This branch is not merge-ready yet because no live strict runtime canary has been run for this exact head.

Implementation evidence:

- `python3 -m pytest tests/test_factory_capacity_controls.py` -> `22 passed`
- `python3 -m pytest tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_control_runtime_import_path.py tests/test_factory_control_superfactory.py` -> `20 passed`
- `bash scripts/preflight-factory-control-runtime.sh` -> `factory_control_runtime_preflight=ok`
- `python3 -m pytest` full collection is blocked by missing optional `pydantic` and `httpx` on the server.

Required next gate:

1. Open a stacked PR over PR #140.
2. Wait for GitHub CI.
3. Deploy only `ops/factory_control.py` to `primary-candidate` with a timestamped backup.
4. Run strict stages `20/50/100/250/500/1000`.
5. Pass only if created equals leased, lease statuses are only `200`, empty statuses are only `200`, no `status 0`, no `5xx`, result JSON is complete, and FD/thread counts stay bounded.
6. Roll back immediately on any strict failure.

PR #119 remains blocked until that strict runtime canary passes.
