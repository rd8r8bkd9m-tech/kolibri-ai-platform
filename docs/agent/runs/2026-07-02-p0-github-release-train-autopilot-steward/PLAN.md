# Plan

Task: `P0_GITHUB_RELEASE_TRAIN_AUTOPILOT_STEWARD_2026_07_02`

1. Confirm execution is on the server Agent Host environment, not a Mac.
2. Inspect current remote branches and open PR state without printing secrets.
3. Ensure code-bearing remote branches have draft PR coverage.
4. Classify PR #105 repair state, PR #90, runner/fleet PRs, and the remaining release queue.
5. Record blockers, artifacts, and the next merge/repair order without merging to `main`.

Mutation limits:

- No push to `main`.
- No force push.
- No destructive git operation.
- No PR marked ready.
- No merge.
- GitHub writes limited to creating draft PRs for existing remote code branches.
