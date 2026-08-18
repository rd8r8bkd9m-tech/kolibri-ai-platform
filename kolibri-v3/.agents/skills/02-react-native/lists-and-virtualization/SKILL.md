---
name: lists-and-virtualization
description: "Kolibri V3 skill. Build performant FlatList/SectionList/virtualized interfaces for large datasets. Use when the task matches this capability."
version: 2.0.0
license: MIT
---

# Lists And Virtualization

## Mission
Build performant FlatList/SectionList/virtualized interfaces for large datasets.

## Trigger
Use this skill when the task explicitly or implicitly requires this capability. Do not load it for unrelated work.

## Non-goals
- Do not redesign unrelated modules.
- Do not invent missing contracts, credentials, production state, prices, or runtime facts.
- Do not bypass repository gates to make a task appear complete.

## Inputs
- User requirement and acceptance criteria.
- Current repository state, diffs, tests, and configuration.
- Applicable upstream documentation as source of truth for framework behavior.

## Operating procedure
1. Inspect the existing implementation and identify the smallest affected surface.
2. Resolve applicable contracts, invariants, and compatibility constraints before editing.
3. Load only the references needed for the current decision.
4. Implement the smallest coherent change.
5. Run targeted verification closest to the changed behavior.
6. Run broader gates proportional to risk and changed surface.
7. Inspect the final diff for accidental scope expansion.
8. Record evidence and remaining limitations.

## Decision rules
- Prefer existing project conventions over introducing another abstraction.
- Prefer deterministic code for calculations, permissions, migrations, and release gates.
- Prefer explicit failure states over silent fallback.
- Treat external data and model output as untrusted input.
- Preserve backward compatibility unless the task explicitly permits a breaking change.

## Verification
- Syntax/type validation where applicable.
- Targeted unit/integration/e2e checks.
- Build or platform validation when relevant.
- Regression check for adjacent behavior.

## Evidence contract
Return: changed files, key decisions, commands/tests executed, pass/fail results, unresolved issues, and rollback notes when risk is material.

## Failure handling
Stop at the smallest safe boundary. Report the exact blocker, observed evidence, attempted remediation, and the next actionable step. Never fabricate success.

## Handoff contract
When another agent continues: provide assumptions, affected paths, interfaces changed, tests already run, known failures, and explicit next action.

## Security
Never print or commit secrets, tokens, cookies, private keys, or personal data. Redact sensitive values in diagnostics.

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

