# Next

Next exact task:

`P0_FACTORY_CONTROL_TELEGRAM_GATEWAY_OWNER_APPROVED_NO_MUTATION_DIAGNOSTIC_2026_07_02`

Objective:

Diagnose Telegram gateway ownership and startup state without mutating Bot API
state. Factory Control is now healthy and exposing Fabric routes; Telegram must
be handled separately with single-receiver safety.

Constraints:

- Do not start a second Telegram receiver.
- Do not call `getUpdates` manually.
- Do not delete or set webhooks.
- Do not send live Telegram messages.
- Do not print tokens or env.

