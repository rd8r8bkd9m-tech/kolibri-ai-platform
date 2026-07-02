# PLAN

Remote-authored relay for `P0_PR135_EMPTY_POLL_HIGH_STAGE_STATUS0_REPAIR_2026_07_02`.

Goal: preserve PR #135 lease equality and repair high-stage empty-poll transport `status 0` without runtime deploy.

Plan:
1. Start from PR #135 head `fdb5f8606cc376fe4860f98be86706e780efb894`.
2. Apply Андрей's server-authored diff from primary-candidate.
3. Keep scope limited to `ops/factory_control.py` and `tests/test_factory_capacity_controls.py`.
4. Verify with py_compile, focused pytest, diff check, and local 1000 empty-poll probe evidence.
5. Push branch for GitHub CI.
6. Next task after CI: controlled strict runtime canary only.
