# Fleet and project census for the Kolibri master plan

- Snapshot window: `2026-07-10T20:50:58Z`–`2026-07-10T20:58:19Z`.
- Authority queried: canonical Home Control Plane at the endpoint resolved for
  `home`, plus the Home mesh membership read API.
- Supporting evidence: `release/evidence/fleet-truth-audit-20260710T202608Z.md`,
  current local Git metadata, repository contracts, and existing release/run
  artifacts.
- Method: read-only HTTP and local file/Git metadata inspection. No SSH, task
  submission, service mutation, deploy, manifest mutation, secret file read,
  fetch, checkout, or production write was performed.

## Executive result

The current system proves a real 21-entry physical membership projection and a
live Home Control Plane, but it does **not** yet provide a complete project
inventory or a proven 21-node execution fabric.

Three facts must remain separate:

| Layer | Current evidence | Verdict |
| --- | --- | --- |
| Membership | 21 peers, 21 unique durable node IDs, 21 unique mesh IPs | proven for the current projection |
| Agent freshness | 20 canonical nodes fresh; `main` stale | partial, `20/21` |
| Strict capability execution | no completed task contains both content-bound hash evidence and an explicit independent verifier verdict | not proven, `0/21` |

The Control Plane sees enough telemetry to schedule generic work, but it does
not know which repositories, releases, model files, datasets, databases, or
project knowledge stores exist on each server. Hostnames imply useful intended
roles, but those roles are mostly not represented as enforceable scheduler
capabilities. Therefore a claim such as “all projects and all server files have
been studied” would be false from the currently exposed evidence.

## Evidence vocabulary

- **Proven** means directly observed in the live read API or current local Git
  metadata during the snapshot window.
- **Inferred** means suggested by a hostname, historical document, source-code
  default, or task path, but not verified by a current runtime attestation.
- **Missing** means the current API cannot answer the question or the protected
  data surface was unavailable to this least-privilege read-only scan.

## Fleet truth, without blended counters

| Fact | Evidence | Status |
| --- | --- | --- |
| Canonical Control Plane | `/health` reports node `home`; `/v1/fabric/health` reports Redis `PONG` | proven |
| Physical membership projection | Home mesh read API returns 21 unique node IDs and IPs | proven |
| Hardened distributed registrar contract | deployed projection is still schema-v1; the prior audit did not find v2 records or deployed signature verification | missing / contract gap |
| Raw Control Plane registry | 136 registrations: 21 canonical plus 115 legacy/logical duplicates | proven, hygiene failure |
| Canonical heartbeat freshness | 20 fresh, `main` stale by about 26 hours | proven |
| Mac bootstrap route | prior read-only audit: 20/21 through existing direct paths plus existing Home ProxyJump; `main` unavailable | partial |
| Home SSH route | prior read-only audit: 19/21; `main` timeout and Home-to-self root SSH rejection | partial |
| Scheduling drain state | 0 canonical nodes draining | proven |
| Reported fleet resources | 44 logical CPUs, 112.4 GiB RAM, 824.7 GiB disk including stale `main` telemetry | proven as heartbeat self-report only |
| Fresh-node resources | approximately 43 logical CPUs, 110.5 GiB RAM, 806.0 GiB disk after excluding stale `main` | derived from proven telemetry |
| Active task telemetry | node cards initially showed no active task; by `20:58:19Z` one task was running and three remained queued | proven, dynamic |

The raw registry count is not a physical-server count. Legacy identities such
as `agent-01`, `mesh-*`, `home-live`, and `server-kfrm` must be reconciled to
canonical manifest IDs before task history can be used for per-server truth.

## Canonical 21-node census

Resource values are heartbeat self-reports. `RAM` and `disk` show
`total / free-or-available GiB`. Role signals marked with `†` come from the
hostname and are **not** currently enforced capabilities.

Capability abbreviations:

- `G` — `generic_implementation`;
- `I` — `implementation`;
- `R` — `review`;
- `RO` — `read_only_probe`;
- `C/M` — `runner:codex` / `runner:mimo`;
- `O/P` — legacy `orchestrator` / wildcard permission metadata.

