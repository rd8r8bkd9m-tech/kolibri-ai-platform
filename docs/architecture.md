# Архитектура Kolibri Control Station Foundation

> Версия: 2026-07-05

## Цель

Kolibri Control Station — это не чатовый дашборд, а локальная операционная станция для управления AI-кластером:

- узлами и агентами;
- задачами и очередями;
- деплоем и версионированием изменений;
- событиями, аудитом и observability;
- безопасным исполнением и секретным доступом через политики.

## Целевая платформа

1. Ubuntu 24.04 / Ubuntu Core
2. Ubuntu Frame (kiosk shell)
3. Tauri 2 + React/TypeScript (операторский интерфейс)
4. Rust local daemon (`crates/kolibri-locald`)
5. Rust control plane + планировщик
6. NATS JetStream как event bus
7. PostgreSQL (центральные метаданные)
8. SQLite (локальные кэши, local state)
9. Rust VPS agents
10. Sandbox/Policy layer

## Текущая фактическая реализация

- Реализован рабочий Rust daemon: `kolibri-locald`.
- Имеется зачаток доменного ядра в `crates/kolibri-core`:
  - node/agent/task/task_run/command/artifact модели,
  - event-константы и subject mapping,
  - secret-ref типы и redaction-методика.
- Сетевые интерфейсы locald пока реализованы как HTTP/Axum API.
- Интеграционные компоненты (control plane/agent/scheduler/proto/NATS/sandbox/backends) еще остаются в процессе scaffold/build-out.

## Основные потоки

- `submit_task` → `task.scheduled` → `lease_task` → `task.assigned`
- `task.heartbeat`
- `task.complete` / `task.fail` / `task.cancel`
- `terminal command` (в режиме policy/allowlist, без прямого root-режима)

## Принципы

- `default deny` для опасных команд и sandbox;
- policy всегда обязателен перед критичными действиями;
- события пишутся структурно и traceability через trace_id/correlation;
- no raw secrets in events/logs.

