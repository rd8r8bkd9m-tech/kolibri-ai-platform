# Plan

Task: `P0_REPAIR_LEASE_WATCHDOG_CONTROL_PLANE_URL_AND_TELEGRAM_REPORT_20260704`

Goal: repair KFM Lease Watchdog so it does not hang on `10.99.0.2:9101`, supports fallback Control Plane URLs, and reports owner-facing Telegram messages in clear Russian instead of raw failed/None fields.

Plan:

- Trace the sender and runtime unit.
- Diagnose candidate Control Plane URLs.
- Add bounded fallback URL selection.
- Add owner-safe report formatting.
- Add tests for fallback and report wording.
- Run diagnose-only smoke with no queue mutation and no Telegram send.
