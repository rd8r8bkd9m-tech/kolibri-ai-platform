# EMPTY_POLL_STATUS0_CAUSE

Observed failure before this patch:

- PR #135 fixed created/leased equality and the real lease path.
- Empty-poll requests still returned client-side transport `status 0` under high-stage pressure.

Likely cause addressed by this patch:

- Empty no-task polls were still entering Redis maintenance and node-load work before returning `no_task`.
- Thread-per-connection behavior under high concurrent empty polls made response completion sensitive to connection churn.

Repair approach:

- Return `200 no_task` immediately when both queue structures are empty (`LLEN queue == 0` and `SCARD queued_task_ids == 0`) for normal lease polls.
- Preserve runner telemetry path when `runners` is present.
- Use a fixed HTTP worker pool and larger accept backlog instead of unbounded per-request thread creation.
- Do not introduce a `503` overload gate.
