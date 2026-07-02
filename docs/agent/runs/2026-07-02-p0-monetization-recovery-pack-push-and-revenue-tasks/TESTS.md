# Tests

Documentation recovery verification:

- `python3 -m json.tool docs/agent/dispatcher/envelopes/P0_REVENUE_LAUNCH_REMOTE_TASKS_2026_07_02.json`
- `test -f` for the recovered revenue package files.
- `test -f` for all exact required run artifacts from the failed monetization task.
- `./ops/kolibri-dispatch status <task_id>` for supervisor-created follow-up task ids.
- `git diff --check` for the staged recovery documentation paths.
- Secret-pattern scan over the staged recovery documentation paths.

No product test suite was run because this recovery changes documentation only.
