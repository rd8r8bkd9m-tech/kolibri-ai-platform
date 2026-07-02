# Home NOC Control Center — Runbook

**Статус:** trunk-ready, 2026-07-03
**Сервер:** plastilin (home node)
**Порт NOC:** 9191 (клиентский портал 8180 запрещён)
**Контроллер:** kolibri-control-center.service

---

## Архитектура

```
Firefox kiosk (:0, DISPLAY=:0)
  → http://127.0.0.1:9191  (kolibri-home-kiosk.service)
      ↓
kolibri-control-center.service (port 9191)
  → /api/snapshot → factory_control.py (port 9101)
  → /  → noc_wallboard.html
```

**Ключевые файлы на сервере:**

| Файл | Назначение |
|------|-----------|
| `/opt/kolibri-control-center/server.py` | NOC HTTP-сервер (stdlib, port 9191) |
| `/opt/kolibri-control-center/noc_wallboard.html` | Wallboard HTML (standalone, dark NOC theme) |
| `/etc/systemd/system/kolibri-control-center.service` | systemd unit |
| `/etc/systemd/system/kolibri-home-kiosk.service.d/90-control-center-noc-url.conf` | Drop-in: KIOSK_URL=9191 |

---

## Деплой

```bash
./scripts/deploy-home-noc.sh
```

Или вручную:

```bash
# Копирование файлов
scp ops/noc_control_center_server.py plastilin:/opt/kolibri-control-center/server.py
scp ops/noc_wallboard.html plastilin:/opt/kolibri-control-center/noc_wallboard.html
scp ops/systemd/kolibri-control-center.service plastilin:/etc/systemd/system/
scp ops/systemd/kolibri-home-kiosk.service.d/90-control-center-noc-url.conf \
    plastilin:/etc/systemd/system/kolibri-home-kiosk.service.d/

# Активация
ssh plastilin "sudo systemctl daemon-reload"
ssh plastilin "sudo systemctl enable --now kolibri-control-center"
ssh plastilin "sudo systemctl restart kolibri-home-kiosk"
```

---

## Верификация

```bash
./scripts/verify-home-noc.sh
```

Ручные проверки:

```bash
# Сервис активен
systemctl status kolibri-control-center

# Порт слушает
ss -tlnp | grep :9191

# Клиентский портал НЕ слушает (запрещён)
ss -tlnp | grep :8180  # должен вернуть пустоту

# Health
curl -s http://127.0.0.1:9191/api/health

# Snapshot: health + node/task counts
curl -s http://127.0.0.1:9191/api/snapshot | python3 -m json.tool

# Firefox kiosk URL
systemctl show kolibri-home-kiosk -p Environment | grep KIOSK_URL
# Ожидаемый вывод: KOLIBRI_KIOSK_URL=http://127.0.0.1:9191

# Wallboard HTML доступен
curl -sf http://127.0.0.1:9191/ | head -5
```

---

## Откат

```bash
# Остановить NOC сервер
sudo systemctl stop kolibri-control-center
sudo systemctl disable kolibri-control-center

# Убрать drop-in
sudo rm /etc/systemd/system/kolibri-home-kiosk.service.d/90-control-center-noc-url.conf
sudo systemctl daemon-reload
sudo systemctl restart kolibri-home-kiosk

# Вернуть kiosk на старый URL (если был)
# sudo systemctl edit kolibri-home-kiosk  # убрать/изменить KIOSK_URL
```

---

## Диагностика

```bash
# Логи NOC сервера
journalctl -u kolibri-control-center -f

# Логи kiosk (Firefox)
journalctl -u kolibri-home-kiosk -f

# Проверить что factory_control доступен
curl -s http://10.99.0.2:9101/v1/health

# Список всех kolibri-сервисов
systemctl list-units 'kolibri-*' --no-pager

# Проверить что 8180 НЕ используется NOC-ом
ss -tlnp | grep -E ':8180|:9191'
```

---

## Правила

- Порт **9191** — единственный порт NOC Control Center
- Порт **8180** (клиентский портал) **запрещён** для NOC — никогда не менять
- Wallboard — standalone HTML (не React), без билда
- Все UI-метки на русском языке
- Фабричный контроллер: `http://10.99.0.2:9101`
- Drop-in `90-control-center-noc-url.conf` переопределяет `KOLIBRI_KIOSK_URL`
