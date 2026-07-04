# P0 Telegram Fleet Receiver Discovery Plan

Task: `P0_TELEGRAM_FLEET_RECEIVER_DISCOVERY_2026_07_01`

UTC run window: 2026-07-01 05:04-05:18.

## Scope

Find the active receiver for `@kolibriai_bot` across the allowed fleet without
changing Telegram state, rotating credentials, modifying product code, pushing
to GitHub, or stopping ambiguous/canonical services.

## Constraints Applied

- No `getUpdates` API call from this probe.
- No `setWebhook`, `deleteWebhook`, token rotation, or pending update deletion.
- Bot API use limited to redacted `getWebhookInfo`.
- No secret values, owner chat IDs, or private message text recorded.
- Host evidence limited to service status, state-file metadata, process,
  container, and tmux listings with token redaction.
- No service stop attempted; no stale non-canonical receiver was proven.
- PR #89 was not modified or pushed.

## Evidence Plan

1. Read task envelope for exact artifacts, allowed nodes, known evidence, and
   required constraints.
2. Use Control Plane read-only endpoints for node inventory and targeted task
   history.
3. Use node cards from `ops/orchestrator_roster.py` to interpret canonical
   fleet roles.
4. Inspect safe filesystem manifests by path/name only for prior Telegram probe
   artifacts.
5. Probe authorized/accesssible hosts:
   - `home` / `home-live` local host metadata.
   - `main` via SSH to `10.99.0.2`.
   - `primary-candidate` via SSH to `10.99.0.10`, plus prior task result.
   - `mesh-9fts` via SSH to `10.99.0.5`.
   - `mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03` with bounded SSH probes.
6. Classify each receiver candidate as one of:
   `active_receiver`, `inactive_canonical`, `stale_artifact`,
   `inaccessible`, `unrelated`, `unknown`.

## Decision Rule

Treat a candidate as `active_receiver` only when runtime evidence shows a live
Telegram receiver process/service and fresh receiver state. Treat missing,
inactive, disabled, or artifact-only evidence as non-active. If token identity
cannot be fully proven because only `getWebhookInfo` is allowed, retain that
risk explicitly instead of calling identity-only Bot API methods.
