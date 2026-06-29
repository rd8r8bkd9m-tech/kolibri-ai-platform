# Деплой и эксплуатация

Kolibri разворачивается как набор сервисов: backend, frontend, Control Plane,
Agent Host и вспомогательные mesh/API компоненты.

## Публичный контур

Публичная точка входа:

- приложение: `http://104.253.43.117`;
- backend за nginx: `/api/*`;
- WebSocket: `/ws/chat`;
- SPA fallback: `try_files $uri $uri/ /index.html`.

## Main server

Main отвечает за API Gateway, frontend и публичный nginx.

Базовый deploy:

```bash
./scripts/deploy.sh main
```

После deploy:

```bash
ssh kolibri-main "systemctl status kolibri-ai --no-pager"
ssh kolibri-main "nginx -t"
curl http://104.253.43.117
curl http://104.253.43.117/api/providers
```

## Agent Host

Agent Host должен запускаться через systemd и регистрироваться в Control
Plane.

Проверка:

```bash
curl http://10.99.0.2:9101/v1/nodes
```

Узел готов к реализации задач только если:

- heartbeat свежий;
- `draining=false`;
- есть нужная capability;
- хватает RAM/disk;
- установлен runner (`codex` или `mimo`);
- GitHub push работает без интерактива;
- нет stale `active_task`.

## Bootstrap новых серверов

Все новые серверы готовятся одинаково:

```bash
KOLIBRI_FACTORY_CONTROL_URLS=http://10.99.0.2:9101 \
KOLIBRI_BOOTSTRAP_RESTART_JITTER=60 \
sudo -E ops/bootstrap_factory_node.sh
```

Масштабирование:

- batch size: 10 серверов;
- target agents per node: 20;
- large-node agents per node: 100;
- целевая загрузка фабрики: 80%.

## Rollback

Минимальный rollback:

- вернуть предыдущий Git commit;
- пересобрать frontend;
- перезапустить backend service;
- проверить nginx;
- проверить `/api/providers` и `/health`;
- зафиксировать incident report.

## Production checklist

- `npm --prefix frontend run build`;
- backend tests;
- factory contract tests;
- smoke public URL;
- smoke API;
- smoke WebSocket;
- Control Plane health;
- GitHub CI green или blocker report;
- QA task через Control Plane.
