# Home-first implementation status

Status date: 2026-07-12.

This file reports implementation truth for the clean candidate. It does not report production readiness.

## Authorities

| Concern | Current candidate truth | Target authority |
| --- | --- | --- |
| Code | clean Git worktree at base `9028a20d` | reviewed Git commit on Home mirror |
| Task lifecycle | Python compatibility runtime; Rust task service remains shadow-only | Rust Control Plane under logical identity `home` |
| Projects/responses | compatibility implementations and donor prototypes | PostgreSQL Program Ledger plus transactional outbox |
| Events/mailboxes | compatibility event stores | NATS JetStream quorum |
| Artifact bytes | compatibility filesystem/artifact adapters | immutable S3-compatible CAS |
| Public model | `kolibri` contract | `kolibri` |

The candidate now contains an internal loopback-only Rust response core. It
issues exact-Origin public sessions with hashed credentials and persists
response creation, per-response event sequences, cancellation idempotency and
transactional outbox records only in PostgreSQL. Provider execution and public
routing are deliberately outside this bounded slice; no production service has
been switched to it.

## Home storage fact

The read-only inventory on 2026-07-12 confirms one Samsung 250 GB NVMe device on Home. Its root ext4 filesystem has 128,172,183,552 bytes available (about 119.4 GiB). After preserving a 20% filesystem reserve, about 78 GiB remains eligible for bounded development artifacts and one CAS replica.

Home is therefore no longer excluded for lack of space. It is not treated as the only artifact authority: placement still requires disk-health/performance attestation and two replicas on different failure domains.

## Home development preflight

The canonical `/home/ladik/src` mirror/control/tasks layout already exists on Home. The control worktree is clean but still points at the earlier `2a885d69` integration state, the current foundation branch is absent from the mirror, the task directory is empty, and the releases directory is missing. Mac is therefore not yet a thin client.

After this candidate is committed and verified, the owner-gated development bootstrap will fetch the mirror, refuse any dirty Home worktree, safely switch to the accepted foundation branch and create the missing releases directory without restarting production. Thin-client status is proved only after a task worktree, test run, commit and artifact originate on Home.

The candidate runtime authority files pin Node.js `26.5.0` and Python `3.14.6`.
The Home preflight still reports Python `3.12.3`, so the bootstrap is expected to
fail closed until a separate owner-approved toolchain update has been completed
and verified. This candidate does not install either runtime on Home.

## Donor policy

- Clean V2 contributes POST-first session bootstrap, project lifecycle, resumable SSE, strict artifact byte validation, deterministic estimate arithmetic and tests.
- Clean V2 SQLite storage, daemon threads, in-memory cancellation and client-authored assistant messages are rejected.
- The tracked `kolibri-core` contributes durable event, DAG, lease, fencing, hash and parity contracts.
- Dirty Rust service worktrees, generated `target/` trees and placeholder schedulers are not imported wholesale.
- The current Vista/product runtime remains untouched as evidence and a compatibility source.

## Active gates

1. Preserve repository and donor truth without reading or copying secrets.
2. Reject executable runtime fallbacks to legacy Control Plane identities or fixed endpoints.
3. Pin and verify the stable Rust foundation toolchain.
4. Implement durable response/task binding behind the frozen OpenAI-compatible API.
5. Build the new Shell against generated contracts, not legacy transport.

Production, DNS, credentials, destructive actions and service restarts remain owner-gated.
