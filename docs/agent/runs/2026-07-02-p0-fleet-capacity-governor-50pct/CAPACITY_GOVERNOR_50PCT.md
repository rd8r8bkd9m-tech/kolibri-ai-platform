# Temporary Fleet Capacity Governor: 50 Percent For 2 Hours

Task: `P0_FLEET_CAPACITY_GOVERNOR_50PCT_2026_07_02`
Generated: `2026-07-02T02:44:33Z`
Lease owner: `mesh-agent-02:autonomous_engineer`
Execution host: `kolibri`
Scope: docs-only policy artifact. No live drain, restart, cancel, push, or
destructive action was executed by this task.

## Activation Window

This governor is a temporary safety cap for a two-hour operating window.

- Start: when an owner or Control Plane operator explicitly activates the policy.
- End: 2 hours after activation, or earlier if the owner clears it.
- Default after expiry: return to the normal scheduler only after read-only
  health checks confirm no active overload stop condition remains.
- Source of truth while active: fresh Control Plane node cards plus exact task
  status/artifact endpoints. Stale cards never count as live capacity.

## Capacity Rule

Use the lower of:

- 50 percent of the node's verified normal worker budget, rounded down but at
  least 1 for a fresh runner node;
- the fixed temporary budget in the table below.

Do not infer extra capacity from stale metadata cards or mesh shadow cards.

## Per-Node Worker Budgets

| Node | Temporary worker budget | Safe lanes while capped | Notes |
|---|---:|---|---|
| `mesh-agent-01` | 10 | implementation, review, focused tests, read-only diagnostics | Fresh runner node from fleet inventory; keep one worker free for repair/monitoring. |
| `mesh-agent-02` | 10 | implementation, review, focused tests, read-only diagnostics | Current task host; avoid self-saturating with broad fanout. |
| `mesh-agent-03` | 10 | implementation, review, focused tests, read-only diagnostics | Fresh runner node; prefer for bounded code/test work. |
| `mesh-9fts` | 10 | implementation, inference-recovery work, focused tests, read-only diagnostics | Fresh runner node; do not use for owner-facing deploys unless separately validated. |
| `main` | 1 | orchestration, API/control checks, tiny docs or test probes | Low-memory command/control node; no heavy model, compile, or broad test fanout. |
| `new` | 1 | review, QA read-only checks | Online but not general runner-ready in the inventory. |
| `qjns` | 1 | credential smoke probes, read-only diagnostics | GitHub/MIMO credentials unverified; no implementation or push work. |
| `uiap` | 1 | RAG/knowledge checks, read-only diagnostics | Preserve RAG service capacity; no general implementation. |
| `home` | 0 | read-only inventory only | Stale/non-fresh at last inventory; do not lease new work. |
| `home-live` | 0 | read-only inventory only | Stale/non-fresh at last inventory; do not lease new Telegram/owner work. |
| `primary-candidate` | 0 | read-only endpoint checks only until fresh | Freshness ambiguity; require current heartbeat before any lease. |
| `mesh-agent-04..09` | 0 | read-only inventory only | Stale mesh shadow cards; not live capacity. |
| Metadata-only cards such as `agent-01..09`, `9fts`, `highload`, `paris`, `reserve242`, `server-kfrm`, `smoke-primary` | 0 | read-only inventory only | Metadata debt only; never count toward the active 50 percent cap. |

Fleet-wide temporary ceiling for fresh general runner lanes: 40 workers across
`mesh-agent-01`, `mesh-agent-02`, `mesh-agent-03`, and `mesh-9fts`. The command,
review, RAG, and credential-probe nodes above are additional specialized
single-worker lanes and must not be converted into general capacity.

## Throttle And Drain Policy

While the governor is active:

1. Admit new work only to the safe lanes listed for the target node.
2. Prefer queue throttling before drain. Keep already-running leases alive if
   they are heartbeating, producing artifacts, and not crossing stop conditions.
3. Set a node to drain only when it crosses an overload stop condition or needs
   protected recovery. Drain means no new leases; it does not cancel active work.
4. For long-running non-P0 work, let the current lease finish if it is healthy.
   Do not start the next lease until the active worker count is under budget.
5. If a node is stale, non-fresh, or metadata-only, treat it as already drained
   for scheduling purposes.
6. Do not cancel, kill, restart, rotate credentials, alter firewall/VPN, or
   change production services under this governor without a separate scoped task
   and rollback notes.

Guarded drain command shape, for operators only:

