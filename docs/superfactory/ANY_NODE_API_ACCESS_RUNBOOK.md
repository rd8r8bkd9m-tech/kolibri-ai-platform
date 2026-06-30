# Any-Node API Access Runbook

## Цель

С любого доверенного command node владелец должен управлять фабрикой через один API-контракт, а не помнить SSH jump routes.

## Быстрая проверка command node

1. Проверить локальную идентичность command node.
2. Получить short-lived owner/admin token.
3. Выполнить:

```text
GET /v1/health
GET /v1/fleet/nodes
GET /v1/fleet/topology
GET /v1/fleet/capabilities
GET /v1/models
```

4. Если direct route не работает, запросить:

```text
GET /v1/fleet/route
```

5. Если маршрут недоступен, вернуть structured blocked response и repair task.

## Постановка задачи

Все задачи создаются через:

```text
POST /v1/agents/tasks
```

Минимальный request:

```json
{
  "task_id": "string",
  "trace_id": "string",
  "owner": "Vladislav",
  "source": "mac",
  "command_node": "macbook-air-vladislav",
  "requested_role": "owner_root",
  "target_node": "auto",
  "fallback_allowed": true,
  "write_scope": [],
  "constraints": {
    "secrets_redaction_required": true
  }
}
```

## Получение результата

```text
GET /v1/agents/status/{task_id}
GET /v1/agents/artifacts/{task_id}
```

Ответ должен включать `route_used`, `fallback_nodes`, `blocked_reason`, `repair_task`, `next_action`.

## Admin actions

Admin endpoint-ы используются только через owner_root или scoped delegation:

```text
POST /v1/admin/exec
POST /v1/admin/service
POST /v1/admin/git
POST /v1/admin/bootstrap-node
POST /v1/admin/rotate-keys
```

Перед admin action API обязан проверить:

- authorization;
- write_scope;
- constraints;
- reversibility;
- secrets redaction;
- audit log destination.

## SSH break-glass

SSH можно использовать только если API route не отвечает или нужно bootstrap-ить новый узел. После SSH-диагностики агент обязан записать repair task, чтобы штатное управление вернулось в API.

