# Backend Verifier Env Contract Plan

Task ID: `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01`

Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`

Plan:

1. Inspect the existing PR #83 Agent Host runner contract implementation and focused tests.
2. Add an explicit opt-in backend Python verification environment contract.
3. Wire declared backend envs into backend/review verifier commands without changing default raw verifier behavior.
4. Prove raw Python missing backend deps can pass through a declared backend env.
5. Prove temp env cleanup/exclusion and setup-failure classification.
6. Verify focused Agent Host contract suites and record exact artifacts.