```bash
curl -fsS -X POST "$CONTROL_PLANE_URL/v1/nodes/<node_id>/drain" \
  -H "Authorization: Bearer <redacted>" \
  -H "Content-Type: application/json" \
  --data '{"drain":true,"reason":"temporary_50pct_capacity_governor"}'
```

The command above is documentation only. This task did not run it.

## Safe Workload Lanes

| Lane | Allowed during governor | Preferred targets | Blocked targets |
|---|---|---|---|
| `P0_control_plane_repair` | yes, bounded | `mesh-agent-01..03`, `mesh-9fts`; `main` for tiny checks | stale cards, `home`, `home-live` until fresh |
| `implementation` | yes, capped | `mesh-agent-01..03`, `mesh-9fts` | `main` for heavy work, `qjns`, `uiap`, stale cards |
| `review` | yes, capped | `new`, `main`, `mesh-agent-01..03` | stale cards |
| `QA_read_only` | yes, capped | `new`, `main`, `mesh-agent-01..03`, `mesh-9fts` | production mutation targets |
| `RAG_knowledge` | yes, specialized | `uiap` | general runners unless explicitly RAG-related |
| `credential_probe` | yes, one at a time | `qjns`, `main` | any node without a credential repair task |
| `deploy_or_restart` | no by default | none without explicit owner task | all nodes |
| `broad_test_fanout` | no | none | all nodes |
| `heavy_model_or_local_LLM` | no by default | only after owner clears cap | `main`, `qjns`, `uiap`, stale cards |

## Overload Stop Conditions

Immediately stop admitting new work to a node, mark it drained for scheduling,
and create a repair/triage task if any condition is true:

- heartbeat is stale, missing, or `fresh=false`;
- active leases exceed the temporary worker budget;
- queue age for P0 tasks increases for 15 minutes while lower-priority work is
  admitted;
- task artifacts are missing after a terminal status;
- task lease heartbeat is stale or a lease is stuck beyond its envelope timeout;
- available memory is below 20 percent or swap pressure is observed;
- disk free is below 15 percent or artifact writes fail;
- CPU load stays above 80 percent for 10 minutes on a runner node, or above
  60 percent for 5 minutes on `main`;
- Control Plane `/health` is unhealthy or task endpoints disagree;
- provider/API rate-limit, auth, or quota failures repeat across two tasks;
- any command or log path risks printing secrets.

Recovery requires read-only evidence that the stop condition cleared. Do not
mark the node healthy from intent alone.

## Monitoring Commands

Read-only commands for the server Agent Host environment:

```bash
hostname
date -u +%Y-%m-%dT%H:%M:%SZ
git status --short
test -f docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/CAPACITY_GOVERNOR_50PCT.md
test -f docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/RESULT.md
```

Read-only Control Plane checks, with secrets redacted by the operator shell:

```bash
curl -fsS "$CONTROL_PLANE_URL/health" -H "Authorization: Bearer <redacted>"
curl -fsS "$CONTROL_PLANE_URL/v1/fleet/nodes" -H "Authorization: Bearer <redacted>"
curl -fsS "$CONTROL_PLANE_URL/v1/fleet/topology" -H "Authorization: Bearer <redacted>"
curl -fsS "$CONTROL_PLANE_URL/v1/fleet/capabilities" -H "Authorization: Bearer <redacted>"
curl -fsS "$CONTROL_PLANE_URL/v1/tasks" -H "Authorization: Bearer <redacted>"
```

Local OS checks for an operator already on the server:

```bash
uptime
df -h
free -h
ps -eo pid,ppid,stat,pcpu,pmem,comm --sort=-pcpu | head -20
```

Do not print environment variables, tokens, cookies, private keys, or raw
authorization headers while monitoring.

## Required Result Record

```json
{
  "task_id": "P0_FLEET_CAPACITY_GOVERNOR_50PCT_2026_07_02",
  "status": "completed_docs_only",
  "lease_owner": "mesh-agent-02:autonomous_engineer",
  "artifacts": [
    "docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/CAPACITY_GOVERNOR_50PCT.md",
    "docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/PLAN.md",
    "docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/ACTIONS.md",
    "docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/TESTS.md",
    "docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/RESULT.md",
    "docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/NEXT.md"
  ],
  "blockers": [],
  "next_action": "Operator may activate the two-hour governor and monitor with the read-only commands above; live drain/throttle actions require explicit owner authorization."
}
```