Every fresh node reports Codex and Mimo available. Every canonical node reports
the generic API runner and local LLM unavailable. This is presence/probe
metadata, not a completed-task proof.

| Node | Mesh IP | Host / role signal | Freshness | CPU | RAM | Disk | CP capabilities | Runner report | Rollout stage |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| `9fts` | `10.99.0.5` | inference recovery† | fresh | 1 | 1.9 / 0.7 | 18.7 / 7.6 | I, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent01` | `10.99.0.8` | backend lead† | fresh | 1 | 1.9 / 1.4 | 18.7 / 12.8 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent02` | `10.99.0.9` | frontend design† | fresh | 1 | 1.9 / 1.4 | 18.7 / 12.2 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent03` | `10.99.0.11` | infrastructure/network† | fresh | 1 | 1.9 / 1.4 | 18.7 / 13.2 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent04` | `10.99.0.12` | QA/browser† | fresh | 1 | 1.9 / 1.4 | 18.7 / 13.1 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent05` | `10.99.0.13` | security/audit† | fresh | 1 | 1.9 / 1.4 | 18.7 / 13.4 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent06` | `10.99.0.14` | docs/knowledge† | fresh | 2 | 3.8 / 3.2 | 37.5 / 30.9 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent07` | `10.99.0.15` | FormulaLM eval† | fresh | 1 | 1.9 / 1.4 | 18.7 / 13.3 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent08` | `10.99.0.16` | RAG eval† | fresh | 1 | 1.9 / 1.5 | 18.7 / 13.1 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `agent09` | `10.99.0.17` | release canary† | fresh | 1 | 1.9 / 1.4 | 18.7 / 13.3 | G, RO, C/M | C/M available; API/LLM unavailable | canary |
| `agent10` | `10.99.0.18` | HK edge/load† | fresh | 2 | 7.8 / 7.3 | 46.9 / 10.8 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `highload` | `10.99.0.19` | CI/build high-load† | fresh | 1 | 3.8 / 3.2 | 28.1 / 19.4 | G, RO, C/M | C/M available; API/LLM unavailable | quorum |
| `home` | `10.99.0.1` | canonical Control Plane | fresh | 6 | 15.5 / 7.8 | 97.9 / 12.9 | G, RO, C/M | C/M available; API/LLM unavailable | quorum |
| `kfrm` | `10.99.0.31` | large quorum worker | fresh | 8 | 31.3 / 30.5 | 150.4 / 125.2 | G, RO, C/M | C/M available; API/LLM unavailable | quorum |
| `main` | `10.99.0.2` | legacy API/orchestrator metadata | stale | 1 | 1.9 / 1.5 | 18.7 / 3.1 | O/P, G, I, R, RO, C/M | stale C/M metadata; API/LLM unavailable | missing |
| `new` | `10.99.0.6` | review worker | fresh | 2 | 7.8 / 6.2 | 75.2 / 47.9 | R, RO, C/M | C/M available; API/LLM unavailable | standard |
| `paris` | `10.99.0.20` | build reserve† | fresh | 1 | 3.8 / 3.2 | 28.1 / 22.4 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `primary` | `10.99.0.10` | general last-wave worker | fresh | 8 | 11.7 / 8.2 | 98.3 / 29.1 | G, RO, C/M | C/M available; API/LLM unavailable | last |
| `qjns` | `10.99.0.4` | tools executor† | fresh | 1 | 1.9 / 0.8 | 18.7 / 9.3 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `reserve242` | `10.99.0.21` | reserve worker | fresh | 1 | 1.9 / 1.4 | 18.7 / 13.1 | G, RO, C/M | C/M available; API/LLM unavailable | standard |
| `uiap` | `10.99.0.3` | RAG/knowledge† | fresh | 2 | 3.8 / 2.3 | 37.5 / 23.9 | G, RO, C/M | C/M available; API/LLM unavailable | standard |

