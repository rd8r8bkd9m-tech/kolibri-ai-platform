# Tests

Verification performed:

- `git fetch origin --prune` passed.
- GitHub connector open PR query passed for repository `rd8r8bkd9m-tech/kolibri-ai-platform`.
- GitHub connector workflow-run checks passed for PR heads #105 through #113.
- GitHub connector comment writes passed for PRs #105 through #113.
- GitHub connector label writes passed for PRs #105 through #113.

Current-head CI evidence:

- #105: Kolibri CI `28561507486` success.
- #106: Kolibri CI `28561763736` success.
- #107: Kolibri CI `28561768604` success.
- #108: Kolibri CI `28561773184` success.
- #109: Kolibri CI `28561778515` success.
- #110: Kolibri CI `28561783263` success.
- #111: Kolibri CI `28561789265` success.
- #112: Kolibri CI `28561794180` success.
- #113: Kolibri CI `28561798865` success.

Local artifact checks:

- `git diff --check`: passed.
- `python3 -m pytest tests/test_factory_runtime.py tests/test_factory_control_runtime_import_path.py tests/test_factory_status.py tests/test_fabric_control.py -q`: blocked during collection because system Python is missing `httpx`, imported by `backend/factory_status.py`.
- `.venv/bin/python` check: no executable project virtualenv in this worktree.
- `python3 -m pytest tests/test_factory_runtime.py tests/test_factory_control_runtime_import_path.py tests/test_fabric_control.py -q`: `15 passed in 0.43s`.
