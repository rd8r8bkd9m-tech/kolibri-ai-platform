# Result

Status: `metadata_visibility_restored_single_receiver_candidate_selected`

Task: `P0_TELEGRAM_MAIN_RECEIVER_METADATA_ACCESS_AND_SINGLE_RECEIVER_CUTOVER_GATE_2026_07_02`

## Fresh Evidence

Checked at:

- Host metadata: `2026-07-02T00:44:50Z`
- Bot API metadata: `2026-07-02T00:45:28Z`

Execution node:

- `kolibri`
- This is a server/control-node execution path, not a local Mac
  implementation.

Systemd receiver metadata:

- Unit: `kolibri-telegram-gateway.service`
- `LoadState=loaded`
- `ActiveState=active`
- `SubState=running`
- `MainPID` present
- `ExecStart=/usr/bin/python3 /usr/local/bin/kolibri-telegram-gateway --control-url http://10.99.0.10:9101`
- `FragmentPath=/etc/systemd/system/kolibri-telegram-gateway.service`
- `UnitFileState=disabled`
- `StateChangeTimestamp=Thu 2026-07-02 00:01:25 UTC`

Process metadata:

- Visible receiver process:
  `python3 /usr/local/bin/kolibri-telegram-gateway --control-url http://10.99.0.10:9101`
- No environment output was requested.

State-file metadata:

- `/var/lib/kolibri-telegram-gateway/state.json` exists.
- File size: `24865` bytes.
- File mtime: `2026-07-02 00:30:17.204597104 +0000`.
- JSON parse: valid.
- Telegram update offset: present.
- Tracked task count: `33`.
- Memory keys present: `known_results`, `last_work_request`,
  `open_expectations`, `project`, `recent_messages`, `version`.
- Raw state content was not printed.

Read-only Bot API metadata:

- `getMe`: `ok=true`.
- Bot username: `kolibriai_bot`.
- Bot identity ID: present and redacted.
- `getWebhookInfo`: `ok=true`.
- Webhook URL empty: `true`.
- Pending updates: `0`.
- Allowed updates: `message`.
- Last webhook error date: none.

## Gate Decision

Exactly one receiver candidate is selected:

`main` / `kolibri` / `kolibri-telegram-gateway.service`.

Classification:

- `selected_active_single_receiver_candidate`
- The active process, fresh state-file metadata, successful `getMe` identity,
  empty webhook, zero pending updates, and non-null offset together confirm that
  the active receiver on this server is the live long-polling receiver for
  `@kolibriai_bot`.

Decision:

- Do not start or restart any second receiver.
- Do not cut over to PR #89 or another receiver yet.
- Keep `main` as the selected receiver candidate until a dedicated,
  owner-approved single-receiver cutover task either repairs this receiver in
  place or cleanly replaces it with a proven target.

## Blockers

No metadata-access blocker remains for the `main` receiver.

Remaining operational blockers:

- `UnitFileState=disabled` means a future reboot may not automatically restore
  the receiver unless deliberately enabled in an owner-approved repair task.
- The service is active but its control URL points at `10.99.0.10:9101`; prior
  July 2 evidence says live Factory Control/Fabric routing is still stale after
  rollback. That control-plane issue must be repaired before any receiver
  feature cutover.
- PR #89 remains draft and must not be live-switched until the selected single
  receiver plan is approved and the target is proven.

## Safety Outcome

- No Bot API mutation occurred.
- No service mutation occurred.
- No secrets were printed.
- No raw private Telegram messages were printed.
- No product code was modified.
