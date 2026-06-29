# GoMesh / MikroTik live check — 2026-06-29

## Резюме

Проверка доступа через домашний узел/MikroTik выполнена 2026-06-29 15:41 MSK.

Вывод: путь к `10.99.0.1:8081` живой, SSH на `ladik@10.99.0.1` живой, Kolibri Mesh Agent на home отвечает. Старый endpoint `/health` неверен для этого сервиса: корректный health endpoint сейчас `/api/health`.

## Проверки

| Проверка | Результат |
| --- | --- |
| `curl http://10.99.0.1:8081/health` | HTTP 404, сервис доступен, но route отсутствует |
| `ssh ladik@10.99.0.1 'curl http://10.99.0.1:8081/health'` | HTTP 404 через SSH с home |
| `curl http://10.99.0.1:8081/api/health` | HTTP 200, `Kolibri Mesh Agent`, node `home`, status `ok`, version `0.2.0` |
| `ssh ladik@10.99.0.1 'curl http://127.0.0.1:8081/api/health'` | HTTP 200 на самом home-хосте |
| `ssh ladik@10.99.0.1 'hostname; ss -ltnp'` | host `plastilin`, порты `8080`, `8081`, `8082` слушают |
| `curl http://10.99.0.2:9101/health` | Control Plane ok, Redis PONG |
| `curl http://10.99.0.2:9101/v1/nodes` | зарегистрирован 21 узел; свежих 19, stale 2 |

## Узлы Control Plane

На момент проверки Control Plane показал 21 registered node:

- fresh/online: `main`, `mesh-9fts`, `mesh-agent-01` ... `mesh-agent-09`, `mesh-highload`, `mesh-home`, `mesh-paris`, `mesh-reserve242`, `mesh-server-kfrm`, `mesh-uiap`, `new`, `qjns`;
- stale: `primary-candidate`, `smoke-primary`.

Очередь Control Plane содержит 2 queued задачи:

- `KOL-SUPER-ESTIMATOR-001-REMOTE-STATUS-9FTS`;
- `KOL-UIAP-KNOWLEDGE-REMOTE-STATUS-001`.

## Несоответствия инструкции

Команда из старой инструкции:

```bash
cd /opt/kolibri/repo
python3 scripts/kolibri_gomesh_home_mesh_exec_collect.py --pretty
```

не воспроизводится на `root@10.99.0.2`: хост доступен как `kolibri-main-api`, но `/opt/kolibri/repo` отсутствует. В текущей ветке и на `runtime-repo` файл `scripts/kolibri_gomesh_home_mesh_exec_collect.py` не найден.

Дополнительно `ssh kolibri-main` через настроенный `ProxyJump ladik@178.207.11.90:2222` падает на `banner exchange`, но прямой `ssh root@10.99.0.2` работает. Это отдельный конфигурационный долг SSH alias, не блокер для прямого доступа к Control Plane.

## Следующее исполнение

1. Обновить runbook/инструкцию: заменить `/health` на `/api/health` для `Kolibri Mesh Agent`.
2. Уточнить актуальный repo path для main: сейчас найден `/var/lib/kolibri-agent/runtime-repo`, а не `/opt/kolibri/repo`.
3. Восстановить или удалить из инструкций ссылку на `scripts/kolibri_gomesh_home_mesh_exec_collect.py`.
4. Отдельной задачей починить SSH alias `kolibri-main`, чтобы он не ходил через сломанный jump, когда прямой `10.99.0.2` доступен.
