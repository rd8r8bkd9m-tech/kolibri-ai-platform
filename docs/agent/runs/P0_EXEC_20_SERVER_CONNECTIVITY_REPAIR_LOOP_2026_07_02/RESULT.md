# Result

## What Now Works

- A reusable repair-loop contract exists in code:
  - `ops/factory_control.py` can build a canonical 20-server repair plan.
  - `ops/factory_control.py` exposes `GET /v1/fleet/repair-plan` once deployed.
  - `ops/kolibri-dispatch repair-plan` can generate and submit per-node repair
    tasks.
- Per-node repair artifacts exist for all 20 owner servers.
- The live Control Plane accepted all 20 generated repair tasks through
  existing `/v1/tasks`.
- Verification confirmed all 20 submitted tasks exist and are currently queued.

## Remaining Blockers

- The deployed Control Plane does not yet include the new
  `/v1/fleet/repair-plan` route; live request returned HTTP 404.
- The generated local repair plan could not use live registered node cards
  because the deployed repair-plan route is absent. It therefore conservatively
  classified unknown/missing node states and dispatched repair probes.
- The 20 child repair tasks are queued, not completed. Node-level repair
  outcomes depend on lease pickup by healthy Agent Host nodes.

## Artifacts

- Required run docs:
  - `docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02/PLAN.md`
  - `docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02/ACTIONS.md`
  - `docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02/TESTS.md`
  - `docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02/RESULT.md`
  - `docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02/NEXT.md`
- Per-node envelopes:
  - `docs/agent/runs/P0_EXEC_20_SERVER_CONNECTIVITY_REPAIR_LOOP_2026_07_02/repair-envelopes/*.json`

## Hard Blocker Command

Deploy the scoped Control Plane change before relying on the live route:

```bash
python3 -m pytest tests/test_fabric_control.py tests/test_factory_runtime.py -q && \
python3 -m py_compile ops/factory_control.py ops/kolibri-dispatch && \
sudo install -m 0755 ops/factory_control.py /opt/kolibri-ai-platform/ops/factory_control.py && \
sudo systemctl restart kolibri-factory-control.service && \
curl -fsS http://10.99.0.2:9101/v1/fleet/repair-plan
```

This command is intentionally scoped to the Control Plane sidecar file and has
an immediate rollback path: restore the prior
`/opt/kolibri-ai-platform/ops/factory_control.py` from service backup or package
state, then restart `kolibri-factory-control.service`.

