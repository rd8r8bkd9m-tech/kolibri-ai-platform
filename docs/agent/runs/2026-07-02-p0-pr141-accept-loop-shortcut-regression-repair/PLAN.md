# P0 PR141 Accept Loop Shortcut Regression Repair

Task: `P0_PR141_ACCEPT_LOOP_SHORTCUT_REGRESSION_REPAIR_2026_07_02`

Remote agent: `Artem - transport regression engineer`

Plan:

1. Start from PR #141 head `93df2ca5f07d99ad49a7b9bbd33f959b97906e14`.
2. Keep implementation limited to Control Plane lease transport/matching code and focused tests.
3. Remove or neutralize the raw accept-loop empty lease shortcut that produced strict empty-poll `status0` from stage20.
4. Preserve the normal HTTP handler lifecycle so `200/no_task` responses are produced by the standard response path.
5. Prove the change with focused capacity and adjacent runtime tests.
6. Do not deploy runtime and do not rerun the live canary in this implementation task.