### What the role table actually means

The names `backend-lead`, `frontend-design`, `qa-browser`, `formulalm-eval`,
and similar strings are operational intent encoded in hostnames. The scheduler
currently sees almost all of those nodes as the same `generic_implementation`
class. There are no current resource-class capabilities such as `browser`,
`build`, `security_scan`, `rag_index`, `formulalm_eval`, `document_render`, or
`apple_build` on the corresponding cards. The intended specialization is thus
inferred, not enforceable.

## Providers, models, tools, and runners

### Proven runtime metadata

- `runner:codex` and `runner:mimo` are declared on all 21 canonical cards.
- Codex self-probe status is `available` on all 21 cards.
- Mimo self-probe status is `available` on all 21 cards. Twenty fresh cards
  carry the structured Mimo Auto 2.5 no-user-auth/worktree-scoped contract;
  stale `main` has only legacy availability metadata.
- `api` and `local_llm` runner probes are `unavailable` on all 21 cards.
- Home Control Plane `/v1/models` exposes internal `mimo-auto` metadata.
- The unified public backend `/v1/models` correctly exposes only the public
  model identity `kolibri`.
- Production `/v1/capabilities` reports 63 catalog records: 7 plugins and 47
  skills marked available, plus 9 tools marked degraded. The three discovery
  probes only prove manifest readability/discovery, not successful tool calls.

### Important interpretation

An installed binary or successful lightweight runner probe does not prove that
the provider can execute a real task with current authorization, rate limits,
artifact output, and verifier evidence. The strict execution denominator
therefore remains `0/21`, not `21/21`.

### Missing model/provider facts

The current APIs do not expose:

- model files, formats, hashes, licenses, quantization, memory requirements, or
  load-test results per node;
- provider quotas, current risk-control state, latency/error windows, or
  entitlement-safe model availability;
- a local model server health record on any node;
- FormulaLM trained candidates or production model weights as live runtime
  inventory.

## Tasks and artifacts

The Control Plane was active during the scan, so task counters changed. The
latest bounded snapshot at `2026-07-10T20:58:19Z` contained:

| State | Count |
| --- | ---: |
| completed | 38 |
| failed | 73 |
| cancelled | 16 |
| queued | 3 |
| running | 1 |
| dead-letter | 1 |
| total | 132 |

Additional facts:

- 115 task records had a `result_reference` and a node-local `result_path`.
- 65 task results carried worktree-path metadata.
- All 38 completed records had an `attempt_id`.
- Zero completed records had a stored content hash.
- Zero completed records had an explicit independent verifier verdict.
- Only four exact canonical physical IDs had any completed record:
  `agent09`, `home`, `new`, and `primary`.
- Historical completions assigned to `server-kfrm`, `mesh-9fts`, `agent-01`,
  and `home-live` cannot be counted automatically against canonical `kfrm`,
  `9fts`, `agent01`, and `home` without an explicit identity-lineage record.

The prior fleet audit additionally verified that eight result files on `new`
were regular, non-empty, and locally hashable without reading their content.
That proves artifact availability on one node, but it still does not satisfy
the frozen content-bound verifier contract.

## Repository, release, model, and data-service census

