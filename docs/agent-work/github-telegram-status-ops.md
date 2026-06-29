# GitHub и Telegram статусы для агентов Kolibri

Роль: `github_telegram_status_operator`  
Понятное название: Оператор GitHub и Telegram статусов  
Дата подготовки: 2026-06-29  
Статус: регламент для агентов; код не менялся.

Этот документ описывает, как агенты фабрики Kolibri должны отдавать одинаковые
короткие статусы в GitHub PR/issues/Project и Telegram-бот владельца. GitHub
остаётся подробным операционным журналом со ссылками на task/report/artifacts,
а Telegram получает ту же семантику, но в owner-safe форме: коротко, без
служебных идентификаторов и без технического мусора.

## 1. Цель

Единый статус нужен, чтобы владелец, агенты и automation видели один факт:

- что сейчас происходит;
- что уже проверено;
- где результат или blocker;
- какой следующий шаг;
- какая ссылка соединяет report file, `task_id`, GitHub item и Telegram-сводку.

Нельзя вести отдельные "правды" для GitHub и Telegram. Если GitHub item говорит
`В работе`, Telegram не должен обещать "готово". Если Telegram написал
"требует разбора", в GitHub должен быть issue/PR comment или Project item с
тем же blocker summary.

## 2. Источники факта

Приоритет источников:

1. Control Plane task: `task_id`, state, attempt, result reference, error type.
2. Report file: markdown-отчёт агента или automation в `docs/agent-work/*` или
   `ops/*-report.md`.
3. GitHub issue/PR: owner-visible история, acceptance, review, CI и ссылки.
4. GitHub Project: компактная доска текущего состояния.
5. Telegram: короткая owner-safe сводка и уведомления о важных переходах.

Telegram не является хранилищем результата. Он только сообщает владельцу
состояние и безопасную ссылку, если она уже есть.

## 3. Единый словарь коротких статусов

Агент публикует ровно один короткий статус из этого набора:

| Канонический статус | Control Plane | Project | Telegram-смысл | Когда использовать |
| --- | --- | --- | --- | --- |
| `queued` | `queued` | `Новая` / `Todo` | `В очереди` | Задача принята, но исполнитель ещё не начал работу. |
| `running` | `leased`, `running`, `retry_scheduled` | `В работе` / `In Progress` | `В работе` | Есть активный исполнитель, lease, branch или проверяемый следующий шаг. |
| `review` | `waiting_review`, `review` | `На проверке` / `In Progress` | `На проверке` | Результат готов для review, CI или независимой проверки. |
| `blocked` | `failed`, `dead_letter` | `Заблокирована` / `In Progress` с blocker comment | `Требует разбора` | Нужен доступ, секрет, внешний сервис, owner decision или root-cause fix. |
| `done` | `completed` | `Готово` / `Done` | `Готово` | Acceptance закрыт и есть result/report/PR/issue evidence. |
| `cancelled` | `cancelled` | `Готово` или `Заблокирована` | `Отменена` | Отмена была явным решением или работа больше не нужна. |

Если текущая Project schema имеет только `Todo`, `In Progress`, `Done`, то
`review` и `blocked` остаются `In Progress`, а точная причина пишется в
issue/PR comment и поле `Артефакты`.

## 4. Минимальный status packet

Каждый агент, automation или оператор при изменении статуса формирует один
короткий пакет. Один пакет должен быть переносимым между Control Plane feed,
GitHub и Telegram.

```text
status: running | review | blocked | done | queued | cancelled
summary: 1 короткое предложение по-русски
task_id: KOL-... или TG-...
report_file: docs/agent-work/...md или ops/...-report.md
github: PR #... / issue #... / pending
project_sync: done | pending | blocked | not_needed
telegram_summary: owner-safe фраза без task_id/path/node
next_step: 1 конкретное действие
next_report_at: 2026-06-29 18:30 Europe/Moscow или not_needed
```

Расширенные поля допустимы только для GitHub/report:

- branch;
- commit;
- CI/checks;
- result path;
- manifest path;
- node/agent id;
- verification commands;
- error type.

## 5. Что публиковать

### 5.1 В GitHub issue/PR

Публиковать:

- канонический статус;
- `task_id`;
- ссылку на report file;
- PR/issue cross-link;
- Project sync state;
- result/manifest reference, если есть;
- проверки или честное объяснение, почему они не запускались;
- blocker summary и кто снимает blocker;
- следующий шаг и время следующего отчёта.

Минимальный comment:

