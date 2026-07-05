# P0 Telegram Fleet Receiver Discovery Next Probes

Because an active receiver was found on `main`, the next probes are not for
receiver discovery; they are for closing residual identity and access risk
without consuming Telegram updates.

## Exact Next Probe Set

1. Secret-management lineage check:
   - Compare the source record for `main:/etc/kolibri/telegram.env` against the
     intended `@kolibriai_bot` secret record.
   - Record only `matches_expected_kolibriai_bot_secret=true|false`; do not
     print token values or token hashes.

2. Explicitly approved identity-only Bot API check:
   - If approved by the owner/control plane, call a non-consuming Bot API
     identity method for the `main` token and record only:
     `username_matches_kolibriai_bot=true|false`.
   - Do not call update-consuming or webhook-mutating methods.

3. Access follow-up for inaccessible nodes:
   - Re-run bounded metadata-only SSH probes for `mesh-agent-01`,
     `mesh-agent-02`, and `mesh-agent-03` from a node with valid access.
   - Commands must collect only service status, state-file metadata, sanitized
     process/container/tmux listings, and no environment values.

4. Primary-candidate recheck:
   - Re-run the metadata-only receiver probe on `primary-candidate` from a node
     with valid SSH permission.
   - Expected confirmation: gateway inactive/disabled, no state file, no
     receiver process.

5. PR #89 handling:
   - Keep PR #89 draft.
   - Do not merge, close, or push until the active `main` receiver and token
     lineage are reconciled with the intended canonical receiver plan.

## Stop-Service Rule

Do not stop any Telegram service unless a future probe proves exactly one stale,
non-canonical receiver and also proves that the `main` receiver remains healthy.
