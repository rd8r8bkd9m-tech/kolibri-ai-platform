# Tests

Commands run:

```bash
git fetch origin --prune
```

Result: passed.

```bash
git merge-base --is-ancestor 3416ed1fefea3b399fee3d6f8de55a0ef0f02475 origin/main
```

Result: passed with exit code `0`.

```bash
python3 -m py_compile ops/agent_host.py tests/test_agent_host_runner_contract.py
```

Result: passed.

```bash
python3 -m pytest tests/test_agent_host_runner_contract.py -q
```

Result: `31 passed in 32.73s`.

```bash
python3 -m pytest tests/test_agent_host* -q
```

Result: `44 passed in 42.96s`.

GitHub connector checks:

- `_get_pr_info` for PR #83: `merged=true`, final head `1b2d34fb7d0dd1248457578291b23a2da1855b64`, merge commit `3416ed1fefea3b399fee3d6f8de55a0ef0f02475`.
- `_list_pull_request_review_threads` for PR #83: empty thread list.
- `_fetch_pr_comments` for PR #83: historical validation comments only; no new actionable blocker found.
- `_compare_commits` from merge commit to `main`: `ahead_by=13`, `behind_by=0`.

Limitations:

- `gh` CLI was unavailable in this environment, so GitHub review/thread and PR metadata checks used the GitHub connector.
- Live `kolibri-agent-host.service` restart and canary were not performed from this worktree.
