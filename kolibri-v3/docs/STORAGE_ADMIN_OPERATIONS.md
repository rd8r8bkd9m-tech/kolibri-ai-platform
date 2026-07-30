# Storage administration for Home and Primary

Status: control plane and opt-in Home adapter implemented, execution disabled  
Last verified inventory: 2026-07-30 14:34 MSK

This document is the canonical safety and rollout contract for the owner-only
storage panel. It complements `INFRASTRUCTURE_ACCESS.md`; it does not authorize
an agent or operator to delete a path merely because that path appears here.

## Product boundary

The browser talks only to the Product/Data API:

```text
owner browser
  -> same-origin Next BFF
  -> /v1/platform-admin/storage
  -> typed StorageNodeExecutor
  -> privileged node agent
```

The browser can submit only fixed enums and opaque server-issued identifiers.
It cannot submit a filesystem path, shell command, Docker identifier, systemd
unit or arbitrary cleanup rule.

The Product/Data backend must not receive root SSH authority. The production
executor is a separate minimal Rust node agent:

- the implemented Python adapter supports Home only through the exact private
  Unix socket `/run/kolibri-storage-executor/executor.sock`;
- Primary remains unavailable until its Home/Primary mTLS transport is
  designed, enrolled and reviewed;
- no shell, subprocess or SSH transport exists in the Product/Data adapter.

Until that executor is installed and enrolled, the API and UI remain
fail-closed and show `executor unavailable`.

The adapter is disabled by default with
`KOLIBRI_V3_STORAGE_EXECUTOR_ENABLED=false`. Enabling it requires protocol
`v1`, a 64-character expected policy digest and the exact Home socket,
executable and policy identity paths. The executable and policy paths are
identity metadata only: Product/Data neither launches the executable nor
reads the policy file. Every node response must match protocol `v1`; signed
inventory must attest the configured policy digest before mutation is
available.

The complete opt-in identity is:

```text
KOLIBRI_V3_STORAGE_EXECUTOR_PROTOCOL_VERSION=v1
KOLIBRI_V3_STORAGE_EXECUTOR_HOME_SOCKET_PATH=/run/kolibri-storage-executor/executor.sock
KOLIBRI_V3_STORAGE_EXECUTOR_HOME_EXECUTABLE_PATH=/usr/local/libexec/kolibri-storage-executor
KOLIBRI_V3_STORAGE_EXECUTOR_HOME_POLICY_PATH=/etc/kolibri-storage-executor/policy.json
KOLIBRI_V3_STORAGE_EXECUTOR_HOME_POLICY_DIGEST=<64 lowercase hex>
KOLIBRI_V3_STORAGE_EXECUTOR_ENABLED=false
```

Keep `ENABLED=false` through inventory-only rollout. Request/response limits
and timeout also have bounded settings; values outside the adapter's hard
ceilings fail application configuration.

## Current capacity truth

Home currently has one physical NVMe device. Its LVM volume group contains:

- a 210 GiB root logical volume mounted at `/`;
- 19.83 GiB of unallocated volume-group extents.

The unallocated reserve is a separate read-only capacity segment. It is not
free space on `/`, must never be summed with filesystem free space, and cannot
be allocated from the storage panel. Extending or repartitioning LVM is a
separate maintenance operation.

Live read-only verification on 2026-07-30:

| Node | Root available | Root use | Available memory |
|---|---:|---:|---:|
| Home | 48 GiB | 77% | 11 GiB |
| Primary | 25 GiB | 74% | 7.9 GiB |

Configured topology records shown while the executor is unavailable must be
labelled as recorded, not live. Once the executor is ready, capacity segments
come from its signed inventory response.

## Required protection set

Every inventory, preview and execute request must revalidate all of these
guards:

- active release and every current/canary symlink target;
- the primary database, WAL/SHM, backups and credentials;
- Docker volumes and bind mounts;
- durable agent runtime state and retained agent result artifacts;
- systemd, Nginx, cron, Docker and open-file/cwd/exe references;
- at least two known-good rollback releases.

Any missing, stale or ambiguous guard fails closed.

Important current protected roots include:

- `/opt/kolibri-v3/current`, `/opt/kolibri-v3/var` and `/etc/kolibri-v3`;
- `/home/ladik/src/kolibri-ai-platform`;
- `/home/ladik/qwen-kolibri-rust-gateway`;
- `/home/ladik/kolibri-fabrika` and `/srv/kolibri/repo`;
- `/home/ladik/.kolibri-agent/artifacts`;
- `/opt/kolibri-ai/current` and referenced legacy release components;
- Primary `/var/lib/kolibri-agent`, `/opt/actions-runner`,
  `/home/runner/actions-runner`, `/opt/kolibri-ai-platform` and
  `/srv/kolibri`.

