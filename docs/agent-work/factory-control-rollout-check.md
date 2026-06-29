# Factory Control Plane rollout check

Date: 2026-06-29
Role: SRE rollout factory
Scope: local review of `ops/factory_control.py` and
`tests/test_factory_runtime_queue_contracts.py`; rollout procedure for Control
Plane only. This note is intentionally operator-facing and does not execute
against live servers.

## Change summary

The local Control Plane change makes task list reads bounded and adds a small
agent-message feed:

- `/v1/tasks` now applies `FACTORY_DEFAULT_TASK_LIST_LIMIT`,
  `FACTORY_MAX_TASK_LIST_LIMIT`, and queue prefix reads instead of returning
  the full Redis queue by default.
- `/v1/tasks?summary=1&compact=1` returns a bounded summary with
  `queue_total`, `queue_returned`, `queue_truncated`, `tasks_scanned`,
  `tasks_matched`, `tasks_returned`, `tasks_truncated`, `active_total`,
  `expired_lease_total`, and `lease_expiring_soon_total`.
- `compact_task_listing()` strips large `envelope` and `result` payloads from
  task list output.
- `/v1/agent-messages` accepts `POST` updates and exposes target feeds with
  `GET`, backed by Redis lists capped to 500 entries per target.
- The added queue contract test covers bounded compact listings, queue totals,
  truncated queue prefixes, stripped payloads, state counts, and expired lease
  summary fields.

## Local verification

Run before packaging the rollout artifact:

```bash
python3 -m compileall -q ops/factory_control.py \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_agent_messages.py
```

Expected: no output and exit code 0.

Run when `pytest` is available in the deploy/test environment:

```bash
python3 -m pytest \
  tests/test_factory_runtime_queue_contracts.py \
  tests/test_factory_agent_messages.py
```

Expected: all tests pass. In this local worktree, system Python does not have
`pytest` installed, so only `compileall` was executed.

Do not run FormulaLM, local LLM workers, or Mac-side agent runners as part of
this rollout check.

## Preflight on Control Plane

All commands below are for the Control Plane operator. Capture output before
changing files.

```bash
date -u
hostname
git -C /opt/kolibri-ai-platform status --short
systemctl status kolibri-factory-control --no-pager
curl -fsS http://127.0.0.1:9101/health
curl -fsS http://127.0.0.1:9101/v1/nodes > /tmp/factory-nodes.before.json
curl -fsS 'http://127.0.0.1:9101/v1/tasks?summary=1&compact=1&limit=20' \
  > /tmp/factory-tasks.before.json
```

Preflight must pass before rollout:

- `/health` reports `status=ok`, `queue_backend=redis`, and `redis=PONG`.
- The service unit is active or its current failure mode is documented before
  restart.
- `git status --short` has no unknown operator changes that would be
  overwritten by the deployment.
- `factory-tasks.before.json` is saved even if it is large; it is the rollback
  comparison point.

## Rollout

Use a canary deployment for the Control Plane process only. Do not drain nodes,
submit tasks, requeue tasks, or mutate live queue state during the binary/file
swap.

1. Prepare rollback artifact:

```bash
sudo install -m 0644 /opt/kolibri-ai-platform/ops/factory_control.py \
  /var/backups/kolibri-factory-control/factory_control.py.$(date -u +%Y%m%dT%H%M%SZ)
```

2. Install the reviewed `ops/factory_control.py` into the Control Plane
   checkout using the standard repo deploy path.

3. Keep the first rollout on conservative limits:

```bash
sudo systemctl set-environment FACTORY_DEFAULT_TASK_LIST_LIMIT=100
sudo systemctl set-environment FACTORY_MAX_TASK_LIST_LIMIT=500
sudo systemctl set-environment FACTORY_MAX_TASK_SUMMARY_SCAN=2000
sudo systemctl set-environment FACTORY_LEASE_EXPIRING_SOON_SECONDS=30
```

4. Restart only the Control Plane sidecar:

```bash
sudo systemctl restart kolibri-factory-control
sleep 3
systemctl status kolibri-factory-control --no-pager
```

Abort immediately if the service does not stay active.

## Smoke checks

Run read-only checks first:

