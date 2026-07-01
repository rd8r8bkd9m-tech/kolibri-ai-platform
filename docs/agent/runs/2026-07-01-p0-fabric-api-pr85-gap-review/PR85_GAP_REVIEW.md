# PR #85 Gap Review: API-First Full-Control Fabric

Task id: `2026-07-01-p0-fabric-api-pr85-gap-review`
Node: `kolibri`
Reviewer: `autonomous_engineer`
Reviewed at: `2026-07-01T14:29:49Z`
Repository: `rd8r8bkd9m-tech/kolibri-ai-platform`

## Decision

Release decision: `repair_in_pr85`

PR #85 is not merge-ready. It is accessible, open, draft, and GitHub reports it as mergeable, but it should be repaired in PR #85 before release because the implementation does not satisfy the larger API-first Fabric surface documented by the master canvas / Prompt #3 artifacts in the PR.

## Remote Review Scope

- Review ran on server/control node `kolibri` from repository path `/var/lib/kolibri-agent/worktrees/2026-07-01-p0-fabric-api-pr85-gap-review/2026-07-01-p0-fabric-api-pr85-gap-review-attempt-1/repo`.
- No local Mac implementation was used.
- Product code was not modified by this review.
- Secrets were not printed. The review confirmed PR #85 replaces a literal sudo-password field with `sudo_password_env`; this report does not repeat the removed value.

## Inputs Compared

- PR #85: `Finalize API-first full-control Fabric`
  - State: open, draft, not merged.
  - Base: `main` at `6d0317c52a9694448ee2c352dc196ce7a27b9487`.
  - Head: `p0/api-first-full-control-fabric-2026-07-01` at `9690361f02addeff37771c52fd37878aef455e13`.
  - Changed files: 29.
- Master canvas / Prompt #3 requirement evidence available in PR #85:
  - `docs/superfactory/API_FIRST_CONTROL_FABRIC.md`
  - `docs/superfactory/TASKS.md`
  - `docs/superfactory/ANY_NODE_API_ACCESS_RUNBOOK.md`
  - `docs/fabric-api-first-control.md`
- PR #91 dependency check:
  - PR #91 is accessible, open, draft, not merged.
  - Head: `p0/mimo-runner-output-auth-contract-repair-2026-07-01` at `350544492ce14a12865fb9a04e2abf6f87c87d3f`.
  - Scope: `ops/agent_host.py`, direct MIMO runner output/auth classification, and tests.
  - Assessment: helpful for remote Agent Host execution quality, but not a hard code dependency for PR #85's control-plane endpoints. Both PRs are draft and should not be merged automatically.

## Gap Matrix

| Requirement | Evidence | PR #85 status | Decision impact |
| --- | --- | --- | --- |
| API-first control path, SSH emergency-only | README and Fabric docs added; dispatcher language updated | Mostly met as policy and partial CLI behavior | Not blocking alone |
| Protected Fabric health/policy/routes endpoints | `GET /v1/fabric/health`, `/policy`, `/routes`, `/keys/rotation` implemented in `ops/factory_control.py` | Met for narrower `/v1/fabric/*` surface | Positive |
| Structured blocked response instead of dead-end unavailable | `fabric_route`, dispatcher unreachable envelope, backend degraded fallback | Partially met | Needs broader reason taxonomy |
| Prompt #3 canonical fleet endpoints | Canvas requires `GET /v1/fleet/nodes`, `/topology`, `/route`, `/capabilities` | Not implemented; only docs/runbook mention them | Blocking repair |
| Prompt #3 model/API endpoints | Canvas requires `GET /v1/models`, `POST /v1/responses`, `POST /v1/chat/completions` | Not implemented | Blocking repair |
| Prompt #3 agent endpoints | Canvas requires `POST /v1/agents/tasks`, status, artifacts, cancel | Not implemented as aliases; existing task endpoints remain `/v1/tasks/*` | Blocking repair |
| Prompt #3 admin endpoints | Canvas requires `POST /v1/admin/exec`, `/service`, `/git`, `/bootstrap-node`, `/rotate-keys` | Not implemented; PR has safe `/v1/fabric/bootstrap` and policy docs only | Blocking repair |
| Request/response envelope schema | Canvas requires common `task_id`, `trace_id`, owner/source/role/route fields | Not implemented as canonical schemas or validation | Blocking repair |
| Fallback reason taxonomy | TASKS requires `api_unreachable`, `vpn_down`, `firewall`, `disk_full`, `auth_failed`, `dns`, `unknown` | PR mostly returns generic route/control-plane reasons | Repair needed |
| Owner rights/security gates | Policies and docs added | Mostly documentation/safe stubs; no auth enforcement in sidecar | Should remain safe-stub or implement gates explicitly |
| Node identity and key rotation | Policy endpoint and docs added | Contract only, no rotation action implementation | Repair or clearly label as contract-only |
| New server bootstrap | `/v1/fabric/bootstrap` safe stub added | Partial; canvas also expects `/v1/admin/bootstrap-node` and fleet registration path | Repair needed |
| Secret hygiene | Literal credential removed from config and env reference used | Met for PR diff; do not print historical value | Positive |
| Test coverage | `tests/test_fabric_control.py` added | Focused tests pass; tests do not assert missing Prompt #3 endpoints | Add endpoint/schema tests |
| Patch hygiene | `git diff --check origin/main...HEAD` fails on extra blank lines at EOF in 11 docs files | Minor docs hygiene failure | Fix while repairing |

