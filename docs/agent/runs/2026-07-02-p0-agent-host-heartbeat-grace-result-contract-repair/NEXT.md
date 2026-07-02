# Next

Recommended next step:

- Open or update a PR for branch
  `p0/agent-host-heartbeat-grace-2026-07-02`.

Suggested PR validation:

```text
python3 -m pytest -q tests/test_agent_host_runner_contract.py
git diff --check
```

Deferred by instruction:

- Runtime canaries.
- Any Control Plane runtime mutation or service restart.
