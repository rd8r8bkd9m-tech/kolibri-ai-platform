# Actions

- Added `ops/github_release_train_bot.py`.
- Added `tests/test_github_release_train_bot.py`.
- Implemented `origin/main` freshness enforcement by comparing local
  `origin/main` with remote `refs/heads/main`.
- Implemented conservative PR classification states:
  `blocked_main_freshness`, `repair_required`, `waiting_for_ci`,
  `blocked_mergeability`, `owner_review_ready_draft`,
  `owner_approval_required`, and `release_ready_owner_merge_only`.
- Implemented idempotent PR body release-train block rendering between
  `<!-- kolibri-release-train:start -->` and
  `<!-- kolibri-release-train:end -->`.
- Implemented repair task payloads for failing PRs with explicit forbidden
  actions: no secret printing, no force push, no push to main, no merge without
  owner approval.
- Implemented dry-run default and explicit `--apply` mutation mode.
- Verified that live PR metadata mutation is blocked on this node because
  `gh` is not installed.

