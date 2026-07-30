# Kolibri Storage Executor

`kolibri-storage-executor` is the minimal privileged node-side boundary for
the owner Storage Admin. It is not a general remote shell and never accepts a
filesystem path, command, glob, Docker argument or unit name from its protocol.

Status: implementation foundation; **not enrolled or enabled in production**.

## Safety model

- Rust 1.85, edition 2024, pinned dependencies and a committed lockfile.
- One versioned JSON request on stdin, one JSON response on stdout.
- Ed25519-signed node policy; unknown fields and an invalid signature fail
  startup closed.
- Literal absolute roots are resolved only from policy. Protocol inputs are
  enums and opaque IDs.
- Unix directory descriptors, `O_NOFOLLOW`, `fstatat`, `renameat` and
  `unlinkat` keep recursive work below an opened allowlisted root. Symlinks,
  mount crossings, live `/proc` references and special files are blocked.
- Preview persists the exact device/inode/size/mtime/tree manifest, node
  generation, policy digest and expiry.
- SQLite uses WAL and `synchronous=FULL`. An operation is durably journaled as
  `applying` before mutation. Replays use the same `operationId`; changed
  payloads are rejected. `status` exposes `applying`, `succeeded` or `failed`.
- Project quarantine and restore are same-filesystem atomic renames followed
  by directory `fsync`. Purge requires a fresh preview after at least seven
  days. There is no scheduler and no automatic purge.
- The shipped policies have `executeEnabled: false`.

Every shipped binary and ordinary custom/debug build forces effective
execution off. Inventory is capacity/topology-only, always advertises
`guardedScopes=[]`, and returns zero actionable category/project candidates.
Preview and execute always fail with `guard_evidence_unavailable`, whether
`guardEvidence` is omitted or configured. Mutation tests use an internal
`cfg(test)` seam that is absent from the executor binary.

The non-authorizing parser foundation reads no commands. It can inspect
signed, digest-bound literal files for systemd, Nginx, cron and Compose plus
one bounded Docker inventory snapshot. Every file must be a root-owned regular
file, have no observed symlink component, be non-executable and not writable
by group or other. Content is bound to signed SHA-256 digests and provider
generations rather than trusted from `mtime`. Ambiguous expansion, includes,
unknown path-bearing directives, user-crontab arguments and relative Compose
host references fail parsing closed.

The Docker record binds a signed daemon identity, inventory generation,
canonical container-list digest and aggregate digest of configured Compose
files, with a maximum signed age of 15 minutes. It is still only an enumerated
snapshot, not proof of exhaustive live daemon state. Likewise, evidence files
currently use absolute-path traversal with final-component `O_NOFOLLOW`, not
descriptor-relative no-follow traversal for every component. These are
explicit P2 gaps, so parsed evidence cannot authorize scopes or actions. A
future exhaustive live config/daemon-generation attestation and read-only
Docker Engine Unix API/mTLS adapter require separate review.

The executor reports Build, Cache, Log and Stopped Container categories, but
all remain zero/non-actionable in ordinary builds. Direct removal of Docker
state is intentionally not implemented. It must be enabled only by a future
Docker Engine API adapter that revalidates the disposable label,
stopped age, mounts, binds, restart policy and Compose/systemd references.
Generic `docker system prune`, container-directory deletion and shelling out
to Docker are prohibited.

## Protocol

See [`PROTOCOL_V1.md`](PROTOCOL_V1.md). The transport-neutral engine supports:

- `inventory`
- `preview`
- `execute`
- `status`

The temporary transport is stdio. It can be placed behind the supplied local
systemd Unix socket or an SSH forced command. Primary mTLS enrollment remains
a rollout gate; stdio is not presented as the final mesh transport.

## Build and verify

```bash
cargo fmt --all -- --check
cargo clippy --all-targets --all-features -- -D warnings
cargo test --all-targets
cargo build --release --locked --bin kolibri-storage-executor
```

Do not copy `target/`. Install only the release executor binary; the offline
policy signer must never be installed on a node.

## Policy signing

Create a 32-byte Ed25519 signing key on an offline administrator workstation,
store its lowercase hex representation in a mode `0600` file, and keep it off
Home and Primary. Copy one policy template, remove the envelope's placeholder
signature so the file contains only the `policy` object, review every literal
root/guard, then sign:

```bash
cargo run --locked --bin kolibri-storage-policy-sign -- \
  --policy /secure/reviewed-policy.json \
  --private-key-file /secure/storage-policy-ed25519.hex \
  > /secure/signed-policy.json
```

Distribute only the signed policy and the 32-byte public key hex. Any policy
change requires a new signature and invalidates old previews.

## Central adapter gate

Production execution must stay disabled until the Product/Data adapter:

1. maps `executeEnabled=false` to disabled destructive UI/actions;
2. maps live `capacitySegments` and never adds VG reserve to root free bytes;
3. calls `status(operationId)` after an ambiguous transport interruption;
4. reconciles executor quarantine inventory into central state after a crash;
5. exposes restore end to end and passes a synthetic quarantine/restore drill;
6. compares central and node-local audit records before declaring success.

The current Python control plane does not yet satisfy all of these gates.

## Deployment and rollback

Use [`../../deploy/storage-executor/README.md`](../../deploy/storage-executor/README.md).
No file in this crate authorizes installing or enabling the executor.
