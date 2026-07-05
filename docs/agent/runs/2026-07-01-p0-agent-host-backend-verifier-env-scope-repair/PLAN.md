# Backend Verifier Env Scope Repair Plan

Task ID: `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01`

Objective:

Repair the Control Plane verifier/scope mismatch for PR #83 without changing
runtime code unless verification proves a minimal server-side adjustment is
needed.

Plan:

1. Confirm the PR #83 branch head is at or beyond the useful failed result
   `4b8d2a9f431034963945ffc929a7c19e3c7ff640`.
2. Verify the branch diff from original base `23e8e43` is covered by the
   corrected allowlist:
   - `.gitignore`
   - `docs/agent/AGENT_RUNNER_CONTRACT.md`
   - `ops/agent_host.py`
   - `tests/test_agent_host_runner_contract.py`
   - `docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-contract/**`
   - `docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-scope-repair/**`
3. Run the focused runner contract tests.
4. Record the exact five repair artifacts under this directory.
5. Do not push unless a minimal server-side adjustment is needed.
