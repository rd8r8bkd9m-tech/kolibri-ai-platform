# API Fallback Routing Policy

## Закон маршрутизации

Агент не имеет права отвечать тупиком "server unavailable", пока не проверил доступные API-first маршруты и не вернул structured blocked status.

## Порядок попыток

1. Direct Fabric API route from command node.
2. Primary Control Plane route.
3. Standby Control Plane route.
4. Home relay route.
5. Main relay route.
6. Primary-candidate relay route.
7. Mesh/API relay through any fresh healthy node with required capability.
8. Emergency SSH diagnostic route only for bootstrap/repair classification.

## Причины блокировки

Разрешенные machine-readable причины:

```text
api_unreachable
vpn_down
firewall
disk_full
auth_failed
dns
agent_host_down
control_plane_down
model_unavailable
runner_auth_failed
github_auth_failed
unknown
```

## Fallback response

```json
{
  "status": "blocked",
  "node": "hostvds-agent-10",
  "reason": "api_unreachable",
  "fallback_nodes": ["primorye", "home", "main", "primary-candidate"],
  "can_continue_elsewhere": true,
  "repair_task": "P0_REPAIR_AGENT_10_API_ROUTE",
  "next_action": "Run read-only network and agent-host diagnostic through a reachable relay."
}
```

## Continue elsewhere

Если задача может выполняться на другом узле, API должен вернуть `can_continue_elsewhere=true` и список узлов-кандидатов. Агент обязан продолжить выполнение через fallback node или объяснить, почему capability уникальна и задача реально заблокирована.

## Что считается успехом

- command node получил structured status;
- route_used указан явно;
- fallback_nodes указаны явно;
- artifact paths указаны явно;
- repair_task создан для сломанного узла;
- владелец видит, что работа продолжена или почему продолжение невозможно.