| Asset class | Proven now | Inferred or historical | Missing evidence |
| --- | --- | --- | --- |
| Repositories on servers | Task records contain 65 worktree-path references | Agent Host convention creates node-local clean worktrees | no repository registry, origin identity, commit, dirty state, size, or branch matrix per node |
| GitHub source | local origin is `rd8r8bkd9m-tech/kolibri-ai-platform`; current local metadata has 75 local branches, 303 remote-tracking refs, 40 worktrees, 2 tags | remote-tracking refs represent a large historical development surface | no fetch was performed; current live GitHub branch/PR/CI truth is not proven by this census |
| Releases | 20 canonical cards have rollout-stage labels | source contains a signed immutable release controller/installer contract | installer status is unavailable on 20 cards and missing on stale `main`; no fleet release list or installed release digest is exposed |
| Public model | `kolibri` | provider provenance is internal by design | no public issue |
| Internal model route | Home model catalog contains `mimo-auto`; Mimo Auto 2.5 contract appears on 20 fresh cards | Mimo is intended as first external teacher/worker | real per-node capability acceptance and quota/risk-control windows are missing |
| Local LLM | all 21 cards report unavailable | historical source contains Qwen/LoRA work | no live model runtime, model artifact, or inference benchmark inventory |
| Redis | Home Fabric health returns `PONG`; task/node state is live | Redis is the compatibility queue during migration | backup, persistence, replication, and retention status are not exposed |
| Backend compatibility DB | source resolves production data to `/opt/kolibri-ai/data/kolibri.db` | SQLite is intended to hold conversations, projects, workstreams, artifacts, and FormulaLM compatibility tables | record counts and live DB health were inaccessible |
| PostgreSQL HA | target architecture names it authoritative | contract only | no deployed service or replication evidence |
| NATS JetStream | target architecture names it authoritative for events/mailboxes | contract only | no deployed service, stream, quorum, or retention evidence |
| S3/CAS | target architecture names it authoritative for immutable artifacts | contract only | no bucket, hash index, retention, or object-health evidence |
| RAG/knowledge | `uiap` hostname signals RAG/knowledge intent | historical docs mention ChromaDB/embeddings | no current service health, corpus, vector index, dataset lineage, or freshness API |
| FormulaLM | a durable candidate-only SQLite boundary and tests exist in source | target includes async training/eval/canary | production `/v1/learning/status` is unavailable, so live queue/candidate state is not proven |

### API evidence gaps and false-positive HTTP 200s

The canonical Home Control Plane returns `404` for collection inventory routes
such as `/v1/projects`, `/v1/releases`, `/v1/artifacts`, `/v1/providers`,
`/v1/runtime/summary`, `/v1/tools`, and `/v1/capabilities`. Those domains live
in the unified compatibility backend, not the Control Plane.

On the production unified backend, the protected execution routes
`/v1/projects`, `/v1/artifacts`, `/v1/tools`, `/v1/runtime/swarm`,
`/v1/learning/status`, `/v1/canvases`, `/v1/responses`, `/api/providers`, and
`/api/conversations` all returned:

```text
503 execution_api_auth_not_configured
```

This is fail-closed behavior, but it also means the durable project, artifact,
runtime, and FormulaLM stores cannot currently be inventoried through the
production API. No credential was read or synthesized for this scan.

Several nonexistent API collections, including `/v1/releases`,
`/v1/providers`, `/v1/runtime/summary`, `/api/releases`, and `/api/projects`,
returned `200 text/html` because the SPA fallback served `index.html`. They are
not working JSON APIs and must not be counted as implemented inventory routes.

The public `/api/factory/status` also exposed a pagination defect during the
scan: it reported only 50 node records and the first 100 tasks, while the
authoritative Home endpoints held 136 registrations and 132 tasks. Source
inspection confirms the backend calls `/v1/nodes` and `/v1/tasks` without
following pagination. `/control` must not use this partial aggregate as fleet
truth.

## Where project knowledge actually resides

The current knowledge plane is fragmented across six places:

1. **Git/GitHub source history.** The only structured source-of-code identity
   observed is `kolibri-ai-platform`. The current local clone contains 633
   tracked files, of which 484 are under `docs/`. It has 75 local branches, 303
   remote-tracking refs, and 40 linked worktrees. This is the largest durable
   engineering knowledge source, but remote freshness was not checked here.
2. **The active dirty implementation worktree.** The current implementation is
   on `codex/kolibri-os-implementation-20260710` at
   `91a9b000379c1ce89d5d5403e78c4a4a15c76f51`, with substantial uncommitted
   backend, frontend, mesh, release, FormulaLM, and test work. Until reviewed,
   committed, and published, this knowledge exists only in local worktrees.
