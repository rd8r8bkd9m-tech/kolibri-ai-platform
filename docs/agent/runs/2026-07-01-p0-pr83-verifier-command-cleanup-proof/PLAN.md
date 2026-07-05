# PR #83 Verifier Command Cleanup Proof Plan

Task ID: `P0_PR83_VERIFIER_COMMAND_CLEANUP_PROOF_2026_07_01`
Node: `kolibri`
Agent display name: `Автономный инженер`
Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`
PR: `#83`

## Scope

Prove the current Agent Host runner contract branch from PR #83 head
`8951a9feb4a44b8dd87a762d0da199257de1dae0` with corrected verifier commands.

## Steps

1. Confirm the worktree is at PR #83 head `8951a9feb4a44b8dd87a762d0da199257de1dae0` or a fast-forward successor.
2. Run the focused runner contract suite with `python3`.
3. Run the relevant Agent Host suite with `python3` using only existing test files.
4. Compile `ops/agent_host.py` with `python3`.
5. Run `git diff --check`.
6. Confirm PR #83 still has no overlap with:
   - `docs/superfactory/00_README.md`
   - `docs/superfactory/20_ROADMAP.md`
   - `docs/superfactory/TASKS.md`
7. Publish only this docs proof if all checks pass.
