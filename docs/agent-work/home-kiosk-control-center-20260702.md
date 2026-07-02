# Home Kiosk Control Center — Пульт фабрики на home/plastilin

## Текущее состояние (2026-07-02)

### Существующие компоненты

| Компонент | Тип | Статус | Расположение |
|-----------|-----|--------|--------------|
| Wallboard (текстовый) | systemd service (tty10) | **active (running)** | `kolibri-home-wallboard-tty1.service` → tmux `kolibri-factory-screen` на `/dev/tty10` |
| Wallboard (пользовательский) | systemd user service | **active** | `~ladik/.config/systemd/user/kolibri-home-wallboard.service` → tmux `kolibri-home-screen` |
| Firefox kiosk | systemd service | **СОЗДАН, требует деплоя** | `kolibri-home-kiosk.service` → Firefox fullscreen на `:0` |
| Web UI ( Kolibri) | Docker контейнер | **active** | `kolibri-kf-web` → `http://127.0.0.1:8180` |
| Backend API | Docker контейнер | **active** | `kolibri-kf-api` → `http://127.0.0.1:8000` |
| Control Plane | systemd service | **active** | `kolibri-factory-control.service` → `http://10.99.0.2:9101` |

### Пути отображения

| Путь | Тип | Доступ |
|------|-----|--------|
| tty10 | Текстовый консоль (tmux) | `Ctrl+Alt+F10` → `tmux attach-session -t kolibri-factory-screen` |
| tty7 / :0 | Графический (Xorg + LightDM) | `Ctrl+Alt+F7` → XFCE4 desktopladik |
| http://127.0.0.1:8180 | Веб-интерфейс Kolibri | Браузер на любом устройстве в сети |
| http://kolibriai.ru | Веб-интерфейс (nginx) | Через интернет (SSL) |

### Firefox/kiosk/display/tty состояние

- **Firefox**: установлен (`/usr/bin/firefox`, snap-пакет)
- **Xorg**: работает на `:0` (tty7), LightDM — display manager
- **DISPLAY**: `:0` (graphical session)
- **Kiosk-режим**: создается (Firefox `--kiosk`指向 `http://127.0.0.1:8180`)
- **Секреты**: не раскрываются, все URL — внутренние/localhost

### Панели текстового wallboard (tmux)

1. `overview` — общее состояние фабрики (серверы, задачи, сообщения)
2. `nodes` — список серверов и их статус
3. `tasks` — очередь и активные задачи
4. `messages` — последние сообщения агентов
5. `services` — состояние systemd-сервисов
6. `resources` — CPU, RAM, диски
7. `logs` — journalctl последних строк

## Деплой Firefox kiosk

```bash
# 1. Скопировать systemd-юнит
sudo cp ops/systemd/kolibri-home-kiosk.service /etc/systemd/system/
sudo systemctl daemon-reload

# 2. Активировать
sudo systemctl enable --now kolibri-home-kiosk.service

# 3. Проверить
sudo systemctl status kolibri-home-kiosk.service
```

## Просмотр панели

```bash
# Текстовый wallboard (tty10)
sudo chvt 10
tmux attach-session -t kolibri-factory-screen

# Веб-интерфейс (из браузера)
# Локально: http://127.0.0.1:8180
# Через интернет: https://kolibriai.ru

# Firefox kiosk (на мониторе owner)
# Автозапуск при загрузке graphical.target
sudo systemctl status kolibri-home-kiosk.service
```

## Безопасность

- Firefox kiosk не имеет доступа к cookies/credentials wallboard
- Все внутренние API-адреса (10.99.0.x) не раскрываются наружу
- Wallboard автоматически фильтрует секреты через `redact_stream`
- Сервисы запускаются с минимальными привилегиями
