# Tests

Verification commands run:

```bash
hostname && uname -a
git status --short --branch
git branch -r --format='%(refname:short)' | sort
git rev-parse origin/agent/P0_PR105_ROUTE_FRESHNESS_CI_REPAIR_2026_07_02/generic origin/agent/P0_PR90_TELEGRAM_MINIAPP_AUTH_PYTEST_IMPORT_COLLISION_REPAIR_2026_07_02/generic origin/main
git diff --name-status origin/main...origin/agent/P0_PR105_ROUTE_FRESHNESS_CI_REPAIR_2026_07_02/generic
git diff --name-status origin/main...origin/agent/P0_PR90_TELEGRAM_MINIAPP_AUTH_PYTEST_IMPORT_COLLISION_REPAIR_2026_07_02/generic
```

GitHub connector checks:

- `_search_prs` for open PR inventory.
- `_get_pr_info` for #83, #85, #88, #89, #90, #91, #92, #96, #97, #105, and #106-#113.
- `_list_pr_changed_filenames` for #90 and #105.
- `_get_commit_combined_status` for inspected active heads.
- `_create_pull_request` for #106-#113 as draft PRs only.

Limitations:

- `gh` CLI is not installed on this server runtime, so GitHub Actions run-log inspection was not available.
- The GitHub connector combined-status endpoint returned empty legacy status context lists for active heads. This does not prove Actions passed; it means this steward run could not observe check-run conclusions through that endpoint.
