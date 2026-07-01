# Tests

Task: P0_CANONICAL_RUN_ARTIFACT_CONTRACT_AND_ALIASES_2026_07_01

Commands run:

```bash
python3 -m pytest tests/test_agent_host_runner_contract.py -q
```

Result: passed, `19 passed in 0.19s`.
Final rerun after adding the canonical publish-gate regression: passed,
`20 passed in 0.22s`.

```bash
python3 -m pytest tests/test_agent_host_runner_contract.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py -q
```

Result: passed, `25 passed in 2.17s`.
Final rerun after adding the canonical publish-gate regression: passed,
`26 passed in 2.20s`.

```bash
python3 -m compileall -q ops/agent_host.py
```

Result: passed.

```bash
git diff -- docs/superfactory/00_README.md docs/superfactory/20_ROADMAP.md docs/superfactory/TASKS.md
```

Result: no diff.
