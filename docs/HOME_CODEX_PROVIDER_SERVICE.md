# Home Codex provider service

Status: reviewed implementation candidate; not installation or production
evidence.

## Purpose

`kolibri-home-codex-provider.service` makes the already-authorized Codex CLI
session of the Home owner available to the Kolibri factory without copying
that session to any worker.

```text
Shell / OpenAI-compatible client
              |
              v
        public model kolibri
              |
              v
     Provider Gateway on Home
              |
       strict read-only task
              |
              v
 home-codex-provider (audit actor)
              |
       current Home user session
              |
              v
           Codex CLI
```

This is one authenticated provider slot on Home. It does **not** claim that
Codex is logged in on 21 servers. The physical workers remain credential-free
and receive ordinary factory tasks only through Home. The actor is outside the
canonical physical fleet count, so it cannot turn a provider login into a fake
`21/21` execution claim.

## Security and authority boundary

- The service runs as the Home owner through that user's systemd user manager.
- It calls only `codex login status` and bounded Codex executions against the
  current user's session in place.
- It never opens, reads, copies, archives or logs a Codex authentication file.
- It never sends cookies, access tokens or refresh tokens to Home Control Plane
  or workers.
- Home Control Plane sees a separate node-bound HMAC actor credential. The raw
  HMAC value remains in a current-user `0600` file; Home stores only its
  SHA-256 verifier and credential metadata.
- Registration, heartbeat, lease, completion and failure requests are HMAC
  signed with nonce/replay protection.
- The actor can lease only the exact `kolibri.factory-provider.readonly.v1`
  envelope: `owner_remote_task`, one attempt, empty write scope, read-only,
  provider-managed network and source `control_plane=home`.
- Completion still requires the Home-issued `attempt_id`, lease owner,
  fencing token, non-empty result hash and independent Home verifier.
- The public model remains `kolibri`; Codex appears only as operator
  provenance.

`home_systemd_user` is accepted only with the signed label
`authority=home`. The installer additionally proves that the local host owns
Home's mesh address before it renders or installs anything. No Control Plane
URL, old hostname or static server IP is embedded in the unit.

## Installed layout

```text
~/.config/systemd/user/kolibri-home-codex-provider.service
~/.local/share/kolibri/home-codex-provider/
  config/runner-access.json
  config/external-provider-actor.credential  # current-user 0600
  runtime/releases/<source-sha256>/
  worktrees/
  artifacts/
  logs/agent-host.log
  logs/systemd-bootstrap.log
```

Runtime releases are content-addressed and tamper-checked. Child output passes
through the existing bounded redacting launcher; service stdout is disabled and
private logs are mode `0600`.

The service points Agent Host's release selector at its own private provider
runtime namespace. This prevents Home's ordinary physical-worker release
symlink from replacing the audit actor process with a runtime that does not
implement `home_systemd_user`; it does not change or write the physical-worker
release selection.

## Dry-run validation

Run this **on Home as the already-authorized owner**, not as root:

```bash
python3 scripts/linux/install-home-codex-provider.py \
  --mesh-manifest /var/lib/kolibri-mesh/peers.json \
  --provider-proxy-url http://127.0.0.1:18080
```

The local proxy option is optional. When supplied it must be an uncredentialed
HTTP endpoint on `127.0.0.1` with a non-privileged port. It is injected only
into Codex child processes; Control Plane and mesh traffic stay direct.

Dry-run validation proves:

- this machine owns Home's mesh IP;
- the runner declaration is Home-only and Mimo-disabled;
- the current user reports an authenticated Codex CLI session;
- runtime sources and unit rendering are valid;
- no static Control Plane URL or credential material entered the unit.

It does not create directories, install a unit, start a process or prove a
provider response.

## Protected activation sequence

Activation changes a long-running service and the scoped actor credential. It
therefore remains an owner-approved operation and is not performed by this
implementation commit.

1. Drain the intended `home-codex-provider` audit actor.
2. Prove Redis `PONG`, zero active leases, zero expired leases and zero stuck
   task heartbeats.
3. Provision one node-bound external-provider actor credential locally on
   Home with the dry-run-first owner/root transaction in
   [`HOME_CODEX_PROVIDER_CREDENTIAL_PROVISIONING.md`](HOME_CODEX_PROVIDER_CREDENTIAL_PROVISIONING.md).
   Never reuse or copy a Mac/worker credential. If the single current binding
   still belongs to `mac-codex-provider`, use the explicit next-epoch migration
   documented there so both actors stay drained and the old raw token is never
   transferred.
4. Keep the actor drained and verify that Home exposes the exact credential
   ID/epoch marker without returning the raw value.
5. Install without starting:

   ```bash
   python3 scripts/linux/install-home-codex-provider.py \
     --mesh-manifest /var/lib/kolibri-mesh/peers.json \
     --provider-proxy-url http://127.0.0.1:18080 \
     --apply
   ```

6. Enable user lingering through the approved Home administration path. The
   installer refuses `--start` when `Linger=yes` is not proven; this prevents a
   false 24/7 claim that stops at logout.
7. Start the exact managed unit with `--apply --start`.
8. Verify a fresh readiness record: current-user login authenticated, model
   `gpt-5.5`, sandbox `read-only`, exact readiness marker and age under 300
   seconds.
9. Explicitly undrain only after that readiness record passes.
10. Send one OpenAI-compatible request using public model `kolibri`; accept it
    only when the terminal factory task has matching Codex runner binding,
    attempt/fence evidence, result SHA-256 and independent Home verdict.

An installed or active systemd unit, a successful login status, a heartbeat or
an advertised `runner:codex` capability is not provider success evidence.

## Failure behavior

- If the browser/device session expires, the next bounded readiness refresh
  withdraws `runner:codex`.
- If the local proxy fails, readiness is unavailable; Control Plane does not
  move to `main`, `primary` or another authority.
- If the actor credential is missing, unsafe or bound to another node, Agent
  Host fails closed before registration.
- If systemd activation fails, the installer restores the previous managed
  unit and reloads the user manager.
- Provider routing may continue to another policy-approved executor, while
  the client still addresses model `kolibri`.

## Current limitation

This service reuses the reviewed Python compatibility Agent Host and external
provider actor contract. It is not the final Rust multi-slot supervisor and it
does not make the permanent Improvement Controller ready. Rust authority and
24-hour production soak remain separate release gates.
