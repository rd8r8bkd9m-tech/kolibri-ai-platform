# Plan

Task: P0_CANONICAL_RUN_ARTIFACT_CONTRACT_AND_ALIASES_2026_07_01

1. Realign the worktree to PR #83 branch head `c837e93ee3bf9da3c07b806ebfc003f52b9ad8d5`.
2. Inspect Agent Host runner finalization, publish gate, and existing runner contract tests.
3. Add a canonical run artifact contract for exact `PLAN.md`, `ACTIONS.md`, `TESTS.md`, `RESULT.md`, and `NEXT.md`.
4. Support only explicit deterministic aliases, with alias inspection logged and complete aliases materialized into the canonical directory.
5. Add focused regression tests for exact canonical artifacts, near-miss directory rejection, missing `NEXT.md`, and explicit complete alias finalization.
6. Verify with `python3` and confirm Superfactory docs remain untouched.
