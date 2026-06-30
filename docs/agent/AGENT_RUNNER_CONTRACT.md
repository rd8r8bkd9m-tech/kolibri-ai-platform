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
