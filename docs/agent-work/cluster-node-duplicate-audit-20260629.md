# Аудит дублей узлов кластера Kolibri

Дата проверки: 2026-06-29 09:42 MSK
Источник: live `GET http://10.99.0.2:9101/v1/nodes`

## Короткий ответ

- Зарегистрировано записей узлов: 35.
- Канонических узлов после дедупликации: 21.
- Fresh/online записей: 6.
- Fresh и не draining записей: 3.
- Fresh канонических узлов: 3.
- Fresh канонических узлов с `generic_implementation`: 1.
- Найдено `mesh-*` shadow-дублей: 13.
- Группы дублей по `hostname`: 2.

Важно: `35` - это количество записей в Control Plane, а не доказанное
количество физических серверов. Реальная мощность должна считаться по
каноническим узлам, иначе фабрика завышает доступную емкость.

## Дубли по hostname

| Hostname | Записи |
| --- | --- |
| `plastilin` | `home`, `home-live` |
| `server-kfrm` | `mesh-server-kfrm`, `server-kfrm` |

## Mesh shadow-дубли

Эти записи имеют вид `mesh-*` и дублируют обычный `node_id`:

- `mesh-9fts` -> `9fts`
- `mesh-agent-02` -> `agent-02`
- `mesh-agent-03` -> `agent-03`
- `mesh-agent-04` -> `agent-04`
- `mesh-agent-05` -> `agent-05`
- `mesh-agent-06` -> `agent-06`
- `mesh-agent-07` -> `agent-07`
- `mesh-agent-08` -> `agent-08`
- `mesh-home` -> `home`
- `mesh-main` -> `main`
- `mesh-new` -> `new`
- `mesh-reserve242` -> `reserve242`
- `mesh-server-kfrm` -> `server-kfrm`

## Рабочая интерпретация для Control Plane

Для планирования задач нельзя использовать сырое число `35`.
Нужен канонический расчет:

1. Сначала группировать записи по физической машине.
2. Исключать `mesh-*` shadow-записи, если есть обычный одноименный узел.
3. Внутри одной физической машины выбирать fresh non-draining запись.
4. Если fresh записи нет, считать машину stale и не планировать на нее
   исполнительные задачи.
5. Для P0-работы использовать только fresh non-draining узлы с нужной
   capability, например `generic_implementation`.

На момент проверки реальный исполнительный пул для `generic_implementation`
сильно меньше 35: fresh non-draining с `generic_implementation` виден только
`home`.

Текущий канонический ответ на вопрос о мощности: всего 21 после
дедупликации, работает 3 канонических fresh non-draining узла, из них только
1 подходит для `generic_implementation`.

## Следующий инженерный шаг

Выполнено в Control Plane: `/v1/nodes` теперь возвращает отдельный `summary`
с полями:

- `registered_nodes`;
- `canonical_nodes`;
- `mesh_shadow_duplicates`;
- `duplicate_hostname_groups`;
- `fresh_canonical_nodes`;
- `fresh_canonical_generic_implementation_nodes`;
- список исключенных shadow-записей.

Это нужно, чтобы фабрика не принимала решения о мощности по завышенному
числу зарегистрированных карточек.

## Проверки

- Локально: `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_autonomy_contracts.py tests/test_factory_runtime_queue_contracts.py` -> `14 passed`.
- Live deploy: `kolibri-factory-control.service` на `10.99.0.2` перезапущен,
  статус `active`.
- Live `/v1/nodes` после деплоя вернул:
  - `registered_nodes=35`;
  - `canonical_nodes=21`;
  - `fresh_canonical_nodes=3`;
  - `fresh_canonical_generic_implementation_nodes=1`;
  - `mesh_shadow_duplicates=13`;
  - `duplicate_hostname_groups=2`.

## Связанный runtime smoke

Задача `KOL-HOME-GENERIC-RUNTIME-SMOKE-RERUN4-20260629` завершилась на
удаленном узле `home` и подтвердила, что исправленный Agent Host возвращает
результат исполнителя в Control Plane:

- state: `waiting_review`;
- node: `home`;
- runner: `codex`;
- commit: `c357064d29ee41943c3b4967d6c55010614fe894`;
- pushed: `true`;
- changed_files: `docs/agent-work/home-result-capture-rerun4-20260629.md`.
