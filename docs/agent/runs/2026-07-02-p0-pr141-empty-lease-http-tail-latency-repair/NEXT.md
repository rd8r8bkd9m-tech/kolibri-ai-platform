# NEXT

- Push this focused repair branch/commit to the PR #141 stack target.
- Run CI for the updated branch.
- After owner approval, deploy through the protected release process only.
- Rerun strict live canary against the deployed runtime and compare stage250/stage500 empty-poll status0 counts.
- If status0 remains, inspect socket accept backlog, client timeout, and worker pool saturation with runtime metrics before adding broader server changes.
