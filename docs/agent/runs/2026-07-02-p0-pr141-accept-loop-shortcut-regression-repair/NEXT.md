# Next

Next exact task after GitHub CI passes:

`P0_PR141_ACCEPT_LOOP_SHORTCUT_STRICT_RUNTIME_CANARY_2026_07_02`

Required gate:

- deploy only `ops/factory_control.py` from the updated PR #141 head to `primary-candidate`;
- create a rollback backup before deploy;
- run staged canary `20/50/100/250/500/1000`;
- manually classify strict result;
- fail if any stage has empty/lease status `0`, any `5xx`, missing `completed_at`, missing stage, created/leased mismatch, thread count above gate, or unbounded fd growth;
- rollback on failure;
- comment PR #141 with the full table.

Do not start PR #119 release, MIMO requeue, FormulaLM wave, or broad 1000-agent rollout until this canary passes.

