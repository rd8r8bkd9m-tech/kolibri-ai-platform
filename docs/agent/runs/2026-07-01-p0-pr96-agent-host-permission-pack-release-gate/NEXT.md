# Next

Owner decision:

- PR #96 can proceed to owner review/mark-ready/merge decision based on updated head `42625cadb2c0d164e2d82598a8a887d5a9a3d1e1`, CI success, and focused server tests.

After authorized merge/deploy/restart, run the post-merge Agent Host canary:

- Submit a read-only/no-push task that requests forbidden permissions: `full_autonomy`, `git_push`, `write_worktree`.
- Expected behavior: Agent Host blocks before runner dispatch with `error_type=permission_contract_violation`, `retry=false`, `status=blocked`, and exact forbidden permission classification.
- Expected non-events: no branch, no commit, no push.

Do not deploy or restart Agent Host until the owner has approved merge/release.
