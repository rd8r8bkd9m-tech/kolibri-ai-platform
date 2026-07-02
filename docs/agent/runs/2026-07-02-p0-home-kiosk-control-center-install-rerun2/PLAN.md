# План: Home Kiosk Control Center — RERUN2

## Цель
Восстановить и запустить Firefox kiosk панель на home/plastilin для.owner-видимости фабрики.

## Диагностика
1. WireGuard tunnel к home был stale 16+ часов — исправлен (endpoint drift)
2. `kolibri-agent-host` падал с KeyError на `task["task_id"]` — исправлен на `task.get("task_id")`
3. Home heartbeat восстановлен, но node оставался stale из-за CPU contention от mimo процесса

## План действий
1. Проверить существующие wallboard/tty/service компоненты
2. Создать systemd юнит `kolibri-home-kiosk.service` для Firefox kiosk
3. Создать скрипт запуска `/usr/local/bin/kolibri-home-kiosk-start`
4. Исправить проблему X authority (root не имеет доступа к :0 — ladik owns X session)
5. Запустить и верифицировать kiosk

## Критерии успеха
- Firefox kiosk отображает `http://127.0.0.1:8180` в fullscreen на мониторе
- Все kolibri сервисы остаются активными
- PLAN/ACTIONS/RESULT/NEXT артефакты созданы
