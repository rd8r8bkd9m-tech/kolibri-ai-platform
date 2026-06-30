# API-First Control Fabric

## Назначение

Kolibri Factory управляется через единый защищенный API. SSH не является основным рабочим способом управления фабрикой и разрешен только для bootstrap, аварийного восстановления и диагностики.

Главный маршрут управления:

```text
command node
  -> Kolibri Fabric API
  -> Control Plane
  -> Agent Host
  -> remote agents / MIMO / API agents / local LLM / tools
  -> artifacts
  -> GitHub / owner report
```

Command node может быть Mac, Primorye, Home, main, primary-candidate, Telegram, phone или другой доверенный компьютер. С любого command node владелец должен видеть одну и ту же картину фабрики: серверы, агенты, модели, задачи, статусы, артефакты, возможности и маршруты fallback.

## Основное правило

Агент никогда не завершает работу фразой "server unavailable" как тупиком. Если прямой маршрут не сработал, агент обязан использовать API relay или fallback route, классифицировать причину и вернуть структурированный статус с repair task.

## Обязательные API endpoint-ы

```text
GET  /v1/health
GET  /v1/fleet/nodes
GET  /v1/fleet/topology
GET  /v1/fleet/route
GET  /v1/fleet/capabilities
GET  /v1/models
POST /v1/responses
POST /v1/chat/completions
POST /v1/agents/tasks
GET  /v1/agents/status/{task_id}
GET  /v1/agents/artifacts/{task_id}
POST /v1/agents/cancel/{task_id}
POST /v1/admin/exec
POST /v1/admin/service
POST /v1/admin/git
POST /v1/admin/bootstrap-node
POST /v1/admin/rotate-keys
```

## Единый request envelope

Каждый запрос, который меняет состояние, запускает работу или читает защищенные данные, должен иметь общий envelope:

```json
{
  "task_id": "string",
  "trace_id": "string",
  "owner": "Vladislav",
  "source": "mac|primorye|home|telegram|main|primary-candidate|github",
  "command_node": "string",
  "requested_role": "owner_root|command_node|control_plane|agent_host|remote_agent|model_node|review_agent|qa_agent|observer",
  "target_node": "string",
  "fallback_allowed": true,
  "write_scope": [],
  "constraints": {}
}
```

## Единый response envelope

Каждый ответ Fabric API должен быть пригоден для ChatGPT, Telegram, CLI, PWA и GitHub artifact:

```json
{
  "task_id": "string",
  "trace_id": "string",
  "status": "completed|running|blocked|failed|partial",
  "node": "string",
  "route_used": "string",
  "fallback_nodes": [],
  "artifacts": [],
  "blocked_reason": "string",
  "repair_task": "string",
  "next_action": "string"
}
```

## Ответ при недоступном узле

Недоступность одного узла не останавливает фабрику:

```json
{
  "status": "blocked",
  "node": "string",
  "reason": "api_unreachable|vpn_down|firewall|disk_full|auth_failed|dns|unknown",
  "fallback_nodes": ["primorye", "home", "main", "primary-candidate"],
  "can_continue_elsewhere": true,
  "repair_task": "string"
}
```

## SSH

SSH используется только как:

- bootstrap нового узла;
- аварийное восстановление API/mesh;
- диагностика сети, диска, systemd и ключей;
- временный break-glass маршрут с обязательным отчетом.

Любое штатное действие фабрики должно иметь API-аналог и task_id.

