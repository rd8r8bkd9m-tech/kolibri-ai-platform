# Plan

Task: `P0_FACTORY_PACKAGE_MANAGER_LAW_AND_GATE_PRIMARY_20260703T101100Z`

1. Inspect existing Agent Host runner contracts and MIMO rollout behavior.
2. Add the canonical package manager law under `docs/superfactory/`.
3. Wire first enforceable Agent Host gates for declared `package_changes` and
   `package_policy` envelopes.
4. Add focused tests for allowed ephemeral packages, denied global/service
   installs, denied package sources, MIMO service constraints, and pre-dispatch
   blocking.
5. Record exact follow-up runtime-enforcement envelope in `NEXT.md`.
6. Run focused checks, commit, and push the feature branch only.
