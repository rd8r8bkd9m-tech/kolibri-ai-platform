---
name: assistant-action-execution
description: "Подключает действия ассистента к реальным application commands. Use this skill when an agent must implement, modify, or deliver this behavior."
version: 3.0.0
license: MIT
---

# Assistant Action Execution

## Purpose
Подключает действия ассистента к реальным application commands.

## When to use
Use when the task requires a real product change in this area. Do not use this skill as a substitute for implementation.

## Inputs
- User requirement and acceptance criteria.
- Existing repository state.
- Relevant source code, contracts, configuration and runtime evidence.

## Outputs
- Production code/configuration changes.
- Updated contracts or documentation when required.
- Verification evidence.

## Implementation workflow
1. Inspect the existing path end-to-end.
2. Identify the smallest vertical slice that can produce a real user-visible or service-visible result.
3. Implement the slice completely, including wiring, state/data flow and failure states.
4. Integrate with existing project conventions rather than creating parallel infrastructure.
5. Run the narrowest check that proves the new behavior.
6. Fix the first failure at its root cause.
7. Exercise the real integration path when mocks would hide defects.
8. Inspect the final diff for placeholders and accidental churn.

## Rules
- Production behavior is the deliverable; tests are verification.
- Prefer real integration over mock-only completion.
- Preserve working behavior outside the requested scope.
- Do not add dependencies without a concrete need and compatibility check.
- Do not silently change API contracts.
- Do not claim completion from lint/typecheck alone when runtime behavior is required.

## Verification
- Focused verification first.
- Typecheck/build when affected.
- E2E or runtime verification when the change is user-facing.
- Inspect changed files and relevant logs.

## Done criteria
The requested behavior works through its real entry point and no placeholder remains on the affected path.

## Failure handling
Stop repeated identical attempts. Capture the first failure, root-cause hypothesis, changed paths, and smallest next action.

## Development-first execution contract

This skill is an implementation skill. Its purpose is to create or change real product behavior, infrastructure, configuration, or required operational documentation. Tests are evidence, not the deliverable.

### Mandatory order
1. Inspect the existing implementation and identify the real entry point.
2. State one observable production outcome.
3. Implement the smallest complete vertical slice that produces that outcome.
4. Integrate it with the real state, API, domain, persistence, or native boundary as applicable.
5. Run the narrowest verification that directly proves the behavior.
6. On failure, diagnose the first failure and change either the hypothesis or implementation before retrying.
7. Exercise the real path; remove mocks/placeholders on the requested path.
8. Inspect the final diff and handoff evidence.

### Anti-loop rules
- Never treat green tests as completion when production behavior is still absent.
- Never add or loosen tests merely to manufacture progress.
- Never repeat an identical failing command more than twice without a changed hypothesis or code/configuration.
- Never replace required integration with a fake response or test-only branch.
- If three attempts do not materially improve the outcome, enter BLOCKED/root-cause mode instead of looping.

### Completion gate
DONE means the requested production behavior exists through the real entry point, affected contracts/configuration are wired, focused verification provides evidence, and no placeholder remains on the requested path.

### Failure gate
Record the exact blocker, evidence, changed paths, attempted fixes, and the smallest next unblock action. Do not fabricate success.