3. **Historical handoff and run documentation.** The repository currently has
   41 dated `docs/agent/runs` directories and four
   `docs/agent/intelligence` directories. They contain useful decisions and
   incident evidence, but several describe pre-Home or duplicate-node states
   and must be treated as historical, not live truth.
4. **Home Redis Control Plane state.** It owns current node cards, tasks,
   leases, queues, and truth records. It is operational state, not a complete
   project/document repository. It currently contains duplicate logical
   identities and artifact references without content hashes.
5. **Node-local worktrees and artifact roots.** Task metadata proves that these
   paths exist as a convention, and the prior audit proved some files on
   `new`. Their contents, repository identity, sizes, lineage, and retention
   are not centrally indexed.
6. **The unified backend SQLite compatibility store.** Source contracts place
   conversations, projects, workstreams, backlog, checkpoints, canvases,
   artifacts, runtime records, and FormulaLM compatibility state in the
   production data directory. The production execution principal is not
   configured, so live record counts and continuity could not be read.

The related Rust foundation is a separate worktree on
`p0/free-low-cost-model-provider-registry-20260704`; the owner-facing active
workspace and the canonical implementation worktree are also separate. This
branch/worktree topology is useful, but it is not a substitute for a durable
Project/Workstream/Checkpoint service.

## Exact evidence gaps blocking a complete “all projects/all servers” analysis

1. No API enumerates repositories or their branch/commit/dirty/worktree state
   per canonical node.
2. No API enumerates installed immutable releases and signed manifest digests
   per node.
3. No API enumerates service units, containers, listening service identities,
   or their package/release provenance.
4. No API enumerates model files, adapters, licenses, hashes, loadability, or
   benchmark evidence.
5. No API enumerates RAG corpora, datasets, vector indexes, training datasets,
   or data lineage.
6. No API exposes PostgreSQL/NATS/S3 deployment status because those target
   services are not proven deployed.
7. The protected Project/Artifact/Runtime/FormulaLM API cannot currently be
   read because production execution authentication is not configured.
8. Task artifacts are path references rather than a central content-addressed
   catalog with hashes and verifier bindings.
9. Duplicate Control Plane identities prevent automatic attribution of some
   historical task evidence to the 21 physical nodes.
10. The current manifest proves 21 entries but not the hardened signed,
    replicated all-registrar v2 membership contract.

## Proposed safe inventory contract

The missing coverage should be solved once, through the Home API, rather than
with repeated ad-hoc SSH scans.

### Endpoints

```text
POST /v1/inventory/refresh
GET  /v1/inventory/snapshots/latest
GET  /v1/inventory/snapshots/{snapshot_id}
GET  /v1/inventory/nodes/{node_id}
GET  /v1/inventory/repositories
GET  /v1/inventory/releases
GET  /v1/inventory/models
GET  /v1/inventory/data-services
GET  /v1/inventory/artifacts/summary
```

`POST /refresh` is owner-gated and creates only read-only, fenced inventory
tasks through the Factory API. Workers never receive SSH. Every canonical node
returns a signed attestation bound to `node_id`, `attempt_id`, manifest digest,
runtime release digest, and capture time. GET routes require a least-privilege
`inventory:read` principal and return redacted aggregates.

### Per-node record

```json
{
  "schema_version": "kolibri.inventory-node.v1",
  "snapshot_id": "inventory_...",
  "node_id": "opaque-canonical-id",
  "captured_at": "...",
  "freshness": "fresh|stale|missing",
  "evidence_status": "proven|inferred|missing",
  "manifest_digest": "sha256:...",
  "runtime_release": {
    "release_id": "...",
    "manifest_digest": "sha256:...",
    "signature_verified": true,
    "active": true,
    "rollback_release_id": "..."
  },
  "resources": {},
  "capabilities": [],
  "runner_probes": [],
  "repositories": [],
  "models": [],
  "data_services": [],
  "artifact_summary": {},
  "attestation": {
    "attempt_id": "...",
    "payload_sha256": "sha256:...",
    "verifier_verdict": "passed|failed"
  }
}
```

