# Server capacity SRE report

Дата: 2026-06-29  
Роль: `SRE серверов и мощности фабрики`  
Scope: оценить пригодность factory-серверов под QA, FormulaLM и сборки по
локальным артефактам, без запуска моделей, SSH, Control Plane mutations или
изменений кода.

## Источники

- `docs/agent-work/ubuntu-qa-runner-report.md` - снимок Control Plane и
  runner availability на 2026-06-29 07:33 MSK.
- `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json` - read-only probe для
  `server-kfrm` с `required_capability=read_only_probe`, `target_node=server-kfrm`,
  `max_retries=1`.

Этот документ является desk-review по уже собранному снимку. Новые live reads,
SSH, lease/retry/cancel/drain операции и запуск workloads не выполнялись.

## Executive summary

- Для тяжелых QA/build/FormulaLM задач сейчас нельзя считать доступным ни один
  fresh non-draining `generic_implementation` runner.
- `server-kfrm` - главный кандидат под тяжелые сборки, product QA и FormulaLM:
  8 CPU, около 27 GB доступной RAM, около 150 GB диска, capabilities
  `generic_implementation` и `read_only_probe`. Риск: stale heartbeat
  `2026-06-28T20:17:15Z`; использовать только после read-only probe.
- `highload` может быть резервом под сборки после восстановления heartbeat, но
  это не FormulaLM-кандидат: 1 CPU, около 3.3 GB RAM, около 23.3 GB диска.
- `primary-candidate` по ресурсам выглядит заметным, но он stale и связан с
  dead-letter контекстом `lease_expired`; для QA/FormulaLM его нужно держать в
  стороне до отдельного разбора.
- `qjns` имеет `qa`, но `draining=true`, мало RAM и около 6 GB диска; его нельзя
  планировать без явного un-drain решения владельца.
- `home`, `main`, `new` свежие и non-draining, но это контрольные/малые runner
  роли, не замена тяжелому Ubuntu `generic_implementation` capacity.

## Capacity matrix

| Node | Состояние по снимку | Ресурсы | Capabilities | QA | Сборки | FormulaLM |
| --- | --- | --- | --- | --- | --- | --- |
| `server-kfrm` | stale, non-draining | 8 CPU, 27 GB RAM, 150 GB disk | `generic_implementation`, `read_only_probe` | Лучший кандидат после probe | Лучший кандидат после probe | Единственный разумный кандидат на 6h bench после probe |
| `highload` | stale, non-draining | 1 CPU, 3.3 GB RAM, 23.3 GB disk | `generic_implementation`, `read_only_probe` | Только после probe, как резерв | Небольшие/средние сборки после probe | Не рекомендован для длинного bench |
| `primary-candidate` | stale, non-draining, dead-letter history | 8 CPU, 10.8 GB RAM, 80 GB disk | `generic_implementation`, `review` | Не использовать без разбора `lease_expired` | Потенциально, но не сейчас | Не использовать без отдельного подтверждения |
| `home` | fresh, non-draining | 6 CPU, 12.5 GB RAM, 23.2 GB disk | `coordinator`, `orchestrator`, `read_only_probe` | Read-only/control preflight | Нет, не build runner | Нет |
| `main` | fresh, non-draining | 1 CPU, 768 MB RAM, 9.7 GB disk | `implementation`, `review`, `read_only_probe` | Малые targeted checks | Только очень малые изменения | Нет |
| `new` | fresh, non-draining | 2 CPU, 5.8 GB RAM, 51.4 GB disk | `review`, `generic_review`, `read_only_probe` | Review/read-only QA | Нет `generic_implementation` | Нет |
| `qjns` | fresh, draining | 1 CPU, 0.7 GB RAM, 6 GB disk | `implementation`, `review`, `qa` | Не планировать while drained | Нет | Нет |
| `uiap` | fresh, draining | 2 CPU, low RAM, 0 GB disk | `research`, `security`, `rag` | Не планировать | Нет | Нет |

Mesh shadow nodes, включая `mesh-server-kfrm`, не считать вычислительной
емкостью: они показывают mesh presence, но не дают node-local worktree/artifact
roots для QA или сборок.

## Stale и draining

Stale non-draining, сначала probe/heartbeat, потом нагрузка:

