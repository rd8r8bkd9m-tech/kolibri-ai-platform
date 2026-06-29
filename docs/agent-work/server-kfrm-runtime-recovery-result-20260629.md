# Отчет по KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629

Снимок Control Plane: `2026-06-29T05:51:29Z`.

## Итог

Задача `KOL-SERVER-KFRM-RUNTIME-RECOVERY-20260629` не выполнена: она существует, но находится в состоянии `queued`, без `lease_owner`, `lease_until`, `result` и `result_reference`.

Готовность узла `server-kfrm`: **not_ready**.

## Статус задачи

- `state`: `queued`
- `lease_owner`: `null`
- `lease_until`: `null`
- `attempt`: `0`
- `result`: `null`
- `result_reference`: `null`
- `created_at`: `2026-06-29T05:43:57.963045+00:00`
- `updated_at`: `2026-06-29T05:43:58.030572+00:00`

## Узел server-kfrm

Основная исполнительская запись:

- `node_id`: `server-kfrm`
- `agent_id`: `agent-host-server-kfrm`
- `hostname`: `server-kfrm`
- `state/health`: `stale`
- `fresh`: `false`
- `heartbeat_at`: `2026-06-28T20:17:15.661022+00:00`
- `heartbeat_age_seconds`: `34453.558882`
- `capabilities`: `generic_implementation`, `read_only_probe`, `mesh_node`
- `active_task`: `null`
- `draining`: `false`
- `lease_owner`: `null`

Похожая mesh-запись:

- `node_id`: `mesh-server-kfrm`
- `agent_id`: `mesh-server-kfrm`
- `hostname`: `server-kfrm`
- `state/health`: `stale`
- `fresh`: `false`
- `heartbeat_at`: `2026-06-29T00:05:46.769878+00:00`
- `heartbeat_age_seconds`: `20742.450026`
- `capabilities`: `mesh`, `mesh_node`
- `active_task`: `null`
- `draining`: `false`
- `lease_owner`: `null`

## Блокеры

- Recovery-задача не была взята в lease и не дала результата.
- Основной executor `server-kfrm` stale: свежего heartbeat нет.
- Связанная mesh-запись `mesh-server-kfrm` также stale.

## Follow-up задание

С явным operator approval восстановить Agent Host на хосте `server-kfrm`: перезапустить или bootstrap Agent Host так, чтобы `node_id=server-kfrm` стал `fresh=true` и `health=online`, затем выполнить read-only probe, leased by `server-kfrm`, и приложить его `result_reference` из Control Plane.
