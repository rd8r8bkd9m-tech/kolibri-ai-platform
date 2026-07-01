# Plan

Task: `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30`

Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`

## Scope

- Harden `ops/agent_host.py` runner completion behavior.
- Add focused tests for no-push, read-only, product-code, docs-only, write
  scope, required artifacts, unsupported task kinds, artifact path drift, and
  result schema.
- Add the durable runner contract document.
- Do not change frontend, billing, FormulaLM, Telegram UX, server credentials,
  mesh extraction, PR split work, or production runtime repos.

## Steps

1. Read Agent Host, Control Plane, dispatcher, tests, CI, and global
   intelligence context.
2. Add a runner contract finalizer in Agent Host.
3. Replace direct implementation-runner `git push` calls with a no-push-aware
   wrapper.
4. Convert unsupported kind/capability handling to structured blocked results.
5. Add contract tests.
6. Run targeted and full tests in a Python 3.12 environment.
7. Write run artifacts and final report.