```markdown
Status: В работе
Task: KOL-GITHUB-TELEGRAM-STATUS-20260629
Report: docs/agent-work/github-telegram-status-ops.md
Project sync: done
Telegram summary: "Задача в работе. Я пришлю результат после проверки."

Что сделано:
- Подготовлен единый status packet для GitHub и Telegram.

Что проверено:
- Markdown-файл создан, код не менялся.

Следующий шаг:
- Привязать этот регламент к automation, которая синхронизирует PR/issues/Project.
```

### 5.2 В GitHub Project

Публиковать только компактные поля:

- status;
- priority;
- direction;
- agent;
- next report;
- artifacts: PR/issue/report/result references.

Project не должен получать raw logs, длинные отчёты или payloads. Если поле
Project не подходит, добавить ссылку в issue/PR comment и написать
`Project field update: pending`.

### 5.3 В Telegram

Публиковать только owner-safe summary:

- `В очереди. Я поставил задачу в работу и вернусь, когда она начнёт двигаться.`
- `В работе. Исполнитель уже занимается задачей; следующий понятный статус пришлю после проверки.`
- `На проверке. Результат готов, я сверяю его перед тем как назвать готовым.`
- `Готово. Результат проверен: <безопасная ссылка или короткий итог>.`
- `Требует разбора. Есть технический сбой или внешний blocker; я зафиксировал его и веду разбор.`
- `Отменена. Задача остановлена, дальше по ней действий не требуется.`

Если есть публичная безопасная ссылка на PR, preview или документ, её можно
добавить. Если есть только node-local artifact path, в Telegram ссылка не
публикуется.

## 6. Что не публиковать

Нельзя публиковать нигде:

- секреты, токены, cookies, приватные ключи, auth cache;
- содержимое `.env` или путь, который раскрывает secret source;
- персональные контакты инвесторов и клиентов;
- непроверенные финансовые, fundraising или model-performance claims.

Нельзя публиковать в Telegram:

- `task_id`, если владелец прямо не запросил диагностику;
- node id, agent id, hostname, worktree;
- `/var/lib/...`, `/tmp/...`, `result_path`, `log_path`;
- raw stdout/stderr;
- traceback, CLI noise, stack traces;
- длинный список queued/running задач;
- внутренние `Project field id`, option id, OAuth/scopes details.

Нельзя публиковать в Project:

- большие raw payloads;
- приватные local paths без диагностической необходимости;
- full logs без редактуры;
- спорные "готово" без artifact/report/PR evidence.

## 7. Как не спамить владельца

Telegram-бот пишет владельцу только при значимых переходах:

- `queued` после прямого owner request или если задача была создана из Telegram;
- `running`, когда задача реально получила исполнителя или началась после долгого ожидания;
- `review`, когда появился PR/result и нужен review;
- `blocked`, когда появился новый blocker или поменялось действие владельца;
- `done`, когда есть проверенный результат;
- `cancelled`, когда отмена видима владельцу.

Не слать Telegram-уведомления:

- при каждом heartbeat;
- при повторном polling без изменения канонического статуса;
- при каждом retry одной и той же причины;
- когда изменился только `updated_at`;
- когда появилась внутренняя деталь, не влияющая на owner decision;
- чаще одного раза за throttle window по одной задаче.

Рекомендуемый throttle:

| Тип | Правило |
| --- | --- |
| P0 blocker | Сразу при обнаружении, затем не чаще 30 минут без нового факта. |
| P1 active work | При старте, review/blocker/done, затем не чаще 2-4 часов. |
| P2/backlog | При взятии в работу и завершении; не чаще одного раза в сутки. |
| Chat task `TGCHAT-*` | Не auto-track как рабочую задачу, отвечать только результатом разговора. |
| Image task `TGIMG-*` | Не писать промежуточные `running`; отправить картинку или failure summary. |

Dedup key для Telegram:

```text
task_id + canonical_status + public_summary_hash
```

Если key не изменился, Telegram молчит, а GitHub/report могут обновляться по
своему SLA.

## 8. Связь report file, task_id, GitHub и Telegram

Каждая задача должна иметь один trace record. Он живёт в report file или в
issue/PR body/comment.

```text
Trace:
- task_id: KOL-...
- report_file: docs/agent-work/...md
- issue: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/issues/...
- pull_request: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/...
- project_item: Project #2 item или pending
- telegram_thread: owner private chat / message_id скрыт из публичного GitHub
- telegram_summary: "В работе. Исполнитель уже занимается задачей."
- result: result.json или not_ready
- manifest: artifact-manifest.json или not_ready
```

