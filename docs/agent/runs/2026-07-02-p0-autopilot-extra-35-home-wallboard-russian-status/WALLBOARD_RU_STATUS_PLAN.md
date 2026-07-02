# Home Wallboard Russian Status Plan

Purpose:

Make the Home wallboard useful to Vladislav at a glance: what is happening,
who is doing it, what is blocked, and what exact action comes next.

## Owner-Facing Layout

Top line:

`Фабрика: <state> | Обновлено: <time> | Источник: <source>`

Primary sections:

| Order | Russian title | Content |
| ---: | --- | --- |
| 1 | `В работе` | active/running tasks with fresh exact evidence |
| 2 | `Ожидает владельца` | owner-gated PR, merge, deploy, auth, provider, or credential actions |
| 3 | `Блокеры` | blockers with severity and exact repair task |
| 4 | `Активные агенты` | agent display name, role, node, task |
| 5 | `Следующее действие` | exactly one next task id and target node |

## Task Card Contract

Every visible task card must include:

| Field | Russian label | Rule |
| --- | --- | --- |
| `task_id` | `Задача` | exact P0 id |
| `status` | `Статус` | controlled vocabulary below |
| `node` | `Узел` | owner-readable node id, raw metadata secondary |
| `agent_name` | `Исполнитель` | Russian display name from `REMOTE_AGENTS.md` |
| `blocker` | `Блокер` | `нет` or concise blocker |
| `artifact` | `Артефакт` | path or PR artifact URL |
| `next_action` | `Дальше` | exact next task or owner action |

Status vocabulary:

| Internal state | Russian wallboard status |
| --- | --- |
| `queued` | `ожидает запуска` |
| `running` | `в работе` |
| `waiting_review` | `ждет проверки` |
| `blocked` | `заблокировано` |
| `failed` with useful artifact | `есть результат, нужна починка контракта` |
| `failed` without useful artifact | `ошибка выполнения` |
| `completed` | `готово` |
| stale/unknown | `требует перепроверки` |

## Active Agents

Wallboard should show Russian display names first:

| Agent | Role | Preferred use |
| --- | --- | --- |
| `Дмитрий — Fleet Engineer` | node health and Control Plane | active mesh and runtime health |
| `Ольга — Documentation Curator` | docs and owner summaries | status plans and artifacts |
| `Анна — Frontend/PWA Engineer` | Home wallboard implementation | PR-scoped UI work |
| `Наталья — Anti-Degradation Auditor` | independent QA/review | layout, stale data, blocker review |
| `Сергей — Backend/API Engineer` | backend/API contracts | status API repair by PR task |

## Blocker Rules

Blockers must be explicit and actionable:

| Blocker type | Russian label | Required next action |
| --- | --- | --- |
| missing PR scope | `нужна PR-задача` | create exact PR implementation task |
| stale heartbeat | `устаревший heartbeat` | exact Control Plane recheck task |
| missing artifact | `нет артефакта` | artifact repair task |
| auth/provider issue | `требуется доступ владельца` | owner-approved credential/provider repair |
| runtime route issue | `ошибка runtime-маршрута` | server-side canary repair task |
| Telegram mutation gate | `нужна авторизация владельца` | no mutation until owner-approved task |

## Next Action Rule

The Home wallboard should show only one primary next action:

`P0_HOME_WALLBOARD_RUSSIAN_STATUS_PR_IMPLEMENTATION_2026_07_02`

Why:

- This current run is documentation/planning only.
- Product/UI changes require a PR-scoped task.
- The next task should implement the display contract and tests.

## Example Owner Card

```text
Задача: P0_AUTOPILOT_EXTRA_35_HOME_WALLBOARD_RUSSIAN_STATUS_2026_07_02
Статус: готово
Узел: kolibri
Исполнитель: Ольга — Documentation Curator
Блокер: код продукта не менять без PR-задачи
Артефакт: docs/agent/runs/2026-07-02-p0-autopilot-extra-35-home-wallboard-russian-status/
Дальше: P0_HOME_WALLBOARD_RUSSIAN_STATUS_PR_IMPLEMENTATION_2026_07_02
```

