# Release Installer Contract

Status: implementation contract, 2026-07-10. This document does not claim a
production rollout or a verified 21-node release.

## Authority and capability

- Home is the only Control Plane and release task authority.
- Workers accept only `release_bundle_apply` and `release_bundle_rollback`
  tasks carrying `required_capability=release_apply_v1`.
- Agent Host removes a configured `release_apply_v1` claim and adds it back
  only when local prerequisites are currently available.
- Capability prerequisites are trusted, non-symlinked artifact/release roots,
  a safe existing `current` link (if present), `ssh-keygen`, a non-empty local
  `release_allowed_signers` file, and a valid local release policy. Trusted
  files and directories must be owned by root or the Agent Host account and
  must not be group/world writable.
- Bootstrap installs the worker code and directories but does not fabricate
  owner trust or health policy. Until those operator-managed files exist, the
  node does not advertise release capability.

Home's one-time trust bootstrap is defined in
`docs/HOME_RELEASE_AUTHORITY_BOOTSTRAP.md` and implemented by
`scripts/bootstrap-home-release-authority.sh`. It is dry-run by default,
discovers Home only from mesh membership, accepts public signer material only,
backs up checksums and metadata before trust repairs, and rolls back the whole
managed transaction on a failed prerequisite or systemd gate. It deliberately
does not install the backend release drop-in.

## Bundle layout

Canonical archives are produced by `ops/release_bundle_builder.py`; its
read-only plan is the default and final bundle creation requires separate
`--build` and `--sign` opt-ins. See `docs/RELEASE_BUNDLE_BUILDER.md`.

The worker accepts a bounded tar archive with this exact layout:

```text
.kolibri-release/manifest.json
.kolibri-release/manifest.sig
payload/<manifest file path>
```

The manifest uses `kolibri.release.v1`; its on-disk bytes must already be the
canonical UTF-8 JSON form with sorted keys and compact separators. Duplicate
JSON keys and non-finite values are rejected. Every payload file declares
`path`, lowercase SHA-256, byte size, and a safe four-digit octal mode. The
payload file set must match the manifest exactly.

The detached signature is verified again on the worker with:

```text
ssh-keygen -Y verify
namespace: kolibri-release
allowed signers: /etc/kolibri/release_allowed_signers
```

`verified_by_controller` is never treated as proof. The worker uses the signer
identity only to select an identity already present in its local allowed
signers file. It opens that file without following symlinks and gives
`ssh-keygen` a private point-in-time snapshot, so an atomic trust-file swap
cannot change the verification input mid-check.

## Artifact sources

- `artifact://...` is opened by descriptor-walking each path component below
  the root-owned, helper-only `/var/lib/kolibri-release/artifacts` (the
  `KOLIBRI_ARTIFACT_ROOT` for the privileged helper) with no-follow semantics.
  It is deliberately separate from worker-created task artifacts. Traversal, parent swaps,
  and symlink escapes are rejected.
- Remote artifacts must use credential-free `https://` without query or
  fragment. Redirect targets are validated again.
- Downloads are streamed into a private task artifact, bounded by compressed
  size, wall-clock timeout, unpacked size, and member count.
- Tar absolute paths, traversal, duplicate paths, symlinks, hard links,
  devices, FIFOs, and unknown member types are rejected. Extraction is manual;
  `extractall` is not used.

## Activation and rollback

1. Run locally configured pre-health checks without a shell.
2. Fetch, extract, canonicalize, verify signature, and verify every file.
3. Rename staging to `/opt/kolibri-ai/releases/<release_id>` on the same
   filesystem. Existing releases are never overwritten and must revalidate.
4. Atomically replace `/opt/kolibri-ai/current` with a symlink to the immutable
   release.
5. Restart only task-selected services that are present in the local policy
   allowlist, using fixed `systemctl try-restart` argv.
6. Run locally configured post-health checks with individual timeouts.
7. On activation or health failure, atomically restore the prior symlink,
   restart the same allowlisted services, and re-run post-health checks.

An idempotent replay of the same signed release revalidates the immutable
directory and health gates. A reused `release_id` with a different digest is a
hard collision.

The Agent Host service itself is permanently excluded from the service
allowlist. A release task cannot terminate the worker that owns its lease and
rollback transaction. Long downloads, extraction, hashing, service actions,
and health checks refresh the task lease; local subprocesses use process-group
timeouts and their stdout/stderr is discarded rather than copied into logs.

## Local policy

`KOLIBRI_RELEASE_POLICY` defaults to `/etc/kolibri/release-policy.json`:

```json
{
  "schema_version": "kolibri.release-policy.v1",
  "services": ["kolibri-ai.service"],
  "default_services": [],
  "pre_health": [
    {
      "name": "backend-baseline",
      "argv": ["/usr/local/lib/kolibri/check-backend-health"],
      "timeout_seconds": 15
    }
  ],
  "post_health": [
    {
      "name": "backend-activated",
      "argv": ["/usr/local/lib/kolibri/check-backend-health"],
      "timeout_seconds": 20
    }
  ],
  "service_timeout_seconds": 30
}
```

Health argv comes only from this local operator-managed policy. Shell
executables are forbidden. Task fields such as `command`, `commands`, `shell`,
`script`, or task-provided health commands are rejected at any nesting depth
and never executed. Health executables must be absolute, executable, trusted
regular files.

## Completion evidence

Successful task results include the canonical `manifest_digest`, bundle hash,
immutable release path, switch/idempotency state, sanitized service and health
check outcomes, and:

```json
{
  "release_health": {
    "status": "healthy",
    "release_id": "...",
    "manifest_digest": "sha256:...",
    "checked_at": "..."
  }
}
```

`release_health.status=healthy` is emitted only after all post-activation
checks pass. Logs contain event codes, release ID, digest, and rollback status;
they do not contain artifact URLs, signatures, command output, credentials, or
environment contents.

## Threat and safety notes

| Threat | Enforced boundary |
| --- | --- |
| Competing Control Plane | Home-only endpoint resolver and one task authority |
| Forged controller success flag | Independent worker sshsig verification |
| Signer-file replacement race | No-follow read and private signer snapshot |
| Artifact root escape / TOCTOU | Descriptor-relative component walk with no-follow |
| Tar traversal or special files | Manual extraction and strict member types |
| Tar bomb | Compressed, unpacked, and member-count limits |
| Manifest/payload substitution | Canonical digest plus per-file SHA/size/mode |
| Task shell injection | No shell; command-bearing task fields rejected |
| Arbitrary service restart | Local service allowlist and fixed systemctl argv |
| Worker self-termination | Agent Host unit is forbidden in release policy |
| Lease expiry during long work | Throttled progress heartbeats across bounded stages |
| Failed activation | Prior symlink restored and health checked |
| Replay or release ID reuse | Idempotent same digest; collision on different digest |
| Secret leakage | Sanitized result and event-only release log |
