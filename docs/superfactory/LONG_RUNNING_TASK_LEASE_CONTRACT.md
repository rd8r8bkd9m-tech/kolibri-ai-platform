# Long-Running Task Lease Contract

Date: 2026-07-02

Long-running Agent Host tasks must keep their Factory Control Plane lease alive for the entire execution window. This contract applies to direct MIMO, Codex, API/local model runners, image or crawler-like runners, generic subprocess runners, and future runner paths.

## Runtime Contract

1. A task is submitted and starts in `queued`.
2. A compatible Agent Host leases it and receives `leased` state plus `lease_until`.
3. When execution begins, the host heartbeats `/v1/tasks/{task_id}/heartbeat` with `state=running`.
4. While the runner is blocked in subprocess, model, network, crawler, or image work, the host refreshes the lease before expiry.
5. The control plane extends `lease_until` on each heartbeat.
6. A live task with a fresh `heartbeat_at` must not be moved to `dead_letter`.
7. Runner completion must write `result.json` and any runner contract artifacts before calling complete or fail.
8. Runner death, nonzero exit, missing binary, network failure, auth failure, or heartbeat failure must produce a structured failed or blocked result artifact.

## Status Fields

Status responses expose:

- `state`: queue lifecycle state such as `queued`, `leased`, `running`, `completed`, `failed`, `blocked`, or `dead_letter`.
- `lease_status`: `unleased`, `leased`, `lease_expired`, or `terminal`.
- `heartbeat_status`: `heartbeating`, `heartbeat_stale`, or `missing`.
- `heartbeat_age_seconds`: age of the latest task heartbeat.
- `seconds_until_lease_expiry`: remaining lease time when a lease exists.

## Failure Semantics

Heartbeat failure is not treated as a normal runner failure. The Agent Host reports `lease_heartbeat_failed`, writes a structured artifact, and disables automatic retry for that attempt until control-plane connectivity is repaired.

Runner auth and policy failures are blocked, not hidden by fallback to a different runner. Missing runners are blocked with a route/install recommendation.

## Requeue Gate

Do not requeue a large MIMO wave or FormulaLM crawler wave until a canary proves:

- at least two heartbeat renewals per long-running task;
- no `lease_expired` while the runner is alive;
- each task writes `result.json`;
- each task reaches `completed`, `failed`, or `blocked` with structured reason;
- dispatch status shows lease and heartbeat state.
