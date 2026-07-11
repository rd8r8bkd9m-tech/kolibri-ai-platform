# Distributed mesh membership

Status: implementation contract; not a production rollout claim.

Kolibri servers use one replicated membership protocol. Every server runs the
same registrar and can accept an authenticated enrollment, exchange state, and
rebuild its local WireGuard peer fragments. There is no static registrar list
and no Control Plane dependency in membership. `home` remains the only
application Control Plane, but it is one registrar among the servers.

This contract preserves the already working 21-server bootstrap. It does not
change Mac routes, the active Amnezia/`utun` path, firewall, DNS, MikroTik, or
existing WireGuard private keys.

## Trust boundary

Membership writes use a pre-provisioned cluster HMAC credential. The credential
is loaded by systemd from `/etc/kolibri/mesh-registry.key` and exposed to the
process through the systemd credentials directory. It must be a regular file,
at least 32 bytes, and inaccessible to group/other users. Its value is never an
environment variable, response field, log field, manifest field, or artifact.

Every `POST` requires:

- cluster and registrar identity;
- timestamp within a bounded clock window;
- a one-use nonce;
- HMAC-SHA256 over method, path, timestamp, nonce, body digest, and cluster id.

Invalid cluster, signature, time, nonce, or identity returns the same stable
`authentication_failed` response. A repeated signed request is rejected.
Read-only `GET /v1/mesh/peers` remains unsigned only for the mixed v1/v2
migration window; it cannot mutate membership. The service binds to the
WireGuard address, not a public wildcard. Request bodies, queued connections,
and concurrent handler threads are bounded.

The cluster credential authenticates membership authority. It is not a
WireGuard private key. WireGuard private keys remain generated and stored on
their owning node; only public keys enter membership.

## Manifest v2

Canonical state is `/var/lib/kolibri-mesh/peers.json`, mode `0600`:

```json
{
  "schema_version": 2,
  "cluster_id": "kolibri",
  "epoch": 42,
  "records": {
    "node-id": {
      "node_id": "node-id",
      "public_key": "wireguard-public-key",
      "mesh_ip": "mesh-address",
      "endpoint": "host:port",
      "epoch": 42,
      "revision": 3,
      "origin": "registrar-id",
      "tombstone": false
    }
  },
  "peers": {
    "mesh-address": {}
  }
}
```

`records` is authoritative and retains tombstones. `peers` is a generated,
live-only compatibility projection keyed by mesh IP so current Home endpoint
resolution and fleet readers continue to work. A legacy v1 `{"peers": ...}`
file is migrated in memory and becomes v2 at the next real mutation. A v1
manifest is accepted from the rolling-migration pull path only; authenticated
v2 `sync` rejects it.

Validation is fail-closed:

- node ids are normalized and path-safe;
- WireGuard public keys must decode to exactly 32 bytes;
- mesh addresses must be private/CGNAT unicast IPv4 addresses inside the
  configured or interface-derived pool;
- endpoint syntax and port are bounded;
- one live node id, mesh IP, and public key may exist only once;
- schema and cluster changes are rejected;
- manifest and fragment symlinks are rejected.

Manifest writes use a same-directory temporary file, `fsync`, atomic rename,
and directory `fsync`. A crash can leave an unapplied but durable manifest; the
startup recovery and each discovery cycle retry fragment and WireGuard apply.
Mutation responses expose `apply_pending`, and the enrollment CLI exits
non-zero until local apply succeeds; durable state is not misreported as a
fully active peer.

## Deterministic convergence

Each local mutation increments the manifest epoch and that node's revision.
Records use the total order:

```text
(epoch, revision, tombstone, origin, canonical-record-digest)
```

The newest record for a node wins. A tombstone wins an otherwise equal live
record, preventing stale resurrection. Concurrent different nodes claiming the
same IP or public key are sorted by the same version order; one remains live
and every deterministic loser becomes a conflict tombstone. Re-exchanging the
same states is idempotent and all registrars converge byte-for-byte.

Tombstones are not automatically expired. This intentionally prevents an old
partition from resurrecting a removed peer. Compaction requires a future
owner-approved, epoch-aware protocol.

## Discovery and gossip

Registrars discover peers from:

1. explicit bootstrap seeds in `KOLIBRI_MESH_REGISTRY_SEEDS`;
2. live mesh IPs already present in the replicated manifest.

They do not scan `10.99.0.0/24` or assume that a particular host number is an
authority. Each cycle has bounded targets, worker count, request timeout, and
exponential backoff with jitter. A successful exchange pulls remote state,
merges it, and pushes the merged v2 manifest back through authenticated
`/v1/mesh/sync`.

