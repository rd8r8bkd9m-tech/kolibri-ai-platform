# Tests

Remote and dispatcher checks:

```text
ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_DEPLOY_FACTORY_CONTROL_AND_TELEGRAM_GATEWAY_CANARY_REPAIR_2026_07_02.json
ops/kolibri-dispatch status P0_DEPLOY_FACTORY_CONTROL_AND_TELEGRAM_GATEWAY_CANARY_REPAIR_2026_07_02
systemctl show kolibri-factory-control.service -p LoadState -p ActiveState -p SubState -p MainPID -p ExecMainStatus --no-pager
curl --noproxy '*' --max-time 3 http://10.99.0.10:9101/health
curl --noproxy '*' --max-time 3 http://10.99.0.10:9101/v1/health
curl --noproxy '*' --max-time 3 http://10.99.0.10:9101/v1/fabric/health
curl --noproxy '*' --max-time 3 http://10.99.0.10:9101/v1/fabric/routes
curl --noproxy '*' --max-time 3 http://10.99.0.10:9101/v1/fleet/nodes
curl --noproxy '*' --max-time 3 http://10.99.0.10:9101/v1/models
systemctl is-active kolibri-factory-control.service kolibri-agent-host.service kolibri-mesh-control-bridge.service kolibri-telegram-gateway.service
```

Result after rollback:

- `kolibri-factory-control.service`: `active/running`.
- `kolibri-agent-host.service`: `active`.
- `kolibri-mesh-control-bridge.service`: `active`.
- `kolibri-telegram-gateway.service`: `inactive` on the probed node.
- `http://10.99.0.10:9101/health`: HTTP `200`.
- `http://10.99.0.10:9101/v1/health`: HTTP `200`.
- `/v1/fabric/health`, `/v1/fabric/routes`, `/v1/fleet/nodes`,
  `/v1/models`: HTTP `404` after rollback to the old runtime entrypoint.

