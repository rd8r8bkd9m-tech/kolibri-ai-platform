# Next

Next exact task:

`P0_TELEGRAM_MAIN_SINGLE_RECEIVER_IN_PLACE_REPAIR_GATE_2026_07_02`

Objective:

Prepare an owner-approved, no-surprise repair gate for the already selected
receiver candidate:

`main` / `kolibri` / `kolibri-telegram-gateway.service`.

Required constraints:

- Do not start or restart anything until the task explicitly reconfirms this is
  still the only selected receiver candidate.
- Do not introduce a second receiver.
- Do not call `getUpdates` except from the already-running selected receiver.
- Do not call `setWebhook`, `deleteWebhook`, token rotation, or pending update
  deletion.
- Do not print tokens, owner chat IDs, private messages, or raw state files.
- Repair in place first: service enablement, packaging/import-path, and control
  URL health must be handled as explicit, reviewable steps.
- Only after in-place repair is rejected or fails should a separate cutover task
  be proposed.

Safe first step for that task:

Reconfirm read-only metadata for the selected `main` receiver, then produce an
owner approval packet for exactly one of:

- `repair_main_in_place`
- `cutover_from_main_to_named_target`
- `hold_no_mutation`
