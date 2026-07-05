# Модель событий Kolibri Foundation

## Единый event envelope

- `id` — UUID события
- `stream` — логический поток (`KOLIBRI_EVENTS`, `KOLIBRI_TASKS`, ...)
- `subject` — NATS subject
- `event_type` — тип события (`task.created`, `task.assigned`, ...)
- `aggregate_id` — id связанного объекта
- `payload_json` — payload
- `trace_id` / `correlation_id` — трассировка
- `actor` — кто инициировал
- `created_at` — UTC время

## Предписанные event_type

`node.registered`, `node.heartbeat`, `node.offline`,
`agent.enrolled`, `agent.heartbeat`, `agent.capabilities.updated`, `agent.status.changed`,
`task.created`, `task.assigned`, `task.started`, `task.progress`, `task.completed`, `task.failed`, `task.cancelled`,
`command.started`, `command.stdout`, `command.stderr`, `command.completed`, `command.failed`,
`sandbox.created`, `sandbox.destroyed`, `sandbox.violation`,
`artifact.created`, `artifact.uploaded`,
`policy.evaluated`, `secret.requested`, `secret.denied`, `secret.granted`,
`model.requested`, `model.completed`, `model.failed`,
`audit.recorded`.

## NATS subject mapping

`kolibri.node.*`, `kolibri.agent.*`, `kolibri.task.*`, `kolibri.command.*`,
`kolibri.sandbox.*`, `kolibri.artifact.*`, `kolibri.policy.*`,
`kolibri.secret.*`, `kolibri.model.*`, `kolibri.audit.*`.

## Текущее состояние

На текущий момент событийная модель уже частично реализована в `kolibri-core::events`,
а locald публикует внутренние события в in-memory store и local broadcast.

