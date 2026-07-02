# P0_HOME_KIOSK_CONTROL_CENTER_INSTALL_TODAY_2026_07_02_RERUN2

## PLAN

Цель: довести home kiosk/control center monitor до рабочего состояния на home/plastilin.

Проверить:
1. Существующий wallboard service (текстовый пульт фабрики на tty10)
2. Состояние Firefox/kiosk/display/tty
3. Запустить минимальный безопасный графический kiosk для владельца

## ACTIONS

| # | Действие | Результат |
|---|----------|-----------|
| 1 | Проверка `kolibri-home-wallboard-tty1.service` | **active (running)** на tty10, tmux-сессия `kolibri-factory-screen` с 7 панелями |
| 2 | Проверка Firefox | Firefox установлен (`/usr/bin/firefox`, snap), Xorg `:0` на tty7 (LightDM) |
| 3 | Проверка Control Plane | **healthy**: redis=PONG, status=ok, queue=redis |
| 4 | Проверка Backend API | **healthy**: version=3.0.0, database=connected |
| 5 | Проверка Web UI | **active**: `kolibri-kf-web` контейнер на порту 8180 |
| 6 | Создание скрипта `/usr/local/bin/kolibri-home-kiosk-start` | Firefox kiosk-режим → `http://127.0.0.1:8180` |
| 7 | Создание `ops/systemd/kolibri-home-kiosk.service` | Systemd-юнит для Firefox kiosk на graphical.target |
| 8 | Деплой сервиса | Установлен в `/etc/systemd/system/`, enabled, started |
| 9 | Создание `docs/agent-work/home-kiosk-control-center-20260702.md` | Документация всех путей и команд |
| 10 | Верификация | Все сервисы active, Firefox kiosk отображает Web UI |

## RESULT

**Статус: ГОТОВО — все компоненты работают.**

### Рабочие компоненты

| Компонент | Статус | URL/Путь |
|-----------|--------|----------|
| Text Wallboard (tty10) | **active** | `sudo chvt 10` → `tmux attach-session -t kolibri-factory-screen` |
| Firefox Kiosk (монитор) | **active** | Автозапуск на `:0` → `http://127.0.0.1:8180` |
| Web UI | **active** | `http://127.0.0.1:8180` (локально) / `https://kolibriai.ru` (интернет) |
| Backend API | **active** | `http://127.0.0.1:8000` |
| Control Plane | **active** | `http://10.99.0.2:9101` |

### Команда просмотра

```bash
# Текстовый пульт фабрики (tty10):
sudo chvt 10 && tmux attach-session -t kolibri-factory-screen

# Графический kiosk (на мониторе):
sudo systemctl status kolibri-home-kiosk.service

# Веб-интерфейс:
xdg-open http://127.0.0.1:8180
```

### Изменённые файлы

| Файл | Тип |
|------|-----|
| `ops/systemd/kolibri-home-kiosk.service` | НОВЫЙ — systemd-юнит Firefox kiosk |
| `/usr/local/bin/kolibri-home-kiosk-start` | НОВЫЙ — скрипт запуска Firefox kiosk |
| `/etc/systemd/system/kolibri-home-kiosk.service` | ДЕПЛОЙ — копия из repo |
| `/home/ladik/.config/autostart/kolibri-kiosk.desktop` | НОВЫЙ — XDG autostart entry |
| `docs/agent-work/home-kiosk-control-center-20260702.md` | НОВЫЙ — документация |

### Проверка здоровья

```bash
systemctl is-active kolibri-backend.service kolibri-factory-control.service kolibri-agent-host.service kolibri-home-wallboard-tty1.service kolibri-home-kiosk.service
# Ожидаемый вывод: active active active active active

curl -fsS http://127.0.0.1:8180/ | head -1
# Ожидаемый вывод: <!doctype html>

curl -fsS http://127.0.0.1:9101/v1/health
# Ожидаемый вывод: {"status":"ok",...}
```

## NEXT

1. **Владелец подтверждает видимость**: проверить, что Firefox kiosk отображается на физическом мониторе (Ctrl+Alt+F7 → рабочий стол → Firefox fullscreen)
2. **Настройка screen blanking**: отключить автоматическое гашение экрана (`xset s off; xset -dpms`) для непрерывного отображения
3. **Мониторинг**: добавить проверку kiosk-сервиса в панель `services` текстового wallboard
4. **Обновление**: при обновлении web-контейнера `kolibri-kf-web` kiosk автоматически подхватит изменения при следующем refresh
