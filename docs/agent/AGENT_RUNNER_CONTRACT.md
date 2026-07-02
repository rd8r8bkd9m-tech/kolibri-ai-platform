# Agent Runner Contract

Date: 2026-06-30

This contract defines the minimum result and safety behavior for Kolibri Agent
Host runners before a task may be reported as completed to the Control Plane.

## Result Status

Runner results use only these Control Plane contract statuses:

- `completed`: all required artifacts are present and no contract blockers were found.
- `blocked`: the runner could not safely complete because the envelope constraints or
  required outputs were not satisfied.
- `failed`: runtime execution failed.

Domain-specific review states such as `APPROVED` or `CHANGES_REQUESTED` may be
kept in separate fields such as `runner_status`; they must not replace the
contract `status`.

## Required Result Fields

Every persisted runner result must include these fields:

- `task_id`
- `status`
- `changed_files`
- `artifact_dir`
- `required_artifacts_present`
- `required_artifacts_missing`
- `write_scope`
- `write_scope_violations`
- `read_only`
- `product_code_modification_forbidden`
- `product_code_changed`
- `push_attempted`
- `push_blocked`
- `blocked_reason`
- `failure_reason`
- `tests_run`
- `next_recommended_task`

## Push Policy

If the task envelope contains any of these truthy flags, the runner must not run
`git push`:

- `git_push_forbidden`
- `no_push`
- `read_only`

The result must report:

- `push_attempted: false`
- `push_blocked: true`
- `push_block_reason` naming the active constraint

If a push is attempted while one of those flags is truthy, the task must not be
completed. The result status must become `blocked`.

For implementation runners that are allowed to publish a branch, `git push` must
still run only after the runner contract preflight has passed. The preflight must
verify required artifacts, write scope, read-only/product-code constraints, and
artifact directory presence before publishing. If preflight fails, the runner
must report `push_attempted: false`, `push_blocked: true`, and use `/fail` rather
than publishing a branch and later discovering the task cannot complete.

## Read-Only And Product-Code Policy

When `read_only: true`, product code changes are forbidden. Docs and artifact
outputs are allowed unless a stricter `write_scope` is present.

When `product_code_modification_forbidden: true`, non-docs product changes are
blocked.

When `documentation_artifacts_only: true`, only these writes are allowed:

- `docs/**`
- the task artifact directory
- paths explicitly allowed by `write_scope`

## Write Scope

`write_scope` is a strict allowlist. If present, every changed file must match at
least one scope entry. Scope entries may be exact paths, directory prefixes, or
simple glob patterns such as `docs/agent/**`.

Any file outside scope is recorded in `write_scope_violations`, and the task
must not complete.

## Required Artifacts

The envelope may define required outputs with either:

- `required_outputs`
- `required_artifacts`

Each entry may be a string path or an object with `path`, `file`, `artifact`, or
`output`. Relative paths are checked against both the worktree and the artifact
directory. Absolute paths are checked directly.

If any required artifact is missing, the result must include it in
`required_artifacts_missing` and must not be completed.

## Backend Python Verification Environment

Backend verification commands may opt into a declared dependency-satisfied
Python environment. The contract is explicit: no backend environment is created
unless the task envelope contains one of these object keys:

- `backend_python_verification_env`
- `backend_test_environment`
- `backend_verification_environment`

The object must use `type: "backend_python"` or `type: "python_backend"`.
Supported setup inputs are intentionally narrow and auditable:

- `python`: interpreter used to create the venv, default `python3`
- `requirements` or `requirements_files`: explicit requirements files such as
  `backend/requirements.txt`
- `packages`: explicit packages or local package paths such as `pytest`
- `path`, `venv_path`, or `env_dir`: optional env path; relative paths resolve
  under the task artifact directory
- `cleanup`: default `true`

When enabled, verifier commands that start with `python`, `python3`, or `pytest`
run through the temporary backend environment. Other commands run unchanged.

The default env path is the task artifact directory, `backend-test-env`. Env
paths under the worktree are rejected so temporary dependencies cannot become
committed files. Cleanup is enabled by default, and repo ignore rules include the
standard backend test env names as a defense-in-depth guard.

If setup fails, the runner must report a structured blocker:

```json
{
  "error_type": "backend_test_environment_failed",
  "status": "blocked",
  "blocked_reason": "backend_test_environment_failed"
}
```

Example:

