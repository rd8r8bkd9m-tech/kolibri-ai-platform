# Owner Merge Batch Proposal

No merge batch is approved by this file. The owner must explicitly approve any mark-ready or merge action in a later task.

## Proposed Batch 1: Docs

PRs:

- #88 `docs: add factory dispatcher ledger`, head `d4559722`.
- #92 `Document fleet role and capability inventory`, head `5a33c3fc`.

Why this batch is safe:

- Both are draft, clean, green PRs in the fallback snapshot.
- Scope appears documentation-oriented.
- They improve release/fleet context before runtime changes.

Required final checks:

- Recheck current head SHA, draft status, mergeability, and CI.
- Run `git diff --check` on each PR diff.
- Run a narrow secret-pattern scan over changed docs.
- Review #92 for stale fleet-capability claims.

## Proposed Batch 2: Runtime Safety Gates

PRs:

- #96 `[codex] Enforce read-only Agent Host permission packs`, head `42625cad`.
- #97 `[codex] Classify stale factory node heartbeats`, head `f542c5c7`.

Why this batch is safe:

- Both have focused release-decision artifacts marking them `merge_ready_after_owner_review`.
- Both improve safety/truthfulness before broader factory rollout.
- Both remain owner-gated drafts in the snapshot.

Required final checks:

- Recheck current head SHA, mergeability, CI, and draft status.
- Owner accepts post-merge Agent Host permission canary for #96.
- Owner accepts post-merge Control Plane freshness canary for #97.

## Proposed Batch 3: Fabric/API

PR:

- #85 `Finalize API-first full-control Fabric`, head `30b7e5dc`.

Why this batch is safe:

- PR85 release gate artifact says `merge_ready_after_owner_review`.
- GitHub snapshot says draft, clean, CI success.
- Fabric/API surfaces should be stabilized before MIMO and Telegram release gates.

Required final checks:

- Recheck current head SHA, mergeability, CI, and draft status.
- Run focused Fabric API contract tests.
- Run read-only task submission/status/artifact roundtrip after merge/deploy.

## Hold Queue

Held PRs:

- #91 until runtime safety gates are merged or owner explicitly accepts runner canary risk.
- #89 until single receiver/cutover safety is closed and owner accepts Telegram live-risk.
- #83 until overlap/supersession with #96 is resolved.

Forbidden by this task:

- Mark-ready, approval, merge, close, force-push, or push to `main`.
