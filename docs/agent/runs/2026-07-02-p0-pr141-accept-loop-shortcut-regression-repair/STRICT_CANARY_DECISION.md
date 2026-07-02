# Strict Canary Decision

Decision for this implementation task: `runtime_canary_required_before_merge`.

This task did not deploy runtime and did not run the staged live canary. That is intentional.

The change is allowed to proceed only to GitHub CI and then to a separate reversible runtime canary gate.

Strict pass criteria for the next canary:

- all six stages exist: `20`, `50`, `100`, `250`, `500`, `1000`;
- `completed_at` is present;
- `created_tasks == leased_tasks` at every stage;
- lease statuses contain only `200`;
- empty statuses contain only `200`;
- no status `0` anywhere;
- no `5xx` anywhere;
- thread count remains within the gate;
- fd count remains bounded;
- post-canary health is OK.

If any item fails, rollback and keep PR #141 draft.

