# Plan

Task id: `P0_EXEC_FACTORY_ALWAYS_ON_SUPERVISOR_2026_07_02`

Objective: implement a reversible 24/7 Factory supervisor loop in the checked-out repository, with health checks, dead agent detection, repair task dispatch, stuck task requeue, and a Russian owner summary.

Planned scope:

- Add supervisor runtime logic to `ops/factory_control.py`, reusing the existing Redis task/node store and queue contracts.
- Keep dispatch capped at 50% of registered nodes per cycle.
- Add `FACTORY_SUPERVISOR_ENABLED=0` as the rollback switch for all mutating supervisor behavior.
- Expose read-only supervisor status and a manual scoped run endpoint.
- Add focused tests for cap enforcement, dead agent repair dispatch, stuck task requeue, and owner summary.
- Create required run artifacts under this directory.

Rollback:

- Set `FACTORY_SUPERVISOR_ENABLED=0` and restart `kolibri-factory-control.service`.
- Code rollback is isolated to `ops/factory_control.py`, `tests/test_factory_supervisor_loop.py`, and this run artifact directory.
