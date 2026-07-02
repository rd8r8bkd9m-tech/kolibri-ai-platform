# Результат: Home Kiosk Control Center — RERUN2

## Статус: УСПЕШНО

## Изменённые файлы
1. `ops/systemd/kolibri-home-kiosk.service` — systemd юнит для Firefox kiosk (создан)
2. `/usr/local/bin/kolibri-home-kiosk-start` — скрипт запуска kiosk (создан на home)
3. `/etc/systemd/system/kolibri-home-kiosk.service` — deployed systemd unit (с исправлением User=ladik)

## Сервисы
| Сервис | Статус |
|--------|--------|
| kolibri-agent-host | active |
| kolibri-agent-host-live | active |
| kolibri-factory-control | active |
| kolibri-backend | active |
| kolibri-home-wallboard-tty1 | active |
| kolibri-home-kiosk | active (Firefox kiosk running) |

## Команды проверки
```bash
# Статус kiosk
ssh root@10.99.0.1 systemctl status kolibri-home-kiosk

# Просмотр Firefox
ssh root@10.99.0.1 pgrep -a firefox

# Текстовый wallboard
ssh root@10.99.0.1 tmux list-sessions

# Веб-интерфейс
curl -s http://127.0.0.1:8180 | head -5

# Все kolibri сервисы
ssh root@10.99.0.1 systemctl is-active kolibri-agent-host kolibri-agent-host-live kolibri-factory-control kolibri-backend kolibri-home-wallboard-tty1 kolibri-home-kiosk
```

## Пути отображения для владельца
1. **Firefox kiosk** (монитор home): `systemctl status kolibri-home-kiosk` — fullscreen http://127.0.0.1:8180
2. **Текстовый wallboard** (tty10): `Ctrl+Alt+F10` → `tmux attach-session -t kolibri-factory-screen`
3. **Веб-интерфейс**: http://127.0.0.1:8180 (локально) или https://kolibriai.ru (интернет)

## Безопасность
- Firefox kiosk не раскрывает cookies/credentials
- Все внутренние API (10.99.0.x) не видны снаружи
- Сервис запущен от ladik с минимальными привилегиями