Правила связки:

- `task_id` всегда пишется в report file и GitHub.
- `task_id` не пишется в Telegram summary по умолчанию.
- Report file должен ссылаться на issue/PR, если они уже существуют.
- Issue/PR должен ссылаться на report file.
- Project поле `Артефакты` хранит короткий список: `task_id`, report, PR/issue,
  result/manifest или `pending`.
- Telegram state store может хранить `task_id` и message id технически, но
  owner-facing текст показывает только summary.
- Если GitHub item ещё не создан, report пишет `github: pending` и причину.
- Если report ещё не создан, GitHub comment пишет `report_file: pending` и
  кто должен его создать.

## 9. Форматы по каналам

### 9.1 Agent message

```json
{
  "sender": "github_telegram_status_operator",
  "recipients": ["all"],
  "kind": "status",
  "topic": "github_telegram_status",
  "task_id": "KOL-GITHUB-TELEGRAM-STATUS-20260629",
  "body": "running: регламент статусов готовится",
  "artifacts": [
    {
      "report_file": "docs/agent-work/github-telegram-status-ops.md",
      "pull_request_url": "pending",
      "issue_url": "pending"
    }
  ]
}
```

### 9.2 GitHub comment

```markdown
Status: На проверке
Task: KOL-...
Report: docs/agent-work/github-telegram-status-ops.md
Project sync: pending
Telegram summary: "На проверке. Результат готов, я сверяю его перед тем как назвать готовым."

Evidence:
- PR: #123
- Checks: `python3 -m compileall -q ops`
- Result: `/var/lib/kolibri-agent/artifacts/.../result.json`

Next step:
- Дождаться CI и перевести Project item в `Done` только после зелёной проверки.
```

### 9.3 Telegram summary

```text
На проверке. Результат готов, я сверяю его перед тем как назвать готовым.
```

Если есть безопасная публичная ссылка:

```text
Готово. Результат проверен: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/123
```

## 10. Правила для PR, issues и Project

Issue создаётся, если:

- есть blocker, follow-up, research task или docs debt;
- задача пришла из Telegram, но требует видимого operational trail;
- Control Plane result требует review или owner decision.

PR создаётся, если:

- менялись код, docs, configs, CI, envelopes или проверяемые artifacts;
- acceptance закрывается изменением в репозитории.

Project обновляется, если:

- есть issue/PR;
- статус влияет на owner-visible очередь;
- есть blocker, review или done.

Project не обновляется отдельно от GitHub trail. Если Project update не удался,
агент пишет в issue/PR:

```text
Project sync: pending
Reason: <короткая причина>
```

## 11. Handoff

При передаче задачи другому агенту нужно сохранить одинаковый статус во всех
каналах.

Handoff packet:

```text
status: blocked | running | review
task_id: KOL-...
report_file: ...
github: ...
telegram_summary: ...
done: что уже сделано
checked: что проверено
do_not_touch: что нельзя менять
next_step: один конкретный шаг
owner_needed: yes/no + причина
```

Telegram получает только `telegram_summary`. GitHub получает весь packet.

## 12. Acceptance checklist

- [ ] У каждого owner-visible статуса есть канонический `queued/running/review/blocked/done/cancelled`.
- [ ] В GitHub указан `task_id`, если задача пришла из Control Plane или Telegram.
- [ ] В GitHub есть report file или явный `report_file: pending`.
- [ ] Report file содержит ссылку на issue/PR/Project или явный `github: pending`.
- [ ] Project поле `Артефакты` содержит безопасные references.
- [ ] Telegram summary не содержит `task_id`, node, agent, local paths, logs или secrets.
- [ ] Telegram не дублирует один и тот же статус без нового факта.
- [ ] `Готово` не публикуется без result/report/PR/issue evidence.
- [ ] Blocker имеет владельца следующего действия и время следующего отчёта.
- [ ] Код не менялся при обновлении этого регламента.

## 13. Проверка этого документа

Для документационной правки достаточно проверить:

```bash
test -f docs/agent-work/github-telegram-status-ops.md
rg -n "status packet|Telegram summary|Trace:|Acceptance checklist" docs/agent-work/github-telegram-status-ops.md
git diff -- docs/agent-work/github-telegram-status-ops.md
```

Если файл находится в ещё не отслеживаемом `docs/`, использовать:

```bash
git diff --no-index /dev/null docs/agent-work/github-telegram-status-ops.md
```
