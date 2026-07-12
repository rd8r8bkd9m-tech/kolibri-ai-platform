# Home Codex provider credential provisioning

Status: reviewed implementation candidate; no credential has been changed and
no production service has been restarted by this commit.

## Boundary

`home-codex-provider` is one Home-local external provider actor. Its HMAC
credential is not a Codex login and is never copied to a worker. The already
authorized Home owner's Codex CLI session stays in place and is used only by
the Home owner systemd service described in
[`HOME_CODEX_PROVIDER_SERVICE.md`](HOME_CODEX_PROVIDER_SERVICE.md).

Credential material is split deliberately:

```text
Home owner (0600)                              root (0600)
~/.local/share/kolibri/home-codex-provider/    /etc/kolibri/
  config/external-provider-actor.credential     external-provider-actor.sha256
  └─ raw node-bound HMAC token                   └─ SHA-256 verifier + id/epoch
```

The raw token is never printed, passed on a command line, written to the root
record, or returned by an API. The verifier hash is staged in a private owner
file and consumed by an approved root helper. CLI output contains only the
non-secret credential ID, epoch and binding status.

## Files

- `scripts/linux/provision-home-codex-provider-credential.py` — owner phase,
  dry-run by default.
- `scripts/linux/home-codex-provider-credential-root.py` — reviewed root phase
  source. Before use it must be installed as the fixed root-owned executable
  `/usr/local/libexec/kolibri-home-codex-provider-credential-root`, mode `0755`
  or stricter, through the owner-approved Home administration path.

The provisioner refuses a missing, user-owned, group-writable or
world-writable helper. It invokes the fixed helper through non-interactive
`sudo`; the sudoers grant must authorize only that exact root-owned executable.
Installing the helper or sudoers rule is a protected deployment action and is
outside this source-only change.

## Dry run

Run as the Home owner, never as root:

```bash
python3 scripts/linux/provision-home-codex-provider-credential.py
```

Dry run validates identifiers, destination state and the requested epoch. It
does not generate a token, create a directory, invoke `sudo`, drain an actor or
restart a service.

## Owner-approved initial apply

After the reviewed helper and exact sudoers rule are installed:

```bash
python3 scripts/linux/provision-home-codex-provider-credential.py --apply
```

The controlled transaction is:

1. generate a dedicated node-bound token in the owner process;
2. atomically write the owner `0600` raw record;
3. stage only the verifier record in an owner `0600` file;
4. invoke the approved root helper without token/hash command-line arguments;
5. drain `home-codex-provider`;
6. require Control Plane diagnostics to report Redis `PONG`,
   `lease_index_total=0`, `expired_leases=0` and
   `stuck_heartbeat_tasks=0`;
7. atomically install the root-owned `0600` verifier record;
8. restart only `kolibri-factory-control.service`;
9. verify the non-secret `bound_node_id`, `credential_id` and exact `epoch`
   through `/v1/runtime/provider-actors`;
10. leave the actor drained.

If the new binding does not verify, the root phase restores the previous root
record (or absence), restarts only the Home Control Plane and reports whether
owner rollback is safe. The owner record is rolled back only after that
positive acknowledgement. If helper state is ambiguous, the new owner record
is retained, the actor remains drained and an operator must reconcile the two
records; the provisioner never guesses or silently downgrades.

The two privilege domains cannot share a filesystem transaction. They use two
atomic file replacements plus the drain and acknowledgement protocol above to
avoid a schedulable half-rotation.

## Exact epoch rotation

Rotation is explicit and accepts only `current_epoch + 1` in both the owner
and root phases:

```bash
python3 scripts/linux/provision-home-codex-provider-credential.py \
  --rotate --epoch 2 --credential-id home-codex-provider-v2 --apply
```

The existing owner and root records must both be safe regular `0600` files,
bound to `home-codex-provider`, and the root phase independently checks the
current epoch. Skipped, repeated and decreasing epochs fail before mutation.
The actor is never undrained by the provisioner.

## Activation remains separate

A successful result is `credential_installed_actor_drained` or
`credential_rotated_actor_drained`. It is not provider readiness. Next:

1. install/start the Home owner provider runtime separately;
2. prove fresh authenticated Codex readiness;
3. execute one fenced provider task with result hash and independent Home
   verifier;
4. explicitly approve an undrain in a separate operation.

No step in credential provisioning authorizes a 21-node rollout, copies Codex
browser/CLI credentials, or changes the canonical Home Control Plane identity.
