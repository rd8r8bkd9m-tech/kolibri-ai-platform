# Действия: Home Kiosk Control Center — RERUN2

## Выполнено

### 1. Диагностика Wallboard/Kiosk/Display
- Проверены tmux сессии: `kolibri-factory-screen` (root) и `kolibri-home-screen` (ladik)
- Wallboard работает на tty10 через tmux, 7 панелей (overview, nodes, tasks, messages, services, resources, logs)
- Xorg работает на :0 (tty7), LightDM active, ladik owns session
- Firefox установлен (snap), но не запущен в kiosk режиме

### 2. Создан systemd юнит
- Файл: `ops/systemd/kolibri-home-kiosk.service`
- Деплой: `/etc/systemd/system/kolibri-home-kiosk.service`
- Ключевое исправление: `User=ladik` + `XAUTHORITY=/home/ladik/.Xauthority` (root не имеет X auth cookies для :0)

### 3. Создан скрипт запуска
- Файл: `/usr/local/bin/kolibri-home-kiosk-start`
- Ожидает X display и URL, запускает Firefox в kiosk режиме
- Auto-restart через systemd

### 4. Исправление X Authority
- Проблема: service запускался от root, X :0 принадлежит ladik
- Решение: `User=ladik` в systemd unit + `XAUTHORITY=/home/ladik/.Xauthority`
- Верификация: `xdpyinfo -display :0` работает от ladik

### 5. Деплой и верификация
- `systemctl daemon-reload && systemctl start kolibri-home-kiosk`
- Firefox запущен: `firefox --kiosk --new-window http://127.0.0.1:8180`
- Web UI доступен: `curl http://127.0.0.1:8180` OK
- Все 6 kolibri сервисов active
