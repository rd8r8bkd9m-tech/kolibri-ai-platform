---
name: database-migrations
description: "Safe DB migrations. Use when: Schema changes."
version: 2.0.0
license: MIT
---

# Database Migrations

## Purpose
Safe DB migrations.

## When to use
Schema changes.

## Workflow
Expand → migrate → backfill → contract → optionally contract cleanup.

## Rules
Не делать irreversible destructive migration in one step.

## Inputs
- Relevant repository files and current runtime state.
- Existing contracts, tests, configuration and user requirements.

## Outputs
- A concrete code/config/design change or a verified diagnostic result.
- Evidence: changed files, commands/tests executed, and known limitations.

## Verification
1. Inspect the final diff.
2. Run the smallest relevant tests first.
3. Run typecheck/build or platform validation when applicable.
4. Confirm no unrelated regressions.

## Done criteria
Migration works on representative data.

## Failure handling
If blocked, stop at the smallest safe boundary and report the exact blocker, evidence, attempted fixes, and the next actionable step. Do not invent missing facts.

## Agent behavior
- Prefer existing project conventions over introducing new frameworks.
- Make the smallest change that solves the stated problem.
- Preserve backwards compatibility unless the task explicitly allows breaking changes.
- Never expose secrets, tokens or credentials in logs, commits or reports.


## Operational contract

### Before editing
- Inspect the current implementation, tests, package versions, and local conventions.
- Identify whether the change crosses mobile, backend, AI, data, security, or release boundaries.
- Select the narrowest additional skills required; do not load the entire skill tree by default.

### During implementation
- Make changes in coherent units that can be individually verified.
- Keep domain rules in deterministic code and keep UI/orchestration concerns separate.
- Treat network responses, uploaded files, and LLM output as untrusted data.

### After implementation
- Run the closest automated checks first.
- If the change is user-facing, verify the UI state or E2E flow.
- If the change is security-sensitive, run the relevant security checks.
- Inspect the final diff and report exact evidence.

## Evidence contract
The final handoff must include: changed paths, verification commands, observed results, known limitations, and the next action for any follow-up agent.

## Failure policy
A failing test, blocked dependency, unavailable service, or ambiguous contract is not permission to fabricate a green result. Preserve the failure evidence and stop only at the smallest unsafe boundary.

## Development-first execution contract

This skill is an implementation skill. It exists to change the product, infrastructure, configuration, or documentation required to make the requested behavior real.

### Mandatory order
1. **Inspect the existing implementation.** Locate the entry point, affected files, current behavior, and related contracts.
2. **Define one concrete production outcome.** Write the behavior that a user or downstream service should observe after the change.
3. **Implement before broad testing.** Make the smallest coherent code/config change that creates the requested behavior. Tests are evidence, not the deliverable.
4. **Run the narrowest verification that proves the behavior.** Prefer one focused test, smoke path, typecheck, build, API call, or UI interaction tied to the changed behavior.
5. **If verification fails, debug the first failure.** Do not rerun the same command more than twice without changing the hypothesis or the implementation.
6. **Verify the real integration.** Replace mocks/placeholders with the real route, state, API, persistence, or native integration whenever the task requires it.
7. **Inspect the diff.** Remove dead code, temporary scaffolding, debug logging, placeholder text, commented-out alternatives, and test-only workarounds.
8. **Report evidence and remaining work.** State exactly what became real, which paths changed, what command proved it, and what remains blocked.

### Anti-loop rules
- Never treat “tests pass” as completion when the requested feature is not implemented.
- Never create a test merely to make progress appear positive.
- Never repeatedly restart the same failing suite without changing code or diagnosis.
- Never replace a required integration with a fake response solely to satisfy a test.
- Never spend the majority of the task on QA while the production implementation is still a stub.
- A test-only change is acceptable only when the user explicitly requested tests or the production behavior is already demonstrably complete.

### Completion gate
A task is **DONE** only when all applicable conditions hold:
- requested production behavior exists;
- primary user path reaches the implemented behavior;
- affected contracts/types/config are updated;
- focused verification passed or a concrete environmental blocker is documented;
- no placeholder implementation remains on the requested path;
- final diff contains no unrelated churn.

### Failure gate
If blocked, record:
- exact blocker;
- command/action that exposed it;
- evidence;
- what was already changed;
- the smallest next unblock action.
Then stop the loop at that boundary. Do not manufacture success.