```bash
curl -fsS http://127.0.0.1:9101/health
curl -fsS 'http://127.0.0.1:9101/v1/tasks?summary=1&compact=1&limit=1' \
  | tee /tmp/factory-tasks.after.limit1.json
curl -fsS 'http://127.0.0.1:9101/v1/tasks?summary=1&compact=1&limit=20' \
  | tee /tmp/factory-tasks.after.limit20.json
curl -fsS 'http://127.0.0.1:9101/v1/tasks?compact=1&limit=20' \
  | tee /tmp/factory-tasks.after.compact.json
curl -fsS 'http://127.0.0.1:9101/v1/agent-messages?target=all&limit=20' \
  | tee /tmp/factory-agent-messages.after.json
```

Expected task-list behavior:

- `summary.queue_total` is the real Redis queue length.
- `summary.queue_returned` is at most the requested `limit`.
- `summary.queue_truncated` is true when `queue_total > queue_returned`.
- `summary.tasks_returned` is at most the requested `limit`.
- `summary.summary_scope` is `bounded_scan`.
- The `tasks[]` entries do not include full `envelope` or `result` payloads.
- Response size for `limit=1` and `limit=20` is small enough for owner-facing
  status polling and does not resemble the previous multi-megabyte payload.

Expected lease summary behavior:

- `summary.active_total` counts `leased`, `running`, `waiting_review`, and
  `review` tasks in the bounded scan.
- `summary.expired_lease_total` surfaces active tasks with expired leases.
- `summary.lease_expiring_soon_total` surfaces active tasks whose lease expires
  within `FACTORY_LEASE_EXPIRING_SOON_SECONDS`.

Agent-message smoke is optional but useful if a staging namespace is available:

```bash
curl -fsS -X POST http://127.0.0.1:9101/v1/agent-messages \
  -H 'content-type: application/json' \
  -d '{"sender":"rollout-smoke","to":"rollout-smoke","kind":"status","body":"ok"}'
curl -fsS 'http://127.0.0.1:9101/v1/agent-messages?target=rollout-smoke&limit=5'
```

Only run that POST against production if operator policy allows writing a
harmless feed message. It must not create, lease, cancel, requeue, or complete
tasks.

## Abort signals

Stop rollout and roll back if any of these occur:

- `/health` returns non-200, Redis errors, or `control_plane_error`.
- `/v1/tasks?summary=1&compact=1&limit=1` returns full task envelopes/results
  or a large unbounded queue.
- `queue_total` is missing, obviously lower than `queue_returned`, or changes
  only because `limit` changes.
- `limit` requests above `FACTORY_MAX_TASK_LIST_LIMIT` are not capped.
- Existing Agent Host leasing starts returning 500s after restart.
- Service logs show repeated JSON/Redis exceptions for normal task-list reads.

Log inspection:

```bash
journalctl -u kolibri-factory-control -n 200 --no-pager
```

## Rollback

Rollback is file-level plus service restart. It must not mutate queue state.

1. Restore the previous file:

```bash
sudo install -m 0755 \
  /var/backups/kolibri-factory-control/factory_control.py.<timestamp> \
  /opt/kolibri-ai-platform/ops/factory_control.py
```

2. Clear rollout-only environment overrides if they were applied through
   systemd:

```bash
sudo systemctl unset-environment \
  FACTORY_DEFAULT_TASK_LIST_LIMIT \
  FACTORY_MAX_TASK_LIST_LIMIT \
  FACTORY_MAX_TASK_SUMMARY_SCAN \
  FACTORY_LEASE_EXPIRING_SOON_SECONDS
```

3. Restart and verify:

```bash
sudo systemctl restart kolibri-factory-control
sleep 3
curl -fsS http://127.0.0.1:9101/health
journalctl -u kolibri-factory-control -n 100 --no-pager
```

4. Compare post-rollback task and node snapshots with the preflight files. Do
   not manually requeue or cancel tasks as part of rollback unless a separate
   incident decision authorizes it.

## Post-rollout watch

For 15 minutes after a successful rollout, poll read-only endpoints:

```bash
watch -n 30 "curl -fsS 'http://127.0.0.1:9101/v1/tasks?summary=1&compact=1&limit=20' | jq '{queue_total: .summary.queue_total, queue_returned: .summary.queue_returned, active_total: .summary.active_total, expired_lease_total: .summary.expired_lease_total, tasks_returned: .summary.tasks_returned, tasks_truncated: .summary.tasks_truncated}'"
```

Success criteria:

- Control Plane remains healthy.
- Queue lease flow continues normally.
- Owner/status clients receive bounded task-list payloads.
- Expired lease counts are visible without relying on full unbounded task
  downloads.
- No live task state is changed by the rollout procedure itself.
