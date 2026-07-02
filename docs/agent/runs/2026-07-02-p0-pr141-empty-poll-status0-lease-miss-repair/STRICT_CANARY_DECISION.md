# STRICT CANARY DECISION

Decision: implementation_ready_for_ci_then_runtime_canary.

This task did not deploy runtime and did not run the live strict canary. The branch must first pass GitHub CI, then be deployed through a separate reversible runtime gate.

Required runtime pass criteria remain unchanged:

- stages 20/50/100/250/500/1000 all complete;
- `created_tasks == leased_tasks` at every stage;
- lease statuses contain only `200`;
- empty statuses contain only `200`;
- no transport `status 0`;
- no `5xx`;
- complete JSON with `completed_at`;
- thread and fd counts remain bounded.

PR #119 and broad MIMO/FormulaLM requeue remain blocked until this gate passes.
