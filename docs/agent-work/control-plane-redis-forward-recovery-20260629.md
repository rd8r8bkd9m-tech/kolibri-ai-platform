# Control Plane Redis recovery

Дата: 2026-06-29
Роль: `SRE Control Plane`

## Инцидент

`kolibri-factory-control.service` на `main` зависал на `/v1/health`, потому
что `/etc/kolibri-factory-control.env` указывал `FACTORY_REDIS_HOST=10.99.0.1`,
а `10.99.0.1:6379` был недоступен.

## Исполнение

На `main` создан live systemd forward:

```text
kolibri-redis-forward.service
127.0.0.1:6379 -> root@10.99.0.10:127.0.0.1:6379
```

`FACTORY_REDIS_HOST` на `main` переключён на `127.0.0.1`, затем
`kolibri-factory-control.service` перезапущен.

Repo unit: `ops/systemd/kolibri-redis-forward.service`.

## Проверка

- `kolibri-redis-forward.service`: active;
- `kolibri-factory-control.service`: active;
- `/v1/health`: `status=ok`, `redis=PONG`;
- `/v1/tasks?summary=1&compact=1&limit=10`: отвечает через compact
  queue/active index;
- targeted Control Plane tests passed in local verification.

## Follow-up

- заменить ad-hoc SSH forward на штатный Redis endpoint или managed Redis;
- добавить alert на недоступность Redis upstream;
- после миграции удалить forward unit через отдельный rollout.
