# Follow-Up

Task: `P0_TELEGRAM_PR89_MAIN_RECEIVER_CUTOVER_PLAN_2026_07_01`

## Required Before Live Rollout

1. Update PR #89 so `deleteWebhook` cannot run as part of ordinary gateway
   startup for the main-active-polling cutover.
2. Keep `TELEGRAM_ALLOW_WEBHOOK_DELETE` unset for this rollout.
3. Add or confirm tests for:
   - default polling with no webhook does not call `deleteWebhook`;
   - webhook present plus no delete approval refuses polling;
   - webhook deletion requires explicit owner-approved migration mode;
   - webhook mode never starts polling.
4. Update deployment docs to require in-place update of the existing
   `kolibri-telegram-gateway.service`.
5. Run the local test subset and collect CI evidence for the final PR #89 head.
6. Get owner approval for the service restart window.

## Optional Later Migration

If the team later wants webhook mode, handle it as a separate migration:

- Stop the polling receiver only in an approved window.
- Set the webhook from one controlled deployment job.
- Verify no polling receiver remains active.
- Preserve the same single-receiver invariant.

If the team later needs to delete a webhook and return to polling, handle that
as a separate owner-approved migration. Do not combine it with the PR #89
Superfactory rollout.

## Remaining Risks

- Duplicate replies if any hidden process also calls `getUpdates`.
- Missed updates if the state file is changed or reset.
- Accidental webhook deletion if `TELEGRAM_ALLOW_WEBHOOK_DELETE=1` leaks into
  the live service environment.
- Rollout ambiguity if docs continue to mention generic restarts without
  stating that the existing receiver is updated in place.