## Allowlisted categories

### Build

- unused Docker BuildKit cache older than policy retention;
- incomplete executor-owned release staging directories with no live
  reference or open descriptor.

Never run a generic `docker system prune -a`. Tagged images, volumes and
release directories are not build cache.

### Cache

Only literal policy roots may be registered, for example package-manager
caches and executor-owned test/release caches. A generic `.cache`,
`node_modules` or `.next` scan is not an authorization rule.

### Logs

- archived journald segments down to the configured size/retention floor;
- JSON logs belonging to stopped containers only, where the exact path is
  derived from and revalidated through the Docker API.

Active container logs are protected.

### Stopped containers

Only containers carrying the explicit
`ai.kolibri.storage.disposable=true` label are actionable. They must be
stopped for the configured retention period and have no volume, bind,
restart-policy, systemd or Compose reference. Existing unlabeled legacy
containers remain blocked.

### Projects

Project candidates come from a root-owned signed allowlist containing literal
paths and opaque project IDs. Runtime globs such as `dev-c*` are forbidden.
The executor excludes canonical Product/Data projects and any path with a
live operational reference.

Current deferred classes:

- old `dev-c*`, FormulaLM and test trees require an explicit allowlist;
- `/home/ladik/kolibri-projects` remains blocked by stopped Compose
  references;
- `/home/ladik/.kolibri_vault/bench_qualified` remains blocked as
  unclassified benchmark data;
- old V3 releases require a separate release-retention policy;
- `/opt/kolibri-ai/p7-components` requires a separate decommission manifest
  because systemd/Nginx references still exist.

## Preview, execute and recovery

1. Inventory is read-only and returns actionable and blocked items separately.
2. Preview has a 15-minute TTL and records the exact inode/device/size/mtime
   set, policy digest and node generation.
3. Execute accepts only the opaque preview reference and one operation ID.
4. Node-local durable idempotency returns the same result for the same
   operation ID and rejects a changed payload.
5. Before the browser receives an operation ID, a central `pending` operation
   can be rediscovered only with the same idempotency key.
6. Once the operation ID is known, `POST
   /v1/platform-admin/storage/operations/reconcile` queries the node `status`
   journal and never calls `execute`. This recovery survives browser
   `sessionStorage` loss because pending IDs are durable central records.
7. A transport or protocol exception never terminalizes central `pending`.
   Only a validated node `OperationResult` with `succeeded` or `failed` may do
   so.
8. The executor rejects any result whose item or byte count exceeds preview.
9. Central and node-local audit records must agree before the operation is
   considered reconciled.

Long-running recursive work must use an asynchronous executor job with status
polling or a hard bounded synchronous limit. An ambiguous timeout is never
reported as success.

## Project lifecycle

- `quarantine`: atomic same-filesystem rename into a node-owned quarantine;
  reclaimed bytes remain zero;
- `restore`: atomic return when the original target is free and policy still
  permits it; it targets only a retained quarantine ID, requires a fresh
  preview and explicit `RESTORE`, and is blocked if the project has become
  authoritative;
- `purge`: available only after seven days, fresh owner authentication, a new
  preview and explicit `PURGE` confirmation;
- no automatic purge.

Additive migration 043 supports restore state, reconciliation counters and
strict lowercase-hex storage IDs while preserving valid v42 rows.

The Rust protocol implements restore and durable status, but the current
executor build deliberately reports mutation evidence as incomplete
(`executeEnabled=false` and no dynamic guard attestation). The Python adapter
therefore keeps mutation unavailable. This is not a production enablement or
an installation claim.

## Rollout gates

1. Keep execution disabled; merge API/UI and migration recovery tests.
2. Test the Rust agent in an isolated VM: symlink race, mount crossing, open
   descriptors, service/container activation, policy tamper, replay and power
   loss.
3. Install both agents in inventory-only mode and reconcile their output with
   `df`, LVM, Docker and journald.
4. Enable preview-only on Home.
5. Pass a synthetic quarantine and restore drill.
6. Enable small Home cache/build/log operations with hard limits.
7. Enable Primary only after Home audit/reconciliation remains clean.
8. Permit the first purge only after the full retention window and a tested
   restore path.

Rollback disables execution in Product/Data, revokes the executor certificate
and stops/masks the node agent. Existing quarantine data is retained and the
additive database migration is not rolled back.
