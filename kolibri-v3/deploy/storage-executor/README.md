# Storage executor deployment assets

These files are reviewed templates, not an installation script. They do not
modify Home, Primary or production.

Canonical product/runbook contract:
[`../../docs/STORAGE_ADMIN_OPERATIONS.md`](../../docs/STORAGE_ADMIN_OPERATIONS.md).

## Preflight

1. Build with Rust 1.85 and run all crate gates on the exact commit.
2. Complete the isolated-VM race/power-loss drill from the canonical runbook.
3. Create group `kolibri-storage`; keep the service user as root with the
   bounded systemd capabilities in the template.
4. Install only the executor binary to
   `/usr/local/libexec/kolibri-storage-executor`, owned root, mode `0755`.
5. Create `/etc/kolibri-storage-executor` root-owned mode `0750` and
   `/var/lib/kolibri-storage-executor` root-owned mode `0700`.
6. Create each literal policy root and its private
   `.kolibri-storage-trash` directory, owner root, mode `0700`. Never create a
   broad root such as a user's entire home or generic `.cache`.
7. Review the node policy against live open descriptors, systemd, Nginx,
   cron, Docker mounts/volumes and at least two rollback releases. Sign it
   offline. Install only the signed envelope and public key.
8. Diff the local systemd template against the installed unit. Start with
   `executeEnabled=false` and no execution `ReadWritePaths` drop-in.

The example signatures are deliberately invalid. The service must fail closed
until a reviewed policy is signed. The examples deliberately omit
`guardEvidence`: their inventory is capacity-only, `guardedScopes` is empty,
and all actionable counts are zero.

The optional enumerated evidence fields are parser groundwork only and remain
non-authorizing even when every configured file parses. They do not prove
that all live units, includes, cron sources, Compose projects or Docker daemon
objects were enumerated. Evidence reads also do not yet use descriptor-relative
no-follow traversal for every path component. Never let the executor write
its own evidence. This P2 foundation is not the future exhaustive live
config/daemon-generation attestation or read-only Docker Engine Unix API/mTLS
rollout gate.

## Inventory-only activation

```bash
systemd-analyze verify \
  /etc/systemd/system/kolibri-storage-executor.socket \
  /etc/systemd/system/kolibri-storage-executor@.service
systemctl daemon-reload
systemctl enable --now kolibri-storage-executor.socket
systemctl status kolibri-storage-executor.socket
```

Send an inventory request over the Unix socket and compare capacity with
`df`, the LVM metadata backup, Docker and journald. Home must return exactly
two read-only capacity segments: root LV and unallocated VG reserve. The
reserve is never added to root filesystem free bytes. Primary returns no LVM
segments.

With the shipped inventory-only policies, also verify `guardedScopes=[]`,
every category has zero items/bytes, preview fails
`guard_evidence_unavailable`, and `executeEnabled=false`.

Do not enable Product/Data mutation routes merely because the socket is
healthy. Reconcile `executeEnabled=false`, inventory and node audit first.

## Forced-command recovery

`authorized_keys.forced-command.example` uses OpenSSH `restrict` plus a fixed
binary command. Keep PTY, forwarding, agent forwarding and arbitrary commands
disabled. Replace both placeholders offline. This is a recovery fallback, not
the final Primary mesh transport.

## Future staged execution

No current release, debug or ordinary custom build can execute mutation.
Future execution would require all rollout gates in the canonical runbook, an
exhaustive attestation design, a separately reviewed code change, and a
systemd drop-in containing only exact `ReadWritePaths`. Never grant `/`,
`/home`, `/var`, the Docker root or release roots.

Policy changes alone cannot enable mutation.

Project operations require a successful synthetic quarantine/restore drill.
The first purge cannot occur before the full seven-day retention window.

## Rollback

1. Disable Product/Data storage execution and hide destructive controls.
2. Replace policy with a signed `executeEnabled=false` policy.
3. Stop and mask `kolibri-storage-executor.socket`.
4. Revoke the transport certificate/key or forced-command key.
5. Preserve `/var/lib/kolibri-storage-executor`, SQLite WAL/SHM, quarantine
   roots and audit evidence. Do not delete or automatically restore them.
6. Reconcile any `applying` operation by operation ID before another rollout.

Rollback never changes LVM, deletes a quarantine or rolls back the additive
central migration.