The initial seed is discovery transport, not ongoing authority. Once a new
node learns membership it can exchange with any registrar.

## Local WireGuard reconciliation

The registrar writes `/etc/wireguard/kolibri-peers.d/<mesh-ip>.conf` with mode
`0600`. The address is validated before it becomes a filename. Directories,
targets, and parsed fragments cannot be symlinks; duplicate or unknown
directives fail closed. The apply helper passes validated values as separate
`wg` arguments and never evaluates shell content. Valid legacy fragments are
normalized to mode `0600` before they are applied.

`/var/lib/kolibri-mesh/applied-public-keys` tracks keys applied by this
registry. Reconciliation removes a key only when it was previously tracked and
is no longer in the managed fragment set. Unrelated peers on the interface are
not enumerated and removed. An inter-process file lock serializes the boot-time
oneshot helper and registrar-triggered apply, so their tracked-key snapshots
cannot overwrite each other.

## API and operator commands

| Contract | Purpose |
| --- | --- |
| `GET /healthz` | non-secret liveness, epoch, and truthful apply state |
| `GET /v1/mesh/peers` | v2 manifest plus v1-compatible live projection |
| `POST /v1/mesh/peers` | authenticated upsert or tombstone |
| `POST /v1/mesh/sync` | authenticated registrar-to-registrar merge |
| `POST /v1/mesh/allocate` | authenticated allocation or atomic auto-enroll |

The established CLI remains compatible:

```bash
kolibri-mesh-enroll allocate
kolibri-mesh-enroll enroll NODE_ID PUBLIC_KEY MESH_IP ENDPOINT
```

New automation should prefer the single mutation:

```bash
kolibri-mesh-enroll enroll-auto NODE_ID PUBLIC_KEY ENDPOINT
```

Removal is a tombstone, not deletion:

```bash
kolibri-mesh-enroll remove NODE_ID
```

The address pool comes from `KOLIBRI_MESH_ADDRESS_POOLS` or the actual prefix
on `wg-kolibri`; there is no hard-coded `1-21` fleet reservation or `22-99`
allocation loop. Allocation scanning is capped by
`KOLIBRI_MESH_ALLOCATION_SCAN_LIMIT` so a misconfigured broad prefix cannot
create an unbounded loop.

## Controlled migration of the existing fleet

No script in this change performs deployment or SSH.

Before enabling v2 on any live node:

1. Checksum and back up the current manifest, peer fragments, interface config,
   and service unit on every server.
2. Validate that the legacy manifest contains every current mesh peer with one
   unique node id, mesh IP, and valid public key, including non-registrar
   clients such as the Mac or MikroTik when they occupy addresses from the same
   pool. Do not synthesize missing members from a static list.
3. Provision the same cluster trust credential to all servers through the
   owner-gated secret channel, mode `0600`; never copy it through task output.
4. Install the non-secret registrar config with the node id, cluster id,
   bounded seeds, and optional address pool derived from the live interface.
5. Start one registrar in canary mode, verify that v1 loads without changing
   any live peer, then verify signed local mutation/reversal on an unused test
   identity.
6. Roll progressively. During the mixed window, old registrars can read the v2
   `peers` projection; new registrars can pull legacy state from known peers.
7. Accept each server only after manifests converge and Mac/Home reachability
   remains unchanged. Application capability execution is a separate gate.
8. Disable unsigned read compatibility only in a later release after 21/21
   registrars are proven v2.

Rollback restores the checksum-matched manifest/fragments/unit snapshot and
re-applies the already known-good interface state. It does not rebuild keys,
rewrite Mac routes, or disconnect the current VPN.

## Known limits and follow-up gates

P0 before production rollout:

- the shared credential and non-secret node config must be pre-provisioned on
  all 21 servers; the hardened unit intentionally refuses to start without the
  credential;
- the real 21-node v1 manifest must pass strict key/IP/node validation and be
  backed up before this code replaces the current registrar;
- node clocks must be synchronized inside the authentication window before
  signed gossip is enabled;
- mixed-version canary and rollback must be exercised without changing the
  working Mac/Home connectivity matrix.

P1 after safe rollout:

- allocation is coordination-free. Concurrent auto-enrollments converge
  deterministically, but a losing node must retry with a new address; a future
  quorum allocator can eliminate that retry window;
- add owner-approved cluster credential rotation with overlapping key ids;
- add epoch-aware tombstone compaction after every registrar acknowledges a
  safe lower bound;
- remove the unsigned v1-compatible read after the rolling migration is
  complete.
