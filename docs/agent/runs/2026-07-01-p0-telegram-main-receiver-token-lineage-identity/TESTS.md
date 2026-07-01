# P0 Telegram Main Receiver Token Lineage Identity Tests

Control Plane status:

- `P0_TELEGRAM_MAIN_RECEIVER_TOKEN_LINEAGE_AND_IDENTITY_2026_07_01`
  failed on runner authentication before useful execution.

Read-only SSH diagnostic verification:

- Service:
  - `LoadState=loaded`
  - `ActiveState=active`
  - `SubState=running`
  - `MainPID` present
  - `ExecMainPID` present
  - `UnitFileState=disabled`
- State file:
  - `/var/lib/kolibri-telegram-gateway/state.json` exists.
  - `offset` key is present.
  - State file mtime age was about 68 seconds at probe time.
- Bot API:
  - `getMe` returned `username=kolibriai_bot`.
  - `getWebhookInfo` returned empty webhook URL.
  - `pending_update_count=0`.

Safety checks:

- `getUpdates_called=false`
- `setWebhook_called=false`
- `deleteWebhook_called=false`
- `token_printed=false`
- `token_hash_printed=false`
- `service_mutation=false`
