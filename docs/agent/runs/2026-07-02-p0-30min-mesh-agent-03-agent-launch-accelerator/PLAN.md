# Plan

Task id: `P0_30MIN_MESH_AGENT_03_AGENT_LAUNCH_ACCELERATOR_2026_07_02`

Node: `mesh-agent-03`

Objective: produce a bounded, safe remote-agent launch plan that lets the
factory resume useful work without repeating the latest runtime deploy,
Telegram receiver, and artifact-contract failures.

## Scope

This accelerator is docs-only and control-plane-oriented. It does not start or
restart services, mutate Telegram Bot API state, rotate credentials, push to
`main`, or dispatch broad fanout directly from this worktree.

## Inputs Read

- `README.md`
- `docs/agent/dispatcher/QUEUE.md`
- `docs/agent/dispatcher/envelopes/P0_FACTORY_START_24_7_AGENT_MESH_2026_07_01.json`
- `docs/agent/dispatcher/envelopes/P0_PR91_POST_MERGE_MIMO_RUNNER_CANARY_2026_07_01.json`
- `docs/agent/runs/2026-07-02-p0-post-merge-remote-canary-execution/NEXT_REMOTE_TASKS.md`
- `docs/agent/runs/2026-07-02-p0-repair-post-merge-canary-runtime-blockers/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-deploy-factory-control-and-telegram-gateway-canary-repair/RESULT.md`
- `docs/agent/runs/2026-07-02-p0-factory-control-runtime-import-path-repair/RESULT.md`
- `ops/agent_host.py`
- `tests/test_agent_host_permission_contract.py`
- `tests/test_agent_host_runner_contract.py`
- `tests/test_factory_runtime_queue_contracts.py`

## Work Plan

1. Classify current launch blockers and non-negotiable safety gates.
2. Convert the classification into a short remote-agent launch wave that starts
   with read-only probes and only escalates after explicit gates pass.
3. Add a reusable launch readiness matrix under `docs/agent/intelligence`.
4. Add a prepared dispatcher envelope for the first safe wave.
5. Verify that the new JSON artifact is syntactically valid and that no product
   code changed.

## Safety Gates

- Remote work must run on server/control nodes, not a Mac dispatcher.
- First wave must be read-only/probe-only unless a later task records owner
  approval and deploy safety evidence.
- Telegram runtime work must not start a second receiver and must not mutate Bot
  API state without owner approval.
- Factory Control deploy work must wait for the runtime import-path release gate
  and a single-node canary.
- Any result must produce exact canonical run artifacts:
  `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, and `NEXT.md`.
