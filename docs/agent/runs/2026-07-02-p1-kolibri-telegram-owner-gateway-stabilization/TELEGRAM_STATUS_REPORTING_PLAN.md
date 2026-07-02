# Telegram Status Reporting Plan

Task id: P1_KOLIBRI_TELEGRAM_OWNER_GATEWAY_STABILIZATION_2026_07_02
Date: 2026-07-02
Scope: owner-safe status reporting for the Telegram gateway.

## Reporting Goals

- Give the owner a useful answer without exposing factory internals.
- Prefer compact Russian summaries over raw JSON, paths, IDs, logs, or queue records.
- Keep every status response actionable: accepted, in queue, running, waiting review, complete, failed, cancelled, or needs investigation.
- Preserve fake-client testability.

## Status Sources

- `FactoryClient.nodes()` for fleet and runner availability.
- `FactoryClient.get_tasks()` for queue and active task counts.
- `FactoryClient.get_task(task_id)` for explicit owner status requests.
- Gateway state store for tracked task transitions and conversation memory.
- Agent result payloads only after redaction and safe formatter handling.

## Owner Message Shapes

### Fleet Summary

Used by `/nodes`.

Content:

- Number of online/offline/draining nodes.
- Human role names when available.
- Short health phrase.

Forbidden:

- Raw node IDs, hostnames, private addresses, heartbeat internals, absolute paths, or runner debug state.

### Agent Summary

Used by `/agents`.

Content:

- Count of available roles/runners.
- High-level availability and degraded/unavailable count.

Forbidden:

- Agent IDs, process IDs, lease IDs, runner auth details, raw capability arrays, or node mapping internals.

### Queue Summary

Used by `/queue`.

Content:

- Queue length.
- Counts by state.
- Optional safe next-step phrase.

Forbidden:

- Task IDs, owner raw prompts, branch names, artifact paths, PR numbers unless explicitly sanitized, or raw envelope fields.

### Task Status

Used by `/status`, `/cancel`, `/retry`, and transition polling.

Content:

- Human state.
- Sanitized result summary or safe URL when applicable.
- Clear failure phrase when the task failed.

Forbidden:

- Stack traces, stderr, command lines, runner prompts, raw result manifests, file paths, env names, credentials, or task metadata not needed by the owner.

## Transition Reporting

The gateway maps Control Plane states into owner-facing states:

- `queued` -> accepted/queued.
- `leased` and `running` -> in work.
- `waiting_review` -> waiting for review.
- `review` -> under review.
- `completed` -> ready.
- `failed` and `dead_letter` -> needs investigation.
- `cancelled` -> cancelled.

Transition reports should be emitted only when they add meaningful information. Repeated raw progress noise should not be relayed.

## Test Plan

- Keep fake Telegram assertions for `/nodes`, `/agents`, and `/queue` summary redaction.
- Extend fake task payload coverage for `/status`, `/cancel`, and `/retry` before broadening command behavior.
- Add table-driven tests for result payload shapes that include paths, token-like strings, stderr, stack traces, and nested manifests.
- Keep live Telegram smoke separate from regression tests.

## Deferred Work

- Rich Telegram report rendering remains future work behind capability checks.
- Mini App read models remain out of this P1 owner gateway stabilization scope.
- Live status canary remains blocked until the owner approves a non-mutating smoke window.