## Verification Commands

- `git fetch origin pull/85/head:refs/remotes/origin/pr/85 pull/91/head:refs/remotes/origin/pr/91 main` -> passed.
- GitHub connector PR metadata and comments for PR #85 and PR #91 -> accessible; no comments or review threads returned.
- `git diff --stat origin/main...origin/pr/85` -> 29 files, 1579 insertions, 14 deletions.
- `python3 -m pytest tests/test_fabric_control.py -q` in PR #85 temp worktree -> `5 passed in 0.08s`.
- `/tmp/kolibri-p0-fabric-venv/bin/python -m pytest -q` in PR #85 temp worktree -> `65 passed, 1 warning in 4.42s`.
- `python3 -m pytest -q` with system Python -> blocked by missing local dependencies `pydantic` and `httpx`.
- `git diff --check origin/main...HEAD` in PR #85 temp worktree -> failed on extra blank lines at EOF in docs files.
- `git grep` for Prompt #3 endpoints -> required endpoints appear in docs only, not implementation.

## Blockers

1. PR #85 is still draft.
2. Required Prompt #3 API surface is not implemented: `/v1/fleet/*`, `/v1/models`, `/v1/responses`, `/v1/chat/completions`, `/v1/agents/*`, and `/v1/admin/*`.
3. Canonical request/response envelopes are documented but not implemented or validated.
4. Admin/security gates are documented but not enforced in an API contract, except for safe-stub policy text.
5. Tests pass but only cover the narrower `/v1/fabric/*` contracts; they would not catch missing Prompt #3 endpoints.
6. `git diff --check` fails on documentation whitespace.

## Next Exact Task

Task id: `P0_PR85_PROMPT3_FABRIC_API_SURFACE_REPAIR_2026_07_01`

Repair PR #85 in-place by adding tested compatibility endpoints and schemas for the Prompt #3 API surface:

1. Implement `/v1/fleet/nodes`, `/v1/fleet/topology`, `/v1/fleet/route`, and `/v1/fleet/capabilities` over the existing node/fabric route data.
2. Implement `/v1/agents/tasks`, `/v1/agents/status/{task_id}`, `/v1/agents/artifacts/{task_id}`, and `/v1/agents/cancel/{task_id}` as aliases over the existing task control plane.
3. Add safe-stub, deny-by-default `/v1/admin/*` endpoints with explicit auth/scope/audit blocked envelopes.
4. Add OpenAI-compatible fabric stubs or route contracts for `/v1/models`, `/v1/responses`, and `/v1/chat/completions`.
5. Add canonical request/response envelope helpers and tests for required fields.
6. Expand fallback reason classification tests.
7. Fix docs EOF whitespace so `git diff --check` passes.

