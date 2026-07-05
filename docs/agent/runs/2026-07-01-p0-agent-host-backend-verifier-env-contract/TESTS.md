# Backend Verifier Env Contract Tests

Task ID: `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01`

Environment:

- Worktree: `/var/lib/kolibri-agent/worktrees/P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01/P0_AGENT_HOST_BACKEND_VERIFIER_ENV_CONTRACT_2026_07_01-attempt-1/repo`
- Branch: `p0/agent-host-runner-contract-hardening-2026-06-30`

Commands run:

```bash
python3 -m pytest tests/test_agent_host_runner_contract.py -q
```

Result: passed, `28 passed in 40.69s`.

Final rerun after adding the five run artifacts: passed,
`28 passed in 36.62s`.

```bash
python3 -m compileall -q ops/agent_host.py
```

Result: passed.

```bash
python3 -m pytest tests/test_agent_host_runner_contract.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py -q
```

Result: passed, `34 passed in 38.65s`.

Acceptance coverage:

- Existing no-push, read-only, write-scope, publish-gate, and canonical artifact
  tests are included in `tests/test_agent_host_runner_contract.py`.
- The combined Agent Host suite also re-ran telegram chat and image generation
  tests.
