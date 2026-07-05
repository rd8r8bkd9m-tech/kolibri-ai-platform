# Enrollment и heartbeat агентов

## Регистрация агентов

- `POST /v1/agents/enroll`
  - `id?` optional
  - `node_id`, `name`, `kind`, `version`, `capabilities`

## Heartbeat

- `POST /v1/agents/heartbeat`
  - Обновляет `last_heartbeat_at`, статус, capabilities, current_task.

## Логику маршрутизации

- `locald` выбирает свободный online агент с нужной capability,
- пишет события `agent.heartbeat`, `agent.enrolled`, `task.assigned`.

