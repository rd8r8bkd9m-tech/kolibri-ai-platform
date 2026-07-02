# Next

Immediate next action:

Run CI/check-run inspection for draft PRs #105, #106, #107, #108, #109, #110, #111, #112, and #113 from a node with `gh` or a check-run-capable GitHub API tool, then start owner review with #113.

Repair tasks to dispatch:

1. `P0_PR105_ROUTE_FRESHNESS_CI_REPAIR_2026_07_02`
   - Current remote branch is empty at `origin/main`.
   - Decide whether #105 already contains the intended repair or dispatch an actual repair commit.
2. `P0_PR90_TELEGRAM_MINIAPP_AUTH_PYTEST_IMPORT_COLLISION_REPAIR_2026_07_02`
   - Current remote branch is empty at `origin/main`.
   - Dispatch an actual repair for the verifier import/dependency collision or document why #90 is acceptable as-is.

Owner gate:

- Do not mark any draft PR ready or merge until the CI/check evidence and focused review artifacts exist.
