# Tests

Task ID: `P0_PR83_SCOPE_CLEANUP_REMOVE_SUPERFACTORY_OVERLAP_2026_07_01`

Node: `kolibri`

Agent display name: `Автономный инженер`

Focused verification:

- `python3 -m pytest tests/test_agent_host_runner_contract.py -q`

Result:

- Passed: `15 passed in 0.14s`.
- Coverage includes publish-after-verification gate behavior.

Diff verification:

- `git diff --name-status origin/main...HEAD -- docs/superfactory/00_README.md docs/superfactory/20_ROADMAP.md docs/superfactory/TASKS.md`

Expected result:

- No output for the three Superfactory paths, proving the cleanup working tree no longer changes those files relative to `origin/main`.
