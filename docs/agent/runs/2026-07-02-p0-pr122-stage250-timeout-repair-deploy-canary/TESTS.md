# Tests

Source and PR evidence:

```bash
git ls-remote https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git refs/pull/125/head refs/pull/125/merge
```

Result:

- `f152e74711ad4f08b71551502ed273885cf4551d refs/pull/125/head`
- `0bda96ca5bb62c375b26bae902fa01558b119e29 refs/pull/125/merge`

```bash
git fetch https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git refs/pull/125/head:refs/remotes/github/pr125/head refs/pull/125/merge:refs/remotes/github/pr125/merge
git diff --name-status origin/main...github/pr125/merge
```

Result: PR #125 merge ref changes `ops/factory_control.py`, `ops/agent_host.py`, `tests/test_factory_capacity_controls.py`, and related run artifacts.

Local source checks:

```bash
python3 -m py_compile ops/factory_control.py ops/agent_host.py
python3 -m py_compile /usr/local/bin/kolibri-factory-control
python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_queue_contracts.py tests/test_agent_host_runner_contract.py
```

Result: `42 passed in 97.17s`.

Live canary:

```bash
POST /v1/tasks/lease with synthetic node pr125-stage250-canary-no-claim
stages: 20, 50, 100, 250 concurrent requests
```

Result: every request returned HTTP `204`, no task ids were claimed, no errors, and no 5xx responses.

Post-canary service checks:

```bash
systemctl show kolibri-factory-control.service --property=ActiveState,SubState,MainPID,LimitNOFILE,TasksMax,NRestarts,Result
journalctl -u kolibri-factory-control.service --since '2026-07-04 05:18:00 UTC' --no-pager | rg -n 'BrokenPipe|Too many open files|Traceback| 500 |ERROR|Errno 24'
```

Result:

- `ActiveState=active`, `SubState=running`, `Result=success`, `NRestarts=0` after the active runtime entered at `2026-07-04 05:18:57 UTC`.
- No matching `BrokenPipe`, `Too many open files`, `Traceback`, `ERROR`, `Errno 24`, or explicit ` 500 ` log lines were found in the canary window.

GitHub CI status:

GitHub REST status/check-run endpoints returned `404` from this unauthenticated node for the private repository, and `gh auth status` reported no logged-in GitHub hosts. This artifact records PR #125 commit evidence and PR-provided remote test evidence, but does not assert a fresh GitHub check-run conclusion.

