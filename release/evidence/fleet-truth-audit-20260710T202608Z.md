# Kolibri fleet truth audit

- Captured: `2026-07-10T20:26:08Z`
- Scope: Home manifest, Mac/Home SSH reachability, Home Control Plane
  registrations, and durable execution evidence.
- Method: read-only HTTP, SSH and file-metadata probes. No service, route,
  WireGuard, VPN, manifest, host-key, Redis or task mutation was performed.
- Secrets: not read; public keys, endpoints, credentials and task content are
  omitted.

## Result

The fleet is **not proven 21/21 ready**.

| Layer | Proven result | Status |
| --- | --- | --- |
| Home membership projection | 21 peers; 21 unique node IDs; 21 unique mesh IPs | count/uniqueness pass |
| Signed distributed membership | Home still serves schema v1; no v2 records, registrar credential directive or HMAC verification in the deployed runtime | not proven / contract fail |
| Mac SSH, direct manifest mesh addresses | 11/21 | fail |
| Mac SSH, existing direct route plus existing Home ProxyJump | 20/21; `main` remains unreachable | fail |
| Home SSH, canonical `check-fleet.sh` path | 19/21; `main` times out and Home-to-self root SSH is rejected | fail |
| Home Control Plane canonical registrations | 21/21 canonical IDs present; 20 fresh, 1 stale (`main`) | partial |
| Home Control Plane registry hygiene | 136 logical registrations: 21 canonical + 115 noncanonical | fail |
| Canonical physical nodes with any completed task record | 4/21 | insufficient |
| Canonical physical nodes with explicit content hash + independent verifier evidence | 0/21 | fail |

## Membership facts

Home's live endpoint `GET /v1/mesh/peers` and its backing manifest agree on:

- schema version: `1`;
- peers: `21`;
- unique node IDs: `21`;
- unique mesh IPs: `21`;
- records/tombstones: `0/0` (v2 authoritative records are not present);
- manifest SHA-256: `a883f022eabde6fd2dfd197d7c25db2257020203e4e0d1803bb08f7fa786ee53`.

The Home registrar is active and enabled, but it is not the canonical hardened
runtime in the worktree:

- deployed registrar SHA-256:
  `376cf7283afb7314c5ecbe35cec6847a0033a5844d191a2bfb1143ccdef85a9c`;
- canonical worktree SHA-256:
  `471f3ae9cc794477cb7686fb1ea69d0ee7c3a7460570e5d2720a158e608ed60d`;
- deployed unit declares neither `LoadCredential` nor a registry trust-file
  directive;
- deployed code exposes a peer read path but no sync/allocate route and no
  HMAC/signature verification.

Therefore the live projection proves the current 21-entry inventory, but it
does not prove the signed, replicated, all-registrar membership contract.

## Physical matrix

`Mac route` is the first existing path that passed: direct mesh first, then an
unchanged `ProxyJump home` only for direct failures. `Home SSH` is the strict
canonical nested probe used by `scripts/check-fleet.sh`.

