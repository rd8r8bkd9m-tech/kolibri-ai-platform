# Kolibri Agent Development Factory v1

Factory v1 is the persistent control plane for Codex-led MiMo/OpenClaw
development. It exists so agent work continues as a queue with durable state,
review gates, artifacts, and rollback rules instead of ad hoc terminal sessions.

## Current Gate

Status: `BOOTSTRAP`.

Allowed now:
- inventory;
- schema validation;
- dry-run task dispatch;
- two read-only canary tasks;
- local factory tests.

Blocked until gates pass:
- 18/19-node fanout;
- production mutation;
- paid ML training;
- direct deploy from agents.

## Layout

- `server_inventory.json`: known server registry and current unknowns.
- `agents/registry.json`: role-to-server assignments.
- `schemas/`: `TASK_ENVELOPE`, `RESULT_ENVELOPE`, status, and state schemas.
- `backlog/`: prioritized work and state machine.
- `tasks/`: task envelopes by lifecycle state.
- `policies/`: safety, Git/worktree, quality, rollout, and rollback rules.
- `scripts/`: local control-plane commands.
- `memory/`: durable decisions, lessons, recurring errors.
- `logs/`: redacted command output and cycle summaries.
- `runs/`: durable runtime state and dry-run artifacts.

## Commands

Status:

```bash
python3 .factory/scripts/factory_status.py
```

Dry-run dispatch without SSH:

```bash
python3 .factory/scripts/dispatch_task.py --task .factory/tasks/ready/KOL-CANARY-001.json --dry-run
```

Bootstrap one remote worker with official Mimocode and a repo bundle:

```bash
python3 .factory/scripts/bootstrap_worker.py --server hostvds-agent-03 --dry-run
python3 .factory/scripts/bootstrap_worker.py --server hostvds-agent-03
```

Validate a result envelope:

```bash
python3 .factory/scripts/validate_result.py .factory/templates/result_envelope.json
```

Collect current legacy remote results:

```bash
python3 .factory/scripts/collect_results.py
```

Check stale heartbeats:

```bash
python3 .factory/scripts/heartbeat_check.py
```

Safely stop one exact task:

```bash
python3 .factory/scripts/stop_exact_task.py --task-id KOL-CANARY-001 --pid-file /dev/shm/factory_bootstrap_KOL-CANARY-001.pid
```

## First Pilot

Run only two canary tasks first:

1. `KOL-CANARY-001`: read-only factory/bootstrap audit.
2. `KOL-CANARY-002`: read-only FormulaLM Proof v1 readiness audit.

Scale after evidence:

```text
2 servers -> 4 servers -> 8 servers -> 18/19 servers
```

MiMo workers start only after schema validation, dry-run, heartbeat, collect,
and review gates pass.
