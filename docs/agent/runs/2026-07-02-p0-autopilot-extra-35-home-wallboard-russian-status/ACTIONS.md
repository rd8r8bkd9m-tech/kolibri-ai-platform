# Actions

- Confirmed work is executing in the assigned server-side mesh worker checkout,
  not a Mac-local product checkout.
- Reviewed current dispatcher status, remote agent roster, remote result matrix,
  and recent canary artifacts.
- Created a Russian Home wallboard status reporting plan focused on visible
  tasks, active agents, blockers, and next actions.
- Kept all changes inside `docs/agent/runs/...` for this task.
- Avoided product code, frontend code, service restart, secret access, git push,
  force push, and push to `main`.

Owner-visible status model:

| Card | Required fields | Owner-facing wording |
| --- | --- | --- |
| Task card | task id, state, node, agent, artifact, next action | `Задача`, `Статус`, `Узел`, `Исполнитель`, `Артефакт`, `Дальше` |
| Agent card | display name, role, node, task, freshness | `Агент`, `Роль`, `Узел`, `Работает над`, `Свежесть` |
| Blocker card | blocker, severity, evidence, repair task | `Блокер`, `Критичность`, `Доказательство`, `Ремонт` |
| Next action card | exact task id, allowed scope, target node | `Следующая точная задача`, `Разрешенная область`, `Куда отправить` |

Recommended visible task grouping for Home:

| Group | Russian title | Examples |
| --- | --- | --- |
| active | `В работе` | currently leased/running exact P0 task |
| waiting | `Ожидает` | queued tasks or owner-gated work |
| blocked | `Заблокировано` | auth, runtime, stale heartbeat, missing PR gate |
| done | `Готово` | completed tasks with artifact path and verification |
| next | `Дальше` | one next exact task only |