| Physical ID | Mesh IP | Mac route | Home SSH | CP freshness | Completed evidence observed |
| --- | --- | --- | --- | --- | --- |
| `9fts` | `10.99.0.5` | direct | yes | fresh | none |
| `agent01` | `10.99.0.8` | direct | yes | fresh | none |
| `agent02` | `10.99.0.9` | direct | yes | fresh | none |
| `agent03` | `10.99.0.11` | direct | yes | fresh | none |
| `agent04` | `10.99.0.12` | direct | yes | fresh | none |
| `agent05` | `10.99.0.13` | direct | yes | fresh | none |
| `agent06` | `10.99.0.14` | Home ProxyJump | yes | fresh | none |
| `agent07` | `10.99.0.15` | Home ProxyJump | yes | fresh | none |
| `agent08` | `10.99.0.16` | Home ProxyJump | yes | fresh | none |
| `agent09` | `10.99.0.17` | Home ProxyJump | yes | fresh | 2 read-only records; no current truth/verifier gate |
| `agent10` | `10.99.0.18` | Home ProxyJump | yes | fresh | none |
| `highload` | `10.99.0.19` | Home ProxyJump | yes | fresh | none |
| `home` | `10.99.0.1` | direct | no (self-auth) | fresh | 3 read-only records; no current truth/verifier gate |
| `kfrm` | `10.99.0.31` | Home ProxyJump | yes | fresh | none |
| `main` | `10.99.0.2` | none | no (timeout) | stale | none |
| `new` | `10.99.0.6` | Home ProxyJump | yes | fresh | 11 completed; see evidence boundary below |
| `paris` | `10.99.0.20` | Home ProxyJump | yes | fresh | none |
| `primary` | `10.99.0.10` | direct | yes | fresh | 1 read-only record; no current truth/verifier gate |
| `qjns` | `10.99.0.4` | direct | yes | fresh | none |
| `reserve242` | `10.99.0.21` | direct | yes | fresh | none |
| `uiap` | `10.99.0.3` | direct | yes | fresh | none |

Additional existing-path checks did not find a route to `main`: TCP/22 timed
out from `primary` and `qjns`, and the manifest-declared external endpoint also
timed out on TCP/22.

## Control Plane registration truth

Home is serving the canonical task API at `10.99.0.1:9101`; `/health` reports
node `home`, and `/v1/fabric/health` returns Redis `PONG`. The Home service is
active, enabled and listening.

The raw registry must not be presented as a 31-node fresh physical fleet:

- total logical registrations: `136`;
- canonical manifest IDs: `21` (`20` fresh, `main` stale);
- noncanonical registrations: `115` (`11` fresh, `104` stale);
- fresh duplicate IDs: `agent-01` through `agent-10`, plus `server-kfrm`;
- stale families: `mesh-agent-*` (`101`), `mesh-*` (`1`), `home-live` (`1`),
  and `primary-candidate` (`1`).

These are logical/legacy registrations, not additional physical servers.

## Execution evidence boundary

Home Control Plane currently indexes `126` tasks:

- `33` completed;
- `73` failed;
- `16` cancelled;
- `1` dead-lettered;
- `3` queued.

Completed task lease identities are distributed across only eight logical IDs:
`agent-01`, `agent09`, `home`, `home-live`, `mesh-9fts`, `new`, `primary`, and
`server-kfrm`. After requiring an exact manifest physical ID, only four
physical nodes have any completed record: `agent09`, `home`, `new`, and
`primary`.

On `new`, eight non-probe capability artifacts were checked on the worker
without reading their content:

- four `orchestrator_chat_response` artifacts;
- four `owner_remote_task` artifacts;
- all eight paths were contract-safe absolute paths;
- all eight files exist, are regular, non-empty and locally hashable.

This proves artifact availability on one physical server. It does **not** prove
fleet-wide capability acceptance. The task records contain no explicit passed
independent verifier and no stored content hash bound to the attempt. The
current Truth Factory summary (`3` claims, `9` evidence records, `3` true
verdicts) uses reference/count-based evidence; the deployed completion records
do not meet the frozen content-bound verifier contract. Therefore the strict
execution result remains `0/21` proven nodes.

## Evidence commands

- `scripts/check-fleet.sh --manifest-url <Home read endpoint> --home home --expect 21`
- read-only `GET /health`, `/v1/fabric/health`, `/v1/nodes?limit=250`,
  `/v1/tasks?limit=250`, `/v1/tasks/queue/diagnostics`, and
  `/v1/truth/summary`
- read-only service/listener/file-metadata checks on Home
- read-only SSH/TCP reachability probes with default host-key verification
- artifact metadata and SHA-256 availability checks; artifact contents were
  not emitted or stored

No raw secret, public key, provider output, prompt, token, endpoint credential,
private key path or environment file is present in this artifact.
