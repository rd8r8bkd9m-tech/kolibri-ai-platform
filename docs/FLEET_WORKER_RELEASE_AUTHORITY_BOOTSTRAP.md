# Fleet worker release-authority compatibility bootstrap

Status: source/runbook contract, 2026-07-12. This document does not claim a
live canary or fleet rollout.

## Purpose

Existing workers may run an Agent Host and release-helper socket while still
lacking the worker-local release policy and public signer trust. That state
cannot accept the first signed Agent Host runtime through the Home Control
Plane API.

`scripts/bootstrap-fleet-worker-release-authority.sh` is the one-time,
owner-operated compatibility bridge. It is deliberately narrower than the old
Home-only bootstrap:

- membership is read from the replicated mesh manifest;
- the logical `home` member is always excluded;
- no expected fleet count, hostname or fixed canary exists in source;
- worker order is seeded by the signed release manifest digest;
- waves are `1 → 2 → 3 → 5 → rest`;
- only public signer trust, release-helper runtime/unit files, the worker
  policy and its fixed health checker are installed;
- Control Plane, backend and Agent Host services are never installed or
  restarted by this bootstrap;
- the default mode is read-only;
- every target creates checksummed backups and automatically restores its
  prior files, directory metadata and helper-unit state when a gate fails.

After this bridge passes, normal Agent Host release and rollback work returns
to the Home Control Plane API and the signed progressive rollout described in
`docs/AGENT_HOST_PROGRESSIVE_ROLLOUT.md`.

## Worker policy

`ops/release-policy.worker.json` has an empty `services` and
`default_services` set. It requires exactly:

```text
ops/agent_host.py
ops/mimo/kolibri-response-only.md
```

The pre-gate accepts a safely contained historical product-only current
release. Candidate and post-gates require the complete root-owned,
non-writable Agent Host/profile pair, and the post-gate also proves that the
atomic `current` symlink selected that candidate. No payload code is executed
by a health check.

## Operator sequence

Use the digest of the exact signed release manifest planned for the first
Agent Host campaign. The signer input must be a public OpenSSH key; private key
material is not accepted or staged.

Read-only preflight of every current non-Home member:

```bash
scripts/bootstrap-fleet-worker-release-authority.sh \
  --manifest /secure/runtime/peers.json \
  --release-digest sha256:SIGNED_MANIFEST_DIGEST \
  --signer-public-key /secure/runtime/release-signer.pub \
  --signer-identity kolibri-owner
```

Review the emitted membership fingerprint, seeded canary and every preflight
result. A dry run performs zero worker mutations.

Apply only the selected dynamic canary:

```bash
scripts/bootstrap-fleet-worker-release-authority.sh \
  --manifest /secure/runtime/peers.json \
  --release-digest sha256:SIGNED_MANIFEST_DIGEST \
  --signer-public-key /secure/runtime/release-signer.pub \
  --signer-identity kolibri-owner \
  --run-id worker-release-authority-YYYYMMDD \
  --canary-only \
  --apply
```

The target must return `applied` or `already_applied`, advertise
`release_apply_v1` on its next Agent Host heartbeat, and then complete the
signed release plus read-only runtime handshake before the full compatibility
bootstrap is allowed.

Full progressive apply uses the same reviewed inputs without
`--canary-only`:

```bash
scripts/bootstrap-fleet-worker-release-authority.sh \
  --manifest /secure/runtime/peers.json \
  --release-digest sha256:SIGNED_MANIFEST_DIGEST \
  --signer-public-key /secure/runtime/release-signer.pub \
  --signer-identity kolibri-owner \
  --run-id worker-release-authority-YYYYMMDD \
  --apply
```

The controller preflights every selected target before the first mutation and
stops on the first failed target. Per-target rollback evidence is stored under
`/var/backups/kolibri/fleet-release-authority/<run-id>/`. A failed or rolled
back bootstrap is not release success and must not be converted into `21/21`.

## New nodes

The canonical new-node bootstrap must install the same worker policy and
public trust. If a new node is present in membership before a reviewed run, it
is included automatically. If membership changes after a plan is reviewed,
generate a new digest-bound plan instead of reusing the old target set.
