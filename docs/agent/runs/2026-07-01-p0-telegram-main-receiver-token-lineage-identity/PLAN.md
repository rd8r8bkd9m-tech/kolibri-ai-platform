# P0 Telegram Main Receiver Token Lineage Identity Plan

Task: `P0_TELEGRAM_MAIN_RECEIVER_TOKEN_LINEAGE_AND_IDENTITY_2026_07_01`

The Control Plane task on `main` failed before execution because the Codex
runner token was expired. The Mac dispatcher then used a remote SSH diagnostic
fallback to run the same read-only identity probe on `kolibri-main`.

Plan:

1. Confirm the active `main` Telegram receiver service state.
2. Confirm the Bot API identity with a non-consuming method.
3. Confirm webhook state without consuming updates.
4. Record only redacted/boolean facts.
5. Keep PR #89 draft and prepare a controlled cutover plan.
