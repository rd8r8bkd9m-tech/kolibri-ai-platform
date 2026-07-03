# Tests

## Commands Run

```bash
python3 -m py_compile backend/factory_status.py ops/factory_registry.py ops/factory_control.py ops/agent_host.py ops/kolibri-dispatch
/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py tests/test_factory_registry.py tests/test_factory_runtime.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py tests/test_factory_runtime_queue_contracts.py
```

## Result

- `py_compile`: passed.
- Targeted pytest: `43 passed`.
- GitHub Actions `Kolibri CI` passed for initial PR commit `86ae29f`; later pushed commits are awaiting/without reported workflow run at the time of this update.

## Network Registry Fix Suite

- Command: `/tmp/kolibri-p0-venv/bin/python -m py_compile ops/factory_registry.py ops/factory_control.py`
- Result: passed.
- Command: `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_registry.py tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py`
- Result: 22 passed.

## SSH Alias Verification

- Command: sequential command-node SSH check across all 21 canonical server aliases.
- Result: 20 aliases passed by public-key SSH from the command node.
- Failed: `agent-10` only; failure occurs before authentication with `No route to host` / stdio forwarding failure through the `main` jump path.
- Confirmed aliases: `kolibri-home`, `kolibri-main`, `kolibri-qjns`, `kolibri-primary-candidate`, `kolibri-uiap`, `kolibri-9fts`, `kolibri-new`, `reserve242`, `highload`, `agent-01`, `agent-02`, `agent-03`, `agent-04`, `agent-05`, `agent-06`, `agent-07`, `agent-08`, `agent-09`, `paris`, `server-kfrm`.
- Forced canonical key check: `kolibri_ai_platform_deploy_ed25519` authenticates to Home as `ladik` and to 19 other reachable physical servers as `root`.

## Not Run

- Full repository pytest was not run in this sweep.
- Production service restart was not performed.
- GitHub CI was not checked from this branch yet.
- Draft PR push is working through the temporary write deploy key.
