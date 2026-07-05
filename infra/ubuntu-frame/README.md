# Kolibri Kiosk / Ubuntu Frame

## Цель

Запуск Control Station на Ubuntu с UI-режимом Kiosk через Ubuntu Frame для 24/7 дисплейной точки управления.

## Минимальный порядок

1. Подготовьте чистую Ubuntu 24.04 (желательно Core/Server).
2. Установите Ubuntu Frame.
3. Сконфигурируйте автозапуск пользователя `kolibri` с:
   - запуском `kolibri-locald`
   - запуском Tauri station (для этой итерации — локальный бинарник на стенде)
4. Настройте restart policy через systemd.

## Минимальные переменные

- `KOLIBRI_LOCALD_LISTEN=127.0.0.1:8081`
- `KOLIBRI_CONTROL_PLANE_URL=http://127.0.0.1:8080`

## Наблюдение

- Логи системы: `journalctl -u kolibri-locald.service -f`
- Логи агента: `journalctl -u kolibri-agent.service -f`
