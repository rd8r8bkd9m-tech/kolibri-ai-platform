# Control Plane queue unblock report

Role: `control_plane_queue_unblocker`
Date: 2026-06-29
Scope: read-only live diagnostics plus local report / envelope proposal. No tasks
were cancelled, requeued, leased, submitted, or otherwise mutated.

## Live snapshot

Control Plane: `http://10.99.0.2:9101`

- `/health` at `2026-06-29T04:28:59Z`: `status=ok`,
  `queue_backend=redis`, `redis=PONG`, `spool_count=0`.
- Full `GET /v1/tasks?summary=1&compact=1` returned a very large body
  (`~14.4 MB`) with keys `queue`, `spool_count`, `tasks`. The live endpoint
  does not behave like a compact summary: `summary=1` is effectively ignored.
- Full scan observed `tasks=652`, `failed=138`, `completed=399`,
  `cancelled=19`, `queued=61`, `dead_letter=11`, `waiting_review=23`,
  `running=1`.
- The queue is moving / non-atomic during the large scan. A later full read
  around `04:30Z` returned `queue_len=67`. Treat the exact queue length as
  snapshot-specific; the 61 vs 67 difference is not the root blocker.
- `limit` truncates the returned `queue` array. Example:
  `/v1/tasks?summary=1&compact=1&limit=1` returned `queue_len=1`.
  This explains a compact scan showing `queue_count=1`; it is a limited view,
  not the real Redis queue length.
- `state=queued`, `state=running`, and `state=waiting_review` returned empty
  `tasks` arrays in live testing, while still returning queue prefixes. Do not
  use those filters as authoritative state counts until the API is fixed.

## First queued ids

First queue ids from the full scan:

| Task id | State | Routing / blocker |
| --- | --- | --- |
| `KOL-NETWORK-CONVERGENCE-001-NODE-KOLIBRI_217_60_252_10-PROBE-001` | queued | targets `kolibri-217-60-252-10`; node expected quarantined / host key changed. |
| `KOL-NETWORK-CONVERGENCE-001-NODE-217_60_62_39-PROBE-001` | queued | targets `217-60-62-39`; node expected offline / unreachable. |
| `KOL-NETWORK-CONVERGENCE-001-NODE-217_60_249_157-PROBE-001` | queued | targets `217-60-249-157`; node expected degraded / timeout. |
| `KOL-AGENT-HOST-KIND-COMPAT-001` | queued | requires `remote_implementation_runner_ready`; no fresh node advertises it. |
| `KOL-AGENT-HOST-LEASE-HEARTBEAT-001` | queued | requires `remote_implementation_runner_ready`; no fresh node advertises it. |
| `KOL-CONTROL-PLANE-PERSISTENT-AGENTS-001` | queued | product implementation blocked on `remote_implementation_runner_ready`. |
| `KOL-PRIMARY-AGENT-ROSTER-200-001` | queued | blocked on `remote_implementation_runner_ready`. |
| `KOL-PRIMARY-MIMO-KIMI-200-RAMP-001` | queued | blocked on `remote_implementation_runner_ready`. |
| `KOL-DOCS-APP-UNIFIED-FORMAT-001` | queued | app/product task blocked on `remote_implementation_runner_ready`. |
| `KOL-WEB-PORTAL-IMPLEMENTATION-001` | queued | app/product task targets `primary-candidate` and requires `remote_implementation_runner_ready`. |

Queued routing distribution from the full scan:

- `deep_research_runner_ready`: 24 queued tasks.
- `remote_implementation_runner_ready`: 13 queued tasks.
- `snapshot-only`: 10 queued tasks.
- `generic_implementation`: 9 queued tasks.
- `read_only_probe`: 4 queued tasks.
- `owner_local_device_support`: 1 queued task.

## Owner app task

The current owner task for "mini up" is not waiting in queue:

- `TG-20260629003017-4711-up-telegram`
- `state=running`
- `lease_owner=9fts:agent-host-9fts`
- task heartbeat: `2026-06-29T00:30:54Z`
- lease expired: `2026-06-29T00:31:54Z`
- node `9fts` heartbeat: `2026-06-29T00:30:24Z`

