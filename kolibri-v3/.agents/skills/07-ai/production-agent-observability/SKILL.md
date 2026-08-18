---
name: production-agent-observability
description: "Добавляет traceable наблюдаемость agent loop: шаги, tools, latency, failures и результат. Use this skill when an agent must implement, modify, or deliver this behavior."
version: 3.0.0
license: MIT
---

# Production Agent Observability

## Purpose
Добавляет traceable наблюдаемость agent loop: шаги, tools, latency, failures и результат.

## When to use
Use for a real production change or a concrete verification of already implemented behavior.

## Inputs
- User requirement and acceptance criteria.
- Existing repository state and relevant source files.
- Runtime evidence when behavior is involved.

## Outputs
- Real implementation or an evidence-backed verification result.
- Exact changed paths and operational evidence.

## Implementation workflow
1. Inspect the real implementation path.
2. State one observable production outcome.
3. Implement the smallest complete vertical slice needed for that outcome.
4. Wire the slice to the real application boundary.
5. Run one focused verification tied directly to the requested behavior.
6. Fix the first failure; do not repeat unchanged attempts.
7. Verify the real path and inspect the final diff.

## Rules
- Product behavior comes before test breadth.
- No mock-only completion when a real integration is required.
- No placeholder or test-only branch on the requested path.
- No unrelated refactor.
- Never claim success without observable evidence.

## Verification
Focused runtime/test/build/API verification appropriate to the changed boundary.

## Done criteria
The requested production outcome exists through the real entry point, and the evidence is recorded.

## Failure handling
Record the first failure, evidence, changed hypothesis, and next action. Stop repeated identical attempts.

## Development-first execution contract
Tests are evidence, not the deliverable. Implement first, integrate second, verify third. If two identical verification attempts fail, change the diagnosis or implementation. If three attempts do not improve the result, mark the task BLOCKED and preserve evidence.

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

