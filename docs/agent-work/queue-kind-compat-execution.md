# Queue kind compatibility execution

Date: 2026-06-29
Role: `queue_kind_compat_executor`

## Scope

Prepared a local compatibility patch for old queued runtime envelopes. No live
Control Plane task was submitted, cancelled, requeued, drained, restarted, or
edited in Redis/spool state.

## Change

- `ops/factory_control.py` now treats `remote_implementation_runner_ready` as a
  legacy required capability that can be satisfied by nodes advertising
  `implementation` or `generic_implementation`.
- `ops/factory_control.py` exposes `runner_kind` in compact task output so the
  migration path is visible without mutating stored task `kind`.
- `ops/agent_host.py` now advertises both the current implementation capability
  and the legacy alias in default capabilities.
- `ops/agent_host.py` maps a legacy task kind
  `remote_implementation_runner_ready` to the existing
  `generic_implementation` runner path.
- `tests/test_factory_runtime_queue_contracts.py` covers both compatibility
  paths and verifies that the stored queued kind/state are not rewritten.
- `ops/envelopes/KOL-QUEUE-KIND-COMPAT-20260629.json` is a review-ready
  proposal envelope for applying this patch through the factory after operator
  review.

## Safety

This is classification-only compatibility. It does not perform queue surgery:

- no `submit_control_plane_task`;
- no cancel/requeue/drain/restart of live nodes;
- no SSH;
- no Redis or spool edits;
- no staging, commit, push, or PR creation from this pass;
- no FormulaLM or local Mac LLM benchmark runs.

## Acceptance Status

- Old queued kinds are classified with migration or supported runner path: done.
- No queue surgery is performed: done.
- Envelope is safe to submit after review: done.
- No `formulalm_llm_mac_runs`: done.

## Review Notes

The patch intentionally leaves stored task `kind` unchanged. The migration is
computed at lease/runner time so existing queue entries can remain auditable and
operator-visible.
