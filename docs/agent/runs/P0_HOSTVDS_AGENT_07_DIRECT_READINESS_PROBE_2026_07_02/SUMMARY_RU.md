# Сводка для владельца

Статус: `readiness_probe_completed_with_blockers`.

Проверка выполнена на рабочем дереве `mesh-agent-07` для задачи `P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02`. Продуктовый код не менялся, push не выполнялся, credential helper не вызывался, секреты и raw auth output не записывались.

Идентичность узла:
- host: `kolibri`
- ожидаемый агент: `hostvds-agent-07 / mesh-agent-07`
- task id: `P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02`
- branch: `agent/P0_HOSTVDS_AGENT_07_DIRECT_READINESS_PROBE_2026_07_02/generic`
- head: `f7ac32c`

Готовность:
- `kolibri-agent-host.service`: `active`, `enabled`
- `kolibri-factory-control.service`: `active`, `enabled`
- `codex`: установлен
- `python3`: установлен
- `curl`: установлен
- диск `/`: всего `99G`, свободно `49G`, занято `48%`

GitHub:
- классификация: `missing`
- причина: `gh` отсутствует на узле; raw auth не проверялся и не печатался.

Control Plane / API:
- рабочий локальный маршрут: `10.99.0.10:9101`
- `/health`, `/v1/health`, `/v1/fabric/health`, `/v1/fabric/routes`, `/v1/fleet/nodes`, `/v1/models`: HTTP `200`
- repo preflight: `factory_control_runtime_preflight=ok`
- `127.0.0.1:9101` не отвечает; это важно для инструментов, которые ожидают localhost.

Блокеры:
- нет GitHub CLI/auth path на узле: `GitHub auth = missing`;
- localhost alias `127.0.0.1:9101` не является рабочим маршрутом Control Plane;
- точная карточка этой direct-readiness задачи не найдена в `docs/agent/dispatcher/QUEUE.md`, поэтому центральная видимость задачи не подтверждена только по repo docs.

Следующая точная задача:

`P0_REPAIR_HOSTVDS_AGENT_07_GITHUB_CLI_AND_LOCAL_CONTROL_ALIAS_2026_07_02`

Цель следующей задачи: восстановить безопасную redacted-классификацию GitHub auth на `hostvds-agent-07 / mesh-agent-07`, закрепить рабочий Control Plane route `10.99.0.10:9101` или починить `127.0.0.1:9101` alias для dispatcher tooling, и подтвердить центральную видимость task card без раскрытия секретов.

