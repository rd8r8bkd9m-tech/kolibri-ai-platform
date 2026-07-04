# Telegram Sample Messages

Unavailable:

```text
⚠️ Kolibri Lease Watchdog

Статус: не удалось проверить очередь.
Причина: Control Plane недоступен.

Пробовал:
- http://10.99.0.2:9101 — timed out (4000 ms)
- http://10.99.0.10:9101 — timed out (4000 ms)

Что это значит:
Значения Redis/Tasks/Leases не проверены. Это не нули.

Next:
repair_task: P0_REPAIR_CONTROL_PLANE_API_AND_AUTHORITY_FAILOVER_20260704
```

Success:

```text
✅ Kolibri Lease Watchdog

Control Plane: http://10.99.0.1:9101
Redis: PONG
Queue: 100
Expired leases: 0
Stuck heartbeat: не проверено

Action:
No urgent action.
```
