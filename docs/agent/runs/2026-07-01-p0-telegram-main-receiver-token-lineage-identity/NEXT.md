# P0 Telegram Main Receiver Token Lineage Identity Next

Next task:

`P0_TELEGRAM_PR89_MAIN_RECEIVER_CUTOVER_PLAN_2026_07_01`

Goal:

Prepare a no-double-receiver cutover plan from the current live
`main` long-polling `kolibri-telegram-gateway.service` to the PR #89 Telegram
Superfactory implementation.

The next task must be read-only/planning first. It should compare:

- Current live `main` gateway unit/config/runtime.
- PR #89 branch `p0/telegram-superfactory-bot-miniapp-2026-07-01`.
- Required rollback path.
- Single receiver invariant.
- Whether cutover can happen by updating the existing `main` receiver instead
  of launching a second poller.

Do not:

- Start a second receiver.
- Call `getUpdates`.
- Mutate webhook state.
- Stop the current live receiver without a tested rollback.
- Merge PR #89.
- Push to main.
