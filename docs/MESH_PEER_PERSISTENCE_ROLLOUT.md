# Mesh peer persistence rollout

Status: implemented and dry-run verified; no production apply has been run.

## Purpose

Every manifest server already has replicated peer fragments, but a rebooted
node can return with only the peers embedded in `wg-kolibri.conf` when the peer
apply oneshot is absent. `scripts/rollout-mesh-peer-persistence.sh` converges
the helper, Python runtime and systemd unit without changing Mac routes,
stopping WireGuard or restarting the active VPN.

The target set always comes from the supplied membership manifest. The script
contains no worker, `main` or `primary` roster.

## Safety contract

- Default invocation is read-only.
- `--apply` is the only mutation gate.
- `--canary NODE` selects exactly one manifest member.
- Local payload and staged remote files are bound by SHA-256.
- The production source directory must be extracted from the normal signed
  Kolibri release bundle; this script never reads a signing key.
- Existing files and enablement state are copied into a root-only backup.
- The exact WireGuard runtime is captured root-only with `wg showconf`; it is
  never printed or copied off-node.
- Rollback uses `wg syncconf`, so the interface and the user's VPN stay up.
- The `wg-quick` activation timestamp must remain unchanged during apply.
- Acceptance requires every manifest peer except self in the runtime, at least
  two fresh handshakes, direct Mac SSH, and Home SSH.

## Commands

Read-only canary discovery:

```bash
scripts/rollout-mesh-peer-persistence.sh \
  --manifest /path/to/peers.json \
  --canary NODE
```

Explicit canary apply after the signed release and owner gate:

```bash
scripts/rollout-mesh-peer-persistence.sh \
  --manifest /path/to/peers.json \
  --canary NODE \
  --apply
```

Subsequent waves use `--only-node NODE --apply` or a manifest-wide `--apply`
only after the canary gates pass.

Backups remain under:

```text
/var/backups/kolibri/mesh-peer-persistence/<run-id>/<node-id>/
```

An automatic rollback is attempted on remote convergence, Mac SSH, or Home
SSH failure. A failed rollback is a release blocker and must not be hidden by
continuing to another node.