### Repository inventory fields

- stable `repository_id`, sanitized origin identity, default branch, current
  commit SHA, dirty boolean, worktree count, last commit time, approximate
  size, and declared project/workstream binding;
- never return credential-bearing remote URLs, file contents, diffs, untracked
  filenames, or secret-like environment data in the aggregate API;
- include `scan_status`, `captured_at`, and evidence digest so an inaccessible
  repository is reported as missing rather than silently omitted.

### Release, model, and data-service fields

- releases: signed manifest digest, source commit, installed/active/previous
  state, unit/binary checksums, health verdict, and rollback evidence;
- models: stable model ID, family, format, quantization, byte size, content hash,
  license/data class, load-probe status, and resource requirements; never emit
  raw prompts, weights, or provider credentials;
- data services: type, logical service ID, local/mesh exposure class, health,
  schema/version, dataset or volume size, replication/backup freshness, and
  last successful integrity check; never emit DSNs or credentials;
- artifacts: counts/bytes by kind and state, content-hash coverage, verifier
  coverage, oldest/newest timestamps, retention class, and CAS health.

### Truth and privacy rules

1. Every field is tagged `proven`, `inferred`, or `missing`; absence never
   becomes “healthy”.
2. Binary presence is distinct from authenticated capability execution.
3. Inventory payloads use an allowlist. Environment values, task prompts,
   provider output, source contents, cookies, tokens, private keys, and raw logs
   are forbidden.
4. Snapshots are immutable, content-hashed, signed, and retained as release
   evidence. An ETag/digest lets `/control` render one consistent point in time.
5. Duplicate logical IDs are mapped through explicit identity lineage; string
   similarity never attributes evidence to a physical server.
6. `/control` shows the snapshot age and per-section evidence status. It does
   not blend membership, freshness, and capability execution into one number.

## Master-plan implications and priority order

1. Configure the production execution API principal through the owner-gated
   secret mechanism so Projects, Workstreams, Artifacts, Runtime, and FormulaLM
   can be read and used; do not expose them publicly.
2. Fix factory-status pagination before treating `/control` as operational
   truth.
3. Add the inventory contract above to Agent Host and Home, then take one
   signed snapshot across all 21 canonical IDs.
4. Reconcile or retire 115 noncanonical registrations with explicit identity
   lineage and retention; never delete historical evidence blindly.
5. Restore or deliberately re-enroll `main`; until then report freshness as
   `20/21` and bootstrap reachability separately.
6. Deploy and verify the signed release installer contract; current status is
   `0/21` available.
7. Convert hostname intentions into typed, probed capabilities and physical
   resource pools.
8. Run one capability-appropriate task on every node with fenced attempt,
   content hash, immutable artifact, and independent verifier verdict.
9. Centralize task artifacts in CAS and bind historical worktree outputs to
   Project/Workstream/Checkpoint records.
10. Only after this evidence exists should the system schedule broad
    repository analysis, RAG indexing, FormulaLM learning intake, or a signed
    progressive release across the whole fleet.

## Evidence sources used

- Home read endpoints: `/health`, `/v1/fabric/health`, `/v1/nodes?limit=250`,
  `/v1/fleet/capabilities`, `/v1/models`, `/v1/tasks?limit=250`,
  `/v1/tasks/queue/diagnostics`, and `/v1/truth/summary`.
- Home mesh membership read endpoint, selecting only safe node ID/IP facts.
- Production read endpoints: `/api/health`, `/v1/models`,
  `/v1/capabilities`, and `/api/factory/status`; protected endpoint responses
  were inspected only for normalized status/detail.
- `release/evidence/fleet-truth-audit-20260710T202608Z.md` for the existing
  Mac/Home reachability and strict execution boundary.
- Current local Git metadata and source contracts in `backend/`, `ops/`,
  `contracts/`, `docs/`, and `release/`.

No raw secret, private key, token, credential, environment file, task prompt,
provider output, or artifact content is present in this census.
