# Tests

Environment:

- Python: `/Users/kolibri/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`
- Version: Python 3.12.13
- Temporary venv: `/tmp/kolibri-p0-runner-contract-py312-venv`

Commands run:

```bash
/Users/kolibri/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m venv /tmp/kolibri-p0-runner-contract-py312-venv
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pip install pytest -r backend/requirements.txt
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m py_compile ops/agent_host.py
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pytest tests/test_agent_host_runner_contract.py -q
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pytest tests/test_agent_host* -q
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pytest tests/test_factory_runtime.py -q
/tmp/kolibri-p0-runner-contract-py312-venv/bin/python -m pytest -q
```

Results:

- `tests/test_agent_host_runner_contract.py`: 13 passed.
- `tests/test_agent_host*`: 19 passed.
- `tests/test_factory_runtime.py`: 4 passed.
- Full suite: 73 passed, 1 warning.

Test classification:

| Test or check | Classification | Result |
| --- | --- | --- |
| `py_compile ops/agent_host.py` on Mac with Python 3.12.13 | `passed_local_mac` | Passed |
| `pytest tests/test_agent_host_runner_contract.py -q` on Mac with Python 3.12.13 | `passed_local_mac` | 13 passed |
| `pytest tests/test_agent_host* -q` on Mac with Python 3.12.13 | `passed_local_mac` | 19 passed |
| `pytest tests/test_factory_runtime.py -q` on Mac with Python 3.12.13 | `passed_local_mac` | 4 passed |
| `pytest -q` on Mac with Python 3.12.13 | `passed_local_mac` | 73 passed, 1 external warning |
| `pytest -q` on Mac with Homebrew Python 3.14 | `blocked_missing_dependency` | `pydantic-core==2.23.2` cannot build because its PyO3 dependency supports up to Python 3.13 |
| GitHub Actions `Kolibri CI / ci` | `deferred_to_ci` | Completed successfully |
| Remote full suite on `217.60.63.31` | `deferred_to_server` | Completed successfully |
| Control Plane rerun of P0 integration audit | `not_run_with_reason` | Intentionally left for next supervised task after PR merge/deploy |
| Production/runtime repo mutation tests | `not_run_with_reason` | Forbidden by task scope |
| Prompt 19 docs addendum | `passed_local_mac` | `git diff --check` passed; no product code changed |

Remote server validation of code behavior:

- Host: `server-kfrm`
- IP: `217.60.63.31`
- User: `root`
- Commit tested: `67a57ea345e03db4989b56b29e9a7bf9ac65eeec`
- Test checkout: `/var/tmp/kolibri-pr83-67a57ea3`
- Source transfer: `git archive HEAD` from the already pushed PR branch,
  extracted into the temporary server checkout.
- Python: 3.12.3
- Remote results:
  - `tests/test_agent_host_runner_contract.py`: 13 passed.
  - `tests/test_agent_host*`: 19 passed.
  - `tests/test_factory_runtime.py`: 4 passed.
  - Full suite: 73 passed, 1 warning.

GitHub validation:

- PR: <https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/83>
- Workflow run: <https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28472388420>
- Result: `Kolibri CI / ci` succeeded for commit
  `67a57ea345e03db4989b56b29e9a7bf9ac65eeec`.

Notes:

- Finalization rerun on 2026-07-01 in the Control Plane worktree used
  `/usr/bin/python3` version 3.12.3 to create `.venv-p0-runner-contract`, then
  ran the checks through `.venv-p0-runner-contract/bin/python`. The bootstrap
  command was `python3 -m venv .venv-p0-runner-contract`; no `python` verifier
  was used.
- Current finalization results:
  - `py_compile ops/agent_host.py`: passed.
  - `pytest tests/test_agent_host_runner_contract.py -q`: 13 passed.
  - `pytest tests/test_agent_host* -q`: 19 passed.
  - `pytest tests/test_factory_runtime.py -q`: 4 passed.
  - `pytest -q`: 73 passed, 1 external `reportlab` warning.
- `git ls-remote --heads origin p0/agent-host-runner-contract-hardening-2026-06-30`
  confirmed that the GitHub source branch was reachable before the final
  artifact update was pushed.
- `gh` was not installed in this worktree environment, so PR metadata was not
  queried through GitHub CLI during the finalization rerun.
- A first full-suite attempt on the Homebrew default Python 3.14 failed during
  dependency installation because pinned `pydantic-core==2.23.2` depends on a
  PyO3 version that supports up to Python 3.13. The successful full run used
  Python 3.12.13, matching the CI workflow family.
- The one full-suite warning is from `reportlab` using deprecated
  `ast.NameConstant`; it is external to this change.
- `217.60.63.31` did not have `git` or `gh` installed, so the server test used
  a temporary archive checkout instead of modifying or depending on a production
  runtime repository.
- This follow-up only adds documentation examples and test classification; it
  does not change product code or runner behavior. GitHub CI validates each PR
  head after push.
- Prompt 19 addendum files are documentation-only. No server mutation or heavy
  remote rerun is required specifically for those files; GitHub CI validates the
  pushed PR head.