- `server-kfrm` - целевой heavy runner; уже есть envelope
  `KOL-SERVER-KFRM-PROBE-20260629`.
- `highload` - резервный build runner; перед workload нужен отдельный read-only
  probe envelope.
- `primary-candidate` - не будить под QA до разбора dead-letter/lease history.

Draining, не планировать:

- `qjns` - QA-capable, но `draining=true`; еще и ресурсно слабый.
- `uiap` - `draining=true`, 0 GB disk, не QA/build target.

Fresh non-draining, но не heavy capacity:

- `home` - координация и read-only preflight.
- `main` - малые implementation/review задачи.
- `new` - review/read-only QA.

## Безопасный порядок пробуждения

1. Сначала только read-only Control Plane snapshot: `/health`, `/v1/nodes`,
   targeted `/v1/tasks/<task_id>`, `/v1/filesystem`. Не использовать широкий
   `/v1/tasks` как обязательный шаг, потому что в исходном отчете compact list
   давал тяжелый payload и timeout.
2. Дождаться или инициировать через Control Plane уже созданный probe:
   `KOL-SERVER-KFRM-PROBE-20260629`. Это P0 gate для `server-kfrm`.
   Повторно не submit, если task уже live queued.
3. Считать `server-kfrm` пригодным только если probe leased именно
   `server-kfrm`, завершился через node-local artifacts, и acceptance подтвердил:
   без SSH, secrets и shared writable root.
4. После успешного `server-kfrm` probe дать первой пройти уже заведенной P0
   product QA нагрузке `KOL-PRODUCT-QA-E2E-20260629`, если есть fresh
   non-draining `generic_implementation` capacity.
5. Затем пропускать build/UI работу `KOL-PREMIUM-LANDING-UI-20260629`; если она
   меняет release-facing UI, после нее нужен повторный QA gate.
6. Если runner runtime требует нормализации CLI/auth, только потом запускать
   `KOL-CODEX-CLI-ROLLOUT-20260629`.
7. `KOL-DESKTOP-CONTROL-APP-MVP-20260629` запускать после стабилизации capacity,
   не раньше product QA.
8. `KOL-FORMULALM-REMOTE-BENCH-6H-20260629` запускать последним: только после
   fresh heartbeat `server-kfrm`, успешного read-only probe и отсутствия
   ожидающей release QA нагрузки.
9. Для `highload` сначала подготовить/submit отдельный read-only probe envelope
   с `target_node=highload`, `required_capability=read_only_probe`,
   `max_retries=1`; только после него рассматривать small/medium build queue.
10. `primary-candidate` не будить через implementation workload. Если владелец
    отдельно подтвердит разбор stale/dead-letter риска, начинать с read-only
    probe или review-only действия, не с QA/build/FormulaLM.

## Что нельзя делать без подтверждения

- SSH на любые ноды, ручной запуск процессов на серверах, рестарт Agent Host или
  прямое исправление runtime.
- Запуск моделей или FormulaLM benchmark, особенно 6h workload.
- `cancel`, `retry`, `delete`, `drain`, `un-drain`, изменение leases или ручное
  снятие dead-letter задач.
- Повторный submit уже live задач, включая `KOL-SERVER-KFRM-PROBE-20260629` и
  `KOL-PRODUCT-QA-E2E-20260629`, без проверки targeted task status и решения
  оператора.
- Использование `qjns` или `uiap`, пока они `draining=true`.
- Использование `primary-candidate` для QA/build/FormulaLM до расследования
  `lease_expired`.
- Запуск product QA на Mac/control машине вместо Ubuntu factory node.
- Доверять одному `health=online` без freshness heartbeat, `draining=false`,
  capability match и проверки доступного диска.
- Читать или писать node-local файлы через Control Plane в обход manifest /
  namespace контракта.

## Проверки при подготовке

- Прочитан `docs/agent-work/ubuntu-qa-runner-report.md`.
- Прочитан `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json`.
- Проверено отсутствие существующего `docs/agent-work/server-capacity-sre-report.md`
  перед созданием.
- Проверен `git status --short docs/agent-work ops/envelopes` только для
  ориентации по рабочему дереву.
- Не выполнялись: SSH, model workloads, `ops/kolibri-dispatch submit`, Control
  Plane mutations, изменения исходного кода.
