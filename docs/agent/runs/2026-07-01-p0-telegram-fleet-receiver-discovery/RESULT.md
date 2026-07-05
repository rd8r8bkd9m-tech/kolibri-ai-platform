# P0 Telegram Fleet Receiver Discovery Result

## Conclusion

The visible active receiver candidate is:

`main` / `kolibri-main-api` / `10.99.0.2`:
`python3 /usr/local/bin/kolibri-telegram-gateway`, supervised by
`kolibri-telegram-gateway.service`.

Classification: `active_receiver`.

Runtime evidence:

- Systemd service is `active/running`.
- Main PID is present.
- The service runs as user/group `kolibri`.
- The service uses `/etc/kolibri/telegram.env`.
- The gateway state file exists and was being updated during the probe.
- State-file metadata includes a non-null Telegram update offset.
- Redacted `getWebhookInfo` for the main service token reports no webhook URL
  and zero pending updates, consistent with long polling by an active receiver.

Important limitation: `home` and `main` have different normalized Telegram token
material. Because this task allowed only `getWebhookInfo`, not identity methods,
the probe did not call any Bot API method that would identify the bot username.
The active runtime receiver is therefore proven for the deployed main Telegram
gateway credential, while final token lineage to `@kolibriai_bot` should be
confirmed through a non-consuming, explicitly approved identity check or through
secret-management records. No token values or hashes were printed.

## Candidate Classification

| Candidate | Classification | Evidence |
| --- | --- | --- |
| `main` `kolibri-telegram-gateway.service` | `active_receiver` | Active/running systemd unit, receiver process present, fresh gateway state file, non-null offset, redacted `getWebhookInfo` no webhook and zero pending updates. |
| `home` `kolibri-telegram-gateway.service` | `inactive_canonical` | Service loaded but inactive/dead and disabled; no gateway state file; no receiver process. |
| `home-live` `director-home-live` agent | `unrelated` | Agent has `telegram` capability in Control Plane, but it is an agent host, not the gateway receiver; no local receiver process found. |
| `home-live` prior migration artifacts | `stale_artifact` | Artifact manifests exist for prior Telegram investigations; they are historical task outputs, not live processes. |
| `primary-candidate` canonical gateway | `inactive_canonical` | Current SSH probe was denied; predecessor task evidence says gateway inactive/disabled and no visible active receiver. |
| `mesh-9fts` | `unrelated` | Gateway service not found, state file missing, no gateway process; old Mimo process came from a Telegram-originated task but is not a receiver. |
| `mesh-agent-01` | `inaccessible` | SSH permission denied; Control Plane did not expose receiver process evidence. |
| `mesh-agent-02` | `inaccessible` | Bounded SSH probe timed out; Control Plane did not expose receiver process evidence. |
| `mesh-agent-03` | `inaccessible` | Bounded SSH probe timed out; Control Plane did not expose receiver process evidence. |
| Historical `TGCHAT-*` / `TG-*` worktrees and artifacts | `stale_artifact` | Filesystem manifests and paths show old Telegram-originated tasks, not active receivers. |
| Older local filesystem-search process with Telegram markers | `unrelated` | Search/probe command only; not a Telegram client receiver. |

## Safety Outcome

- No `getUpdates`, `setWebhook`, `deleteWebhook`, token rotation, or pending
  update deletion was performed.
- No product code was modified.
- No central GitHub push was performed.
- No service was stopped, because no stale non-canonical receiver was proven.
- PR #89 remains untouched/draft.

## Risks

- Token-lineage ambiguity remains: `home` and `main` token material differs.
- `mesh-agent-01`, `mesh-agent-02`, and `mesh-agent-03` could not be directly
  inspected over SSH during this run.
- `primary-candidate` could not be rechecked directly in this run, but recent
  predecessor evidence is strong enough to classify its canonical gateway as
  inactive for this investigation.

## Recommendation

Treat `main` as the live receiver host for operational purposes. Do not migrate,
stop, or replace it until token lineage is confirmed and an explicit cutover plan
exists. Keep PR #89 draft until the token-lineage ambiguity is resolved.