```json
{
  "backend_python_verification_env": {
    "type": "backend_python",
    "requirements": ["backend/requirements.txt"],
    "packages": ["pytest"],
    "cleanup": true
  }
}
```

## Canonical Run Artifacts

Owner-facing remote task runs that publish a docs run directory must declare one
canonical run artifact directory with one of these envelope keys:

- `canonical_run_artifact_dir`
- `run_artifact_dir`
- `run_artifacts_dir`

When present, the directory must contain exactly these required files:

- `PLAN.md`
- `ACTIONS.md`
- `TESTS.md`
- `RESULT.md`
- `NEXT.md`

The runner finalizer treats those five exact files as required artifacts by
appending their paths to `required_artifacts_present` and
`required_artifacts_missing`. Missing `NEXT.md` is therefore a contract blocker,
not a successful completion with an ambiguous owner-facing state.

Near-miss directories are not discovered by prefix, timestamp, or fuzzy match.
If a run produced the files under another directory, that directory must be
listed explicitly in one of these alias keys:

- `canonical_run_artifact_aliases`
- `run_artifact_aliases`
- `run_artifacts_aliases`

Aliases are deterministic and safe:

- aliases are inspected in the envelope order
- only an alias containing all five exact files may be used
- a complete alias is copied into the canonical directory without overwriting
  existing canonical files
- alias inspection is recorded in `canonical_run_artifact_alias_log` and
  persisted as `run-artifact-aliases.json` in the task artifact directory
- partial aliases never hide missing canonical files

Example:

```json
{
  "canonical_run_artifact_dir": "docs/agent/runs/2026-07-01-p0-run",
  "canonical_run_artifact_aliases": [
    "docs/agent/runs/2026-07-01-p0-run-final"
  ]
}
```

Expected result after a complete alias is materialized:

```json
{
  "status": "completed",
  "canonical_run_artifact_alias_used": "docs/agent/runs/2026-07-01-p0-run-final",
  "canonical_run_artifacts_missing": [],
  "required_artifacts_missing": []
}
```

## Unsupported Tasks

Unsupported task kinds or required capabilities must return a structured
`blocked` result. The Agent Host must not fall back to arbitrary execution and
must not modify product code for an unsupported task.

## Completion Gate

The Agent Host may call `/complete` only after the contract finalizer confirms:

- required artifacts are present
- write scope has no violations
- read-only/product-code constraints are satisfied
- forbidden push was not attempted
- artifact directory exists
- result JSON was written

Otherwise the Agent Host must call `/fail` with a structured contract result and
`error_type: runner_contract_blocked` for blocked states.

## Autopilot Truthfulness Gate

Autopilot tasks are enabled by any truthy envelope flag:

- `autopilot`
- `auto_pilot`
- `autonomous`
- `autopilot_enabled`

Before executing an autopilot task, Agent Host applies an admission gate. The
task must declare:

- a strict `write_scope`
- exact artifacts through `required_artifacts`, `required_outputs`, or a
  canonical run artifact directory
- a positive bounded timebox via `timebox_seconds`, `max_duration_seconds`,
  `timeout_seconds`, or `task_timeout_seconds`
- Agent Host `max_inflight=1`

The final result includes an `autopilot_gate` pass/fail matrix and repair tasks.
The matrix covers:

- server Agent Host execution, not Mac
- task_id/status/lease_owner/artifacts/blockers/next action recording
- exact artifact presence
- no fake `completed` claim while artifacts are missing
- no push to `main`, no force push, and no destructive git mutation
- write_scope compliance
- timebox compliance
- max_inflight compliance

If any matrix row fails, the task status becomes `blocked`; the result records
`blockers`, `next_action`, and `autopilot_gate.repair_tasks`. Commands that
exceed the declared timebox fail with `task_timebox_exceeded:<seconds>`.
Protected git operations are blocked before execution.

## Valid Envelope Examples

### Read-Only Probe With Required Artifact

```json
{
  "task_id": "KOL-READONLY-REPORT-1",
  "kind": "read_only_probe",
  "required_capability": "read_only_probe",
  "read_only": true,
  "no_push": true,
  "required_artifacts": [
    "docs/agent/reports/KOL-READONLY-REPORT-1/RESULT.md"
  ],
  "write_scope": [
    "docs/agent/reports/KOL-READONLY-REPORT-1/**"
  ]
}
```

Expected result if the artifact exists and only scoped docs changed:

