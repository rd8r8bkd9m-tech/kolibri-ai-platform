# Plan

Task: `P0_TELEGRAM_MAIN_RECEIVER_METADATA_ACCESS_AND_SINGLE_RECEIVER_CUTOVER_GATE_2026_07_02`

Objective: restore read-only metadata visibility for the active Telegram receiver
on `main` and decide whether the next move is a single-receiver repair or a
cutover gate.

Safety rules:

- Execute on a server/control node only.
- Do not call `getUpdates`.
- Do not call `setWebhook`, `deleteWebhook`, token rotation, or pending update
  deletion methods.
- Do not start, stop, restart, enable, or disable services.
- Do not print bot tokens, token hashes, owner chat IDs, private messages, or raw
  state-file contents.
- Select exactly one receiver candidate before any future start/restart is
  proposed.

Steps:

1. Read prior Telegram receiver run artifacts and runtime contract.
2. Probe host-level service metadata for `kolibri-telegram-gateway.service`.
3. Probe only read-only Bot API metadata using `getMe` and `getWebhookInfo`.
4. Inspect state-file metadata only, not raw content.
5. Classify the receiver candidate and produce the safe next task.
