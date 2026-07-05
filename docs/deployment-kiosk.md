# Деплой в kiosk / Ubuntu Frame

## Локальный сценарий

1. Установить Ubuntu 24.04 LTS и Ubuntu Frame.
2. Установить systemd service для `kolibri-locald`.
3. Поднять Tauri Station (или веб-режим в fallback), запуск из locald-hosted API.
4. Включить auto-start + Restart=always.

## Минимум systemd (`infra/systemd/`)

- `kolibri-locald.service` — API + события + local storage
- `kolibri-agent.service` — runtime-агент (будет добавлен в следующей итерации)

## Логи и восстановление

- `journalctl -u kolibri-locald`
- health endpoint: `/health` и `/v1/health`
- при падении — авто рестарт через systemd.