At the `04:28:59Z` health snapshot, both the task heartbeat and the node
heartbeat were stale by several hours. This is why the task appears "accepted"
or "running" but is not actually making progress. It is not blocked behind the
61 queued tasks; it is stuck under a stale running lease.

The follow-up owner-facing chat task about the main domain:

- `TGCHAT-20260629003136-4713-kolibri`
- `state=failed`
- target node: `primary-candidate`
- error: `mimo completed without text response`

That explains the owner-visible "executor fell" style message: the chat response
runner failed independently while the implementation task stayed stale-running.

## Fresh nodes

Freshness computed against `/health` time `2026-06-29T04:28:59Z` using a
120-second heartbeat window:

| Node | Fresh | Draining | Relevant capabilities | Active task |
| --- | --- | --- | --- | --- |
| `main` | yes | no | `orchestrator`, `implementation`, `review`, `read_only_probe` | none |
| `new` | yes | no | `review`, `read_only_probe`, `generic_review` | none |
| `home` | yes | no | `coordinator`, `home`, `mesh`, `redis`, `control-standby`, `orchestrator`, `read_only_probe`, `network_convergence` | none |
| `home-live` | yes | yes | `home`, `orchestrator`, `telegram`, `generic_implementation`, `read_only_probe` | none |
| `qjns` | yes | yes | `read_only_probe`, `implementation`, `review`, `qa`, `agent-host` | none |
| `uiap` | yes | yes | `read_only_probe`, `research`, `security`, `rag`, `knowledge-base` | none |

Important stale active nodes:

- `primary-candidate`: heartbeat `2026-06-29T03:03:14Z`, active
  `KOL-META-MIMO-ORCHESTRATOR-PRIMARY-20260629`.
- `9fts`: heartbeat `2026-06-29T00:30:24Z`, active
  `TG-20260629003017-4711-up-telegram`.

The only fresh, non-draining implementation-capable node observed is `main`.
The fresh reviewer is `new`.

## Root cause

1. The owner app task is stale-running on `9fts`, not queued. Its lease expired
   at `00:31:54Z`, but it remains in `running` with an old heartbeat.
2. The large backlog is mostly composed of tasks that require unavailable
   capabilities, especially `remote_implementation_runner_ready` and
   `deep_research_runner_ready`.
3. Several app/product queue entries target stale or unavailable routing:
   `primary-candidate` is stale-active and `remote_implementation_runner_ready`
   is not advertised by fresh nodes.
4. Compact scans are misleading:
   - `limit=1` makes the returned queue look like one item;
   - full unbounded scan shows the older 61+ backlog but is expensive;
   - live `state=` filters are not reliable for task counts.

## P0 envelope needed

The app needs a new P0 implementation envelope that routes to the fresh
implementation node instead of waiting for `remote_implementation_runner_ready`.
Proposal file:

`ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-20260629.json`

Key routing:

- `kind`: `generic_implementation`
- `required_capability`: `implementation`
- `target_node`: `main`
- `runner`: `codex`
- review: `new`

The goal is not to cancel or mutate the stale `9fts` task. It should perform a
fresh P0 app/domain/Telegram Mini App diagnosis and repair on `main`, produce
evidence, and create a review path on `new`. If `codex` is unavailable on
`main`, the task must fail with a blocker artifact instead of faking progress.

## Recommendations

1. Do not trust `limit=1` compact scans for queue health. For owner status,
   expose `queue_total`, `queued_state_total`, `running_stale_total`, and
   `fresh_executor_count` separately.
2. Add or deploy a Control Plane lease sweeper so expired `running` leases are
   surfaced as `stale_running` and can be requeued only through an explicit,
   logged operator action.
3. Submit the proposed P0 app envelope only after the operator accepts that it
   supersedes the stale `9fts` owner task for app recovery. Do not cancel the
   old task without a separate decision.
4. Stop routing new app/product work to `remote_implementation_runner_ready`
   until a fresh node advertises that capability, or retarget P0 app tasks to
   `main` with `required_capability=implementation`.
5. Keep `new` for independent review; it is fresh and non-draining but does not
   advertise implementation capability.
