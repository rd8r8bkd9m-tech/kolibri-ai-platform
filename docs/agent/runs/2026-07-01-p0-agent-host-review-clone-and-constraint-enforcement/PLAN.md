# Agent Host Review Clone And Constraint Enforcement Plan

Task ID: `P0_AGENT_HOST_REVIEW_CLONE_AND_CONSTRAINT_ENFORCEMENT_2026_07_01`

Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`

PR: <https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/83>

## Scope

- Keep changes inside Agent Host runner/review contract code, focused tests, and Agent Host docs.
- Start from PR #83 head `9bebf6cdba32a6886b6343f3701add3e85d18e41`.
- Enforce read-only/no-push constraints before branch publication.
- Ensure missing exact run artifacts cannot be reported as completed.
- Ensure review clone/auth failures leave a concrete `result.json` reference and credential-repair guidance.

## Implementation Steps

1. Fast-forward the local PR #83 branch to `9bebf6cdba32a6886b6343f3701add3e85d18e41`.
2. Add runner permission sanitization for `read_only`, `no_push`, and `git_push_forbidden` envelopes.
3. Extend focused runner contract tests for no-push branch publication, permission stripping, and review clone/auth failure artifacts.
4. Document the tightened contract in `docs/agent/AGENT_RUNNER_CONTRACT.md`.
5. Verify with focused Agent Host suites and branch scope checks.
