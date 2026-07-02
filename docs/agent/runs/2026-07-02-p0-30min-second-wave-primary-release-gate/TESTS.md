# Tests

## Passed

```bash
git diff --check
```

Result: passed.

```bash
python3 -m py_compile ops/factory_control.py ops/agent_host.py ops/telegram_gateway.py ops/telegram_superfactory.py backend/factory_status.py backend/main.py
```

Result: passed.

```bash
scripts/preflight-factory-control-runtime.sh
```

Result: `factory_control_runtime_preflight=ok`.

```bash
python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_contracts.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_control_runtime_import_path.py tests/test_fabric_control.py tests/test_factory_control_superfactory.py tests/test_agent_host_runner_contract.py tests/test_agent_host_permission_contract.py tests/test_agent_host_direct_mimo.py tests/test_telegram_gateway.py tests/test_telegram_superfactory_contracts.py tests/test_telegram_superfactory_miniapp.py tests/test_mesh_control_bridge.py tests/test_prompt3_fabric_api_surface.py tests/test_agent_host_telegram_chat.py tests/test_agent_host_image_generation.py
```

Result: `122 passed in 36.36s`.

```bash
node frontend/tests/mobile_layout_guard.mjs
```

Result: `mobile layout guard passed`.

Live Factory Control route probe:

| Route | HTTP | Result |
| --- | ---: | --- |
| `/health` | 200 | pass |
| `/v1/health` | 200 | pass |
| `/v1/fabric/health` | 200 | pass |
| `/v1/fabric/routes` | 200 | pass |
| `/v1/fleet/nodes` | 200 | pass |
| `/v1/models` | 200 | pass |

Service state check:

| Service | ActiveState | SubState |
| --- | --- | --- |
| `kolibri-factory-control.service` | `active` | `running` |
| `kolibri-telegram-gateway.service` | `active` | `running` |

## Blocked By Environment

```bash
python3 -m pytest -q
```

Result: blocked during collection by missing local Python dependencies:

- `pydantic`
- `httpx`

```bash
npm --prefix frontend test -- --runInBand
```

Result: blocked because `frontend/package.json` has no `test` script.

```bash
npm --prefix frontend run build
```

Result: blocked because the worktree has no installed frontend dependencies:
`vite: not found`.
