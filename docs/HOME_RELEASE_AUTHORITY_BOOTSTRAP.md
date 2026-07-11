# Home release authority bootstrap

Status: implemented, not applied to a live host.

This is the one-time owner-operated bootstrap for the privileged immutable
release boundary on the canonical Home node. It does not deploy a product
release, does not change the mesh, and does not create another Control Plane.
Normal releases remain signed, owner-approved, progressive API tasks after
this prerequisite is available.

## Safety boundary

- `scripts/bootstrap-home-release-authority.sh` is a dry-run unless `--apply`
  is explicit.
- The target is the unique `node_id=home` record in the supplied replicated
  mesh manifest. There is no embedded IP address or legacy authority fallback.
- The wrapper verifies that the manifest-selected mesh address is assigned to
  the remote host before staging anything.
- `--signer-public-key` must point to one OpenSSH public key. The bootstrap has
  no private-key argument, does not read key material from environment
  variables, and never prints the public-key body. Evidence contains only the
  signer identity and a SHA-256 digest of the normalized public trust row.
- Existing trust is one-time/idempotent: an identical allowed-signers row is
  accepted; different existing trust fails closed. This command is not a key
  rotation mechanism.
- Required parent directories must be root-owned and non-writable by group or
  world. The sole exception is the standard `/run/lock` boundary, accepted
  only with the exact root-owned sticky mode `01777`.
- The backend systemd drop-in is deliberately outside this bootstrap. It must
  be installed only by a separate signed release after backend health and
  rollback gates are approved.

## What `--apply` installs

Only these authority prerequisites are managed:

- `/etc/kolibri/release_allowed_signers` — public release signer, root-owned
  mode `0600`;
- `/etc/kolibri/owner_allowed_signers` — public owner-approval signer,
  root-owned mode `0600`;
- `/etc/kolibri/release-policy.json` from
  `ops/release-policy.home.json`;
- current `release_authority.py`, `release_helper.py`, and
  `release_installer.py` under `/usr/local/lib/kolibri`;
- current `kolibri-release-helper.service` and `.socket` units;
- root-only `/var/lib/kolibri-release/artifacts` mode `0700`;
- trusted root ownership and non-writable modes for `/opt/kolibri-ai`, its
  `releases` directory, and the current release directory when one exists.

The program does not touch provider credentials, environment files, Telegram,
DNS, firewall rules, backend drop-ins, or private signing keys.

## Dry-run

Use the same real manifest and public key intended for the apply:

```bash
scripts/bootstrap-home-release-authority.sh \
  --manifest "$HOME/.kolibri-mesh/peers.json" \
  --signer-public-key /path/to/kolibri-release-owner.pub \
  --signer-identity kolibri-owner
```

The dry-run validates local source files and public-key syntax, resolves Home
from the manifest, proves the remote network identity, and checks required
commands and the `kolibri-agent` account. It also streams a read-only preflight
program over SSH to verify current-target containment, existing trust digest,
managed path types, and the backup boundary. It does not create a remote
staging directory or modify systemd.

## Owner-controlled apply

Only after reviewing the dry-run result and current Home backup capacity:

```bash
scripts/bootstrap-home-release-authority.sh \
  --manifest "$HOME/.kolibri-mesh/peers.json" \
  --signer-public-key /path/to/kolibri-release-owner.pub \
  --signer-identity kolibri-owner \
  --apply
```

The remote transaction creates a root-only evidence directory below
`/var/backups/kolibri/release-authority/<run-id>`. Before any `/opt` ownership
or mode repair it records:

- copies and metadata for every managed file that already exists;
- systemd enable/active state;
- recursive `/opt/kolibri-ai` metadata without following symlinks;
- SHA-256 checksums for regular files below `/opt/kolibri-ai`.

It then revalidates that `/opt/kolibri-ai/current`, if present, resolves to one
direct child of `/opt/kolibri-ai/releases`. An outside, broken, non-symlink, or
ambiguous current target aborts the transaction.

After atomic file installation the before/after content checksums must match.
The installer `prerequisite_status` must be `available`, systemd is
daemon-reloaded, the socket and helper are restarted, and a status request is
made through the Unix socket as `kolibri-agent`. A heartbeat or successful
systemd command alone is not accepted as the gate.

## Rollback behavior

Any failure after mutation starts triggers rollback inside the same locked
transaction:

1. stop the helper service and socket;
2. restore or remove every managed file according to the backup;
3. restore prior directory ownership and modes, removing newly created empty
   directories;
4. daemon-reload systemd and restore the previous enable/active state;
5. write a sanitized `transaction.rollback.json` in the root-only backup.

The CLI returns only error codes and rollback status. If rollback itself is
incomplete, the result is explicitly `release_authority_rollback_failed` and
must be treated as an operator incident; no release task may run.

Systemd/helper activation failures are also intentionally classified without
command output: daemon reload, socket enable, socket restart, service restart,
inactive socket, inactive service, and socket probe each have a distinct
`release_authority_*` error. A reachable helper that reports unavailable local
prerequisites remains the separate `release_authority_prerequisite_gate_failed`
condition.

## Verification before the first release

The bootstrap result must show:

```text
status=applied
prerequisite_status.status=available
target_node=home
backend_release_dropin=not_installed_by_this_bootstrap
```

Then verify separately, without exposing environment values:

```bash
ssh root@<manifest-resolved-home> \
  'systemctl is-active --quiet kolibri-release-helper.socket && systemctl is-active --quiet kolibri-release-helper.service'
```

The first actual bundle still requires a signed manifest, a separate owner
approval attestation, a canary release task, content-bound evidence, and the
normal automatic rollback gate.
