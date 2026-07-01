# Tests

Commands run:

```bash
git fetch origin main --prune
git rev-parse HEAD
git rev-parse origin/main
git rev-parse FETCH_HEAD
```

Result:

- `HEAD`: `c97a0f50e14e3c2c20babfd13fbeb045400f66f2`
- `origin/main`: `c97a0f50e14e3c2c20babfd13fbeb045400f66f2`
- `FETCH_HEAD`: `c97a0f50e14e3c2c20babfd13fbeb045400f66f2`

Focused canary suite:

```bash
python3 -m pytest \
  tests/test_agent_host_runner_contract.py \
  tests/test_agent_host_permission_contract.py \
  tests/test_agent_host_direct_mimo.py \
  tests/test_fabric_control.py \
  tests/test_prompt3_fabric_api_surface.py \
  tests/test_telegram_gateway.py \
  tests/test_factory_runtime_queue_contracts.py
```

Result: `89 passed in 40.05s`.

Collection blocker observed:

```bash
python3 -m pytest tests/test_factory_status.py backend/tests/test_factory_status_fast_health.py
```

Result: collection blocked because this node's Python environment lacks `httpx`.

```text
ModuleNotFoundError: No module named 'httpx'
```

Live service probes:

```bash
systemctl is-active kolibri-agent-host.service kolibri-factory-control.service kolibri-telegram-gateway.service kolibri-mesh-control-bridge.service
```

Result:

```text
active
active
inactive
active
```

Factory Control health:

```bash
curl --noproxy '*' -fsS --max-time 2 http://10.99.0.10:9101/health
```

Result summary: `status=ok`, `redis=PONG`, `spool_count=0`, `spool_replayed=0`, `time=2026-07-01T21:07:56.908979+00:00`.

Fabric path probes:

```bash
curl --noproxy '*' -fsS --max-time 2 http://10.99.0.10:9101/v1/fabric/health
curl --noproxy '*' -fsS --max-time 2 http://10.99.0.10:9101/v1/fleet
curl --noproxy '*' -fsS --max-time 2 http://10.99.0.10:9101/v1/status
```

Result: all returned HTTP `404`.

GitHub queue visibility:

```bash
git ls-remote --heads origin main
git ls-remote origin 'refs/pull/*/head' | wc -l
for pr in 83 85 89 91 92 96 97 98; do git ls-remote origin "refs/pull/$pr/head"; done
```

Result:

- `main`: `c97a0f50e14e3c2c20babfd13fbeb045400f66f2`
- Pull refs visible: `68`
- Known refs visible for #83, #85, #89, #91, #92, #96, #97, and #98.

