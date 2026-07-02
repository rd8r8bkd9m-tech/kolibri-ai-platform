# Actions

Implemented:
- Added `classify_backlog_task`, `backlog_policy`, and `backlog_audit_snapshot` in `ops/factory_control.py`.
- Added safe action taxonomy: `requeue_now`, `requeue_after_github_clone_repair`, `cancel`, `supersede`, `wait`, `blocked`, `noop`.
- Added GitHub clone repair detection for `review_clone_auth_failed`, `git_clone_auth_failed`, `missing_node_github_credential`, `github_auth_failed`, and matching redacted error/result text.
- Added `GET /v1/tasks/backlog/audit` as a non-mutating control-plane endpoint.
- Added `./ops/kolibri-dispatch backlog-audit`.
- Added tests for clone-repair retry classification, useful-artifact supersede classification, and expired lease debt requeue/block decisions.

Live probe:
- Command: `./ops/kolibri-dispatch backlog-audit`
- Result: HTTP 404 from current deployed control plane because it does not yet contain this branch's route and treated `backlog/audit` as task ID.
- Classification: deployment/version blocker, not a missing implementation artifact.
