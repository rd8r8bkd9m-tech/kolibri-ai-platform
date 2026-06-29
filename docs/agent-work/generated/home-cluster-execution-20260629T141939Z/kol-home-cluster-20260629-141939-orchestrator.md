# Kolibri Home Cluster Orchestrator

Task id: `KOL-HOME-CLUSTER-20260629-141939-ORCHESTRATOR-DELIVERABLE-RETRY`
Execution: `home-cluster-execution-20260629T141939Z`
Primary role slot: `codex-slot-0`
Generated at: `2026-06-29T14:19:39Z`
Scope: coordination artifact only. No deploy, restart, or live routing change is authorized by this task.

## Mission

Act as the primary orchestrator for the home cluster execution and keep the Control Plane, Telegram-facing owner updates, worker slots, retry rules, and next executable actions synchronized. This artifact is the shared source of truth for agents joining the execution after the retry.

## Task Distribution

| Stream | Owner slot | Responsibility | Output contract | Current state |
| --- | --- | --- | --- | --- |
| Orchestration and lease control | `codex-slot-0` | Own task state, retry policy, artifact publishing, Telegram fallback, final result payload | Markdown report, result JSON, Control Plane completion | Active |
| Repository verification | `worker-slot-verify` | Run non-deploy checks against changed artifacts and relevant runtime contracts | Command list with exit status and notes | Pending until checks run |
| Telegram coordination | `worker-slot-telegram` | Send 5-minute owner updates when credentials/runtime are available; otherwise emit fallback `agent_message` artifact | Sent Telegram message id or `agent-message.json` fallback | Fallback selected; no secret access required |
| Worker dispatch | `worker-slot-dispatch` | Assign implementation workers if the owner adds code tasks; keep deploy/restart blocked unless explicitly authorized | Worker slot map updates and blockers | Standby |
| Risk and blocker tracking | `worker-slot-risk` | Track unavailable nodes, expired leases, missing credentials, and cross-agent conflicts | Blocker list with next action | Active inside this report |

## Worker Slot Map

| Slot | Lease owner format | Allowed work | Disallowed work | Handoff note |
| --- | --- | --- | --- | --- |
| `codex-slot-0` | `node:codex-slot-0` | Coordination, docs, checks, Control Plane result updates | Deploy, restart, secret inspection | Primary orchestrator for this retry |
| `worker-slot-verify` | `node:worker-slot-verify` | `pytest`, syntax checks, artifact validation | Service mutation | Use only read-only commands |
| `worker-slot-telegram` | `node:worker-slot-telegram` | Telegram owner status updates or fallback message creation | Printing tokens, changing bot config | Use existing gateway if already running |
| `worker-slot-dispatch` | `node:worker-slot-dispatch` | Queue follow-up implementation tasks | Manual live host changes | Requires explicit owner objective |
| `worker-slot-risk` | `node:worker-slot-risk` | Blocker triage and stale lease detection | Cancelling unrelated tasks | Escalate only if progress is blocked |

## Lease And Retry Policy

1. A worker must heartbeat at least once per lease interval and include `worktree`, `branch`, `pid`, and log paths when the Control Plane contract supports them.
2. A lease is considered stale when `lease_until` is in the past and no heartbeat has updated the task. Stale work must be re-queued rather than overwritten in-place.
3. Retry attempts must preserve the previous `result_reference`, error type, and attempt id in task history when available.
4. Retried workers must read the latest artifact directory before editing nearby files.
5. If two workers touch the same file, the later worker adapts to the existing delta and does not revert unrelated changes.
6. Retry stops when the Control Plane reaches terminal state, when max retries are exhausted, or when the same external blocker repeats for three consecutive attempts.
7. Deploy, restart, live routing, service draining, or Telegram secret changes require a separate explicit task.

## 5-Minute Telegram Reporting Plan

Cadence starts when the task is accepted by the orchestrator and repeats every five minutes until completion or handoff.

| Minute | Message intent | Required content | Fallback when Telegram is unavailable |
| --- | --- | --- | --- |
| 0 | Acceptance | Orchestrator accepted task, no deploy/restart, artifact path | Write `agent-message.json` with same text |
| 5 | Progress | Task distribution, active checks, blockers | Append/update fallback message status |
| 10 | Verification | Commands run, pass/fail summary, changed files | Store checks in result JSON |
| 15+ | Follow-up | Remaining actions, required owner input, PR/commit evidence | Include in Control Plane result |
| Completion | Done | Result reference, changed files, checks, commit or PR evidence | Complete Control Plane task with fallback evidence |

Fallback owner-facing message:

```text
Kolibri orchestrator accepted KOL-HOME-CLUSTER-20260629-141939-ORCHESTRATOR-DELIVERABLE-RETRY. I created the home-cluster execution coordination artifact, kept deploy/restart out of scope, and will report changed files, checks, blockers, and commit evidence in the Control Plane result.
```

## Blockers

| Blocker | Impact | Mitigation |
| --- | --- | --- |
| Telegram runtime credentials are not exposed to this worker | Cannot safely send a live Telegram message from this lease | Use artifact-backed fallback `agent-message.json`; do not inspect or print secrets |
| Role catalog excerpt is empty | No externally supplied worker roster | Use conservative local slot names and explicit handoff contracts |
| Deploy/restart is forbidden by task scope | Runtime state cannot be changed for verification | Use repository checks only |
| Control Plane availability is environment-dependent | Completion/annotation may fail if sidecar is unreachable | Attempt CLI/HTTP update and record command result |

## Next Executable Actions

1. Validate the markdown artifact exists and is non-empty.
2. Validate fallback `agent-message.json` and result summary JSON parse cleanly.
3. Run focused Control Plane contract tests that cover result references and queue contracts.
4. Commit the generated artifacts on the current branch.
5. Push the branch or report the exact push blocker.
6. Complete or annotate the Control Plane task with `result_reference`, changed files, checks, and commit or PR evidence.

## Verification Commands

Planned commands:

```bash
test -s docs/agent-work/generated/home-cluster-execution-20260629T141939Z/kol-home-cluster-20260629-141939-orchestrator.md
python3 -m json.tool docs/agent-work/generated/home-cluster-execution-20260629T141939Z/agent-message.json
python3 -m json.tool docs/agent-work/generated/home-cluster-execution-20260629T141939Z/result.json
python3 -m pytest tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py
```

## Current Status

The primary orchestrator has created the coordination plan and selected a safe Telegram fallback. No deploy, restart, live service mutation, or secret access has been performed.
