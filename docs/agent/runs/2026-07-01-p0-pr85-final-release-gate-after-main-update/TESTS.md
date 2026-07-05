# Tests

Remote successful checks:

```bash
python3 -m pytest tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py -q
```

Result:

- `11 passed in 0.13s`

Remote structural checks:

- `refs/pull/85/head` -> `30b7e5d`.
- `refs/pull/85/merge` -> `10963ce7`.
- `git merge-tree origin/main HEAD` exited `0`.
- `origin/main` is ancestor of PR head.
- Final worktree clean and restored to `agent/P0_PR85_FINAL_RELEASE_GATE_AFTER_MAIN_UPDATE_2026_07_01/generic...origin/main`.

Wrapper failure:

The generic runner later executed the focused pytest command on the restored base branch, where `tests/test_fabric_control.py` was absent, producing rc=4. This is a runner sequencing/verifier issue, not evidence that PR #85 tests failed.

Command-node GitHub evidence:

- PR #85 CI: success.
- Mergeable: true.
- Mergeable state: clean.