```json
{
  "status": "completed",
  "push_attempted": false,
  "push_blocked": true,
  "push_block_reason": "no_push, read_only",
  "required_artifacts_missing": [],
  "write_scope_violations": [],
  "product_code_changed": false
}
```

### Documentation Artifact Task

```json
{
  "task_id": "KOL-DOCS-ONLY-1",
  "kind": "read_only_probe",
  "documentation_artifacts_only": true,
  "product_code_modification_forbidden": true,
  "required_outputs": [
    {
      "path": "docs/agent/runs/KOL-DOCS-ONLY-1/RESULT.md"
    }
  ],
  "write_scope": [
    "docs/agent/runs/KOL-DOCS-ONLY-1/**"
  ]
}
```

Expected result if only scoped docs outputs are written:

```json
{
  "status": "completed",
  "product_code_modification_forbidden": true,
  "product_code_changed": false,
  "required_artifacts_present": [
    "docs/agent/runs/KOL-DOCS-ONLY-1/RESULT.md"
  ],
  "write_scope_violations": []
}
```

## Invalid Outcome Examples

### Missing Required Artifact

If the envelope requires:

```json
{
  "required_artifacts": [
    "docs/agent/integration/FRONTEND_BACKEND_CONTRACT.md"
  ]
}
```

but the file does not exist in the worktree or artifact directory, the runner
must not complete:

```json
{
  "status": "blocked",
  "required_artifacts_missing": [
    "docs/agent/integration/FRONTEND_BACKEND_CONTRACT.md"
  ],
  "blocked_reason": "required_artifacts_missing"
}
```

### Write Scope Violation

If `write_scope` is `["docs/agent/allowed/**"]` and the task changes
`ops/agent_host.py`, the runner must not complete:

```json
{
  "status": "blocked",
  "changed_files": [
    "ops/agent_host.py"
  ],
  "write_scope_violations": [
    "ops/agent_host.py"
  ],
  "blocked_reason": "write_scope_violations"
}
```

### Forbidden Push Attempt

If the envelope has `git_push_forbidden: true` or `read_only: true`, any push
attempt is a blocker:

```json
{
  "status": "blocked",
  "push_attempted": true,
  "push_blocked": true,
  "push_block_reason": "git_push_forbidden",
  "blocked_reason": "forbidden_push_attempted"
}
```

The runner must also sanitize effective permissions before lease execution. A
`read_only`, `no_push`, or `git_push_forbidden` envelope cannot retain
`git_push` in `permissions`, `permission_set`, or `allowed_permissions`, and a
`full_autonomy` permission pack is downgraded to `read_only` before the task is
run. The sanitized view is recorded in `effective_permissions`.

### Publish Preflight Failure

If a branch-producing implementation runner is otherwise allowed to push but a
required artifact is missing, the runner must skip `git push`:

```json
{
  "status": "blocked",
  "push_attempted": false,
  "push_blocked": true,
  "push_block_reason": "required_artifacts_missing",
  "required_artifacts_missing": [
    "docs/agent/runs/TASK/RESULT.md"
  ],
  "blocked_reason": "required_artifacts_missing"
}
```

### Review Clone/Auth Failure

Review runners must write `result.json` even when the initial clone cannot
authenticate. If clone stderr indicates missing GitHub credentials, missing repo
access, disabled prompts, or SSH permission denial, the result must fail with
`error_type: review_clone_auth_failed`, keep `required_artifacts_missing` empty,
and recommend repairing the Agent Host git credentials before rerunning review.

### Owner Remote Task Requested Runner

`owner_remote_task` is a supported task kind. The Agent Host must honor the
requested `runner` exactly. A task with `runner: mimo` must invoke MIMO or fail
with a structured runner result; it must not invoke Codex unless the task
envelope carries an explicit, audited fallback policy. A task with
`runner: codex` follows the same rule for Codex.

Runner auth and availability failures must be classified without credential
repair side effects:

```json
{
  "status": "blocked",
  "kind": "owner_remote_task",
  "runner": "mimo",
  "blocked_reason": "runner_auth_blocked",
  "next_recommended_task": "repair mimo auth on this node or route to another online node with runner:mimo"
}
```

Nodes that advertise `runner:<name>` but fail with `runner_auth_blocked` or
`runner_unavailable` must be marked blocked or unavailable for that runner so
future leases do not treat the node as a healthy path for that runner.

### Unsupported Task Kind

If the Agent Host receives an unsupported `kind`, it must return a structured
blocked result and avoid product modifications.
