# GitHub Project operating manual for agents

Роль: `github_project_operator`

Этот регламент описывает, как агенты Kolibri ведут GitHub Project, issues,
pull requests, Control Plane artifacts, инвесторский трек и документацию.
GitHub Project является внешним операционным экраном, а Control Plane остаётся
источником факта по задачам, lease, результатам и артефактам.

## 1. Назначение

GitHub Project нужен, чтобы владелец, агенты, reviewers и внешние участники
видели одну картину:

- какие задачи выполняются;
- какой агент или сервер отвечает;
- что заблокировано;
- где PR, CI, result artifact и следующий шаг;
- какие материалы нужны инвесторам и документации.

Project не заменяет:

- `result.json` и `artifact-manifest.json` Control Plane;
- PR description;
- issue acceptance criteria;
- inter-agent feed.

Если GitHub Project временно недоступен, агент всё равно пишет отчёт в issue
или PR и явно добавляет строку `Project sync: pending`.

## 2. Жёсткие правила

- Писать на русском языке.
- Докладывать фактами: что сделано, что проверено, что заблокировано, где
  артефакт, какой следующий шаг.
- Не коммитить и не публиковать секреты, токены, `.env`, приватные ключи,
  cookies, auth cache, персональные контактные данные инвесторов.
- Не откатывать чужие изменения.
- Не использовать GitHub Project как единственное место хранения результата:
  результат должен быть в PR, issue, документе или Control Plane artifact.
- Упавший CI не игнорировать: item переводится в `Заблокирована` или остаётся
  `В работе` с точной причиной и временем следующего отчёта.
- Если задача пришла из Control Plane, любой GitHub item обязан ссылаться на
  `task_id`.
- Если работа меняет код или docs, нужен PR. Если работа только фиксирует долг,
  исследование или follow-up, достаточно issue.
- Investor-facing claims должны быть привязаны к проверяемым artifacts, demo,
  PR, CI или документации.

## 3. Идентификаторы

Репозиторий:

```text
rd8r8bkd9m-tech/kolibri-ai-platform
```

Project:

```text
Kolibri AI Platform: фабрика ИИ и продукт на миллиарды
```

Рекомендуемые переменные для команд:

```bash
export KOLIBRI_REPO="rd8r8bkd9m-tech/kolibri-ai-platform"
export KOLIBRI_PROJECT_OWNER="rd8r8bkd9m-tech"
export KOLIBRI_PROJECT_TITLE="Kolibri AI Platform: фабрика ИИ и продукт на миллиарды"
export KOLIBRI_CONTROL_URL="http://10.99.0.2:9101"
```

Для работы с Projects у `gh` должен быть scope `project`:

```bash
gh auth status
gh auth refresh -s project
```

Если локальная политика OAuth требует отдельный read scope, добавить его в том
же refresh-процессе. При отсутствии scope агент не спорит с GitHub API, а
пишет issue/PR report и помечает `Project sync: pending`.

## 4. Поля GitHub Project

### 4.1 Обязательные поля

| Поле | Тип | Значения / формат | Правило заполнения |
| --- | --- | --- | --- |
| `Статус` | single select | `Новая`, `В работе`, `На проверке`, `Заблокирована`, `Готово` | Отражает текущее действие, а не оптимизм агента. |
| `Приоритет` | single select | `P0`, `P1`, `P2` | Ставится по impact и срочности. |
| `Направление` | single select | `Фабрика`, `SPA/PWA`, `FormulaLM`, `Сметы`, `Инвесторы`, `GitHub/CI`, `Документация`, `Живая птица`, `Мобильный слой` | Одно основное направление. |
| `Агент` | text | роль, agent id, node id или GitHub login | Кто сейчас отвечает за следующий шаг. |
| `Следующий отчёт` | date | дата следующего owner-visible update | Обязателен для `В работе` и `Заблокирована`. |
| `Артефакты` | text | PR, issue, result path, manifest path, report URL | Только ссылки и безопасные references. |

### 4.2 Дополнительные данные в body issue/PR

Пока в Project не заведены отдельные поля, эти данные фиксируются в body:

- `Control Plane task`;
- `Control Plane state`;
- `Branch`;
- `Commit`;
- `Verification`;
- `Risk`;
- `Project sync`;
- `Investor/docs visibility`.

Не добавлять новые Project fields без согласования владельца. Расширение полей
должно быть отдельным issue/PR, чтобы agents не расползались по разным схемам.

## 5. Статусы

### 5.1 Семантика статусов

| Статус | Когда ставить | Что должно быть в item |
| --- | --- | --- |
| `Новая` | Задача принята, но агент ещё не начал работу. | Цель, acceptance, направление, приоритет. |
| `В работе` | Есть активный агент, branch, lease или явный следующий шаг. | Агент, следующий отчёт, текущий прогресс. |
| `На проверке` | PR готов к review, CI идёт/прошёл, result ждёт независимой проверки. | PR/result artifact, проверки, reviewer или review task. |
| `Заблокирована` | Нужен внешний доступ, секрет, scope, инфраструктура, решение владельца, CI/root cause. | Блокер, кто снимает, что уже проверено, следующий отчёт. |
| `Готово` | Acceptance выполнен, artifact доступен, PR merged или issue закрыто. | Финальный результат, проверки, ссылки. |

### 5.2 Переходы

```text
Новая -> В работе -> На проверке -> Готово
В работе -> Заблокирована
На проверке -> В работе
Заблокирована -> В работе
Заблокирована -> Готово
```

Запрещено переводить item в `Готово`, если:

- нет ссылки на PR, issue, doc или Control Plane result;
- acceptance не закрыт;
- CI красный без объяснённого внешнего блокера;
- task завершился только словами агента без artifact.

### 5.3 Маппинг Control Plane -> Project

| Control Plane state | Project status | Комментарий |
| --- | --- | --- |
| `queued` | `Новая` | В Project указать причину ожидания, если routing узкий. |
| `leased` | `В работе` | Lease выдан, агент должен скоро прислать `task_started`. |
| `running` | `В работе` | Указать следующий отчёт. |
| `waiting_review` | `На проверке` | Нужен PR или review task. |
| `review` | `На проверке` | Reviewer отвечает за следующий шаг. |
| `completed` | `Готово` | Только после ссылки на artifact/result/PR. |
| `failed` | `Заблокирована` | Указать error type и artifact. |
| `retry_scheduled` | `В работе` | В body указать retry reason и попытку. |
| `dead_letter` | `Заблокирована` | Нужен operator decision. |
| `cancelled` | `Готово` или `Заблокирована` | `Готово`, если отмена была ожидаемым решением; иначе blocker. |

## 6. Приоритеты

| Priority | Когда ставить | SLA отчёта |
| --- | --- | --- |
| `P0` | Owner-visible outage, security/secrets risk, payment outage, Control Plane/Agent Host не принимает задачи, blocker для investor/demo в ближайшие 24 часа. | Сразу при обнаружении, затем каждые 30 минут или при каждом изменении факта. |
| `P1` | Текущий milestone, PR/CI блокирует merge, docs/investor artifact нужен в ближайшие 48 часов, production UX blocker. | При старте, каждые 2-4 часа в активной работе, при завершении. |
| `P2` | Плановые улучшения, documentation debt, research follow-up, polish, backlog. | При взятии в работу и при завершении; не реже одного раза в сутки. |

Если агент не может выдержать SLA, item переводится в `Заблокирована` или
передаётся другому агенту с комментарием handoff.

## 7. Направления

| Направление | Что входит |
| --- | --- |
| `Фабрика` | Control Plane, Agent Host, queues, leases, nodes, inter-agent feed, artifacts, factory SRE. |
| `SPA/PWA` | React app, UX, themes, chat-first flow, Control FAB, billing UX. |
| `FormulaLM` | Formula discovery, benchmarks, model experiments на удалённых серверах, deterministic overlay. |
| `Сметы` | Pricebook, deterministic estimates, document packs, region profiles. |
| `Инвесторы` | One-pagers, outreach, data room index, investor objections, demo readiness. |
| `GitHub/CI` | Project operations, Actions, PR hygiene, automation, branch/merge process. |
| `Документация` | `docs/`, runbooks, developer portal, API reference, guides. |
| `Живая птица` | Visual identity, living bird asset, brand behavior. |
| `Мобильный слой` | GoMesh, mobile/PWA readiness, mobile fallback. |

Если item затрагивает несколько направлений, выбрать то, где находится
следующий ответственный шаг. Остальные направления перечислить в body.

## 8. Ежедневный цикл оператора

1. Проверить Project items без `Следующий отчёт`.
2. Проверить `Заблокирована`: у каждого blocker должен быть owner/actionable
   next step.
3. Проверить `На проверке`: у каждого PR есть reviewer, CI status и критерий
   merge/return.
4. Проверить Control Plane:

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" nodes
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" status --limit 200
curl "$KOLIBRI_CONTROL_URL/v1/agent-messages?target=all&limit=100"
```

5. Синхронизировать completed/failed Control Plane tasks в GitHub issue/PR.
6. Проверить investor/docs items: нет ли публичных claims без artifact.
7. Закрыть или архивировать items, где PR merged и docs обновлены.

## 9. Добавление issue

Issue создаётся, когда:

- есть bug, docs debt, research task или operator follow-up;
- работа ещё не имеет branch/PR;
- Control Plane artifact требует GitHub-visible follow-up;
- investor/docs задача должна быть видна владельцу.

Минимальная команда:

```bash
gh issue create \
  --repo "$KOLIBRI_REPO" \
  --title "[Фабрика] Починить stale nodes после lease timeout" \
  --body-file issue.md \
  --project "$KOLIBRI_PROJECT_TITLE"
```

Если project scope недоступен:

```bash
gh issue create \
  --repo "$KOLIBRI_REPO" \
  --title "[Фабрика] Починить stale nodes после lease timeout" \
  --body-file issue.md
```

После этого добавить в body или comment:

```text
Project sync: pending
Reason: missing gh project scope
```

### 9.1 Правила issue title

Формат:

```text
[Направление] Глагол + измеримый результат
```

Примеры:

```text
[GitHub/CI] Добавить blocker report для красного CI
[Документация] Обновить runbook Control Plane artifacts
[Инвесторы] Подготовить публичный one-pager без confidential данных
```

### 9.2 Issue body обязателен

В issue должны быть:

- контекст;
- цель;
- acceptance criteria;
- ссылки на Control Plane task/artifacts, если есть;
- риск;
- что считать готовым;
- владелец следующего шага.

## 10. Добавление PR

PR создаётся, когда есть изменения в коде, docs, configs, CI или artifacts,
которые должны попасть в репозиторий.

Ветки агентов:

```text
agent/<TASK_ID>/<short-slug>
codex/<short-slug>
```

Для Control Plane задач предпочтителен формат `agent/<TASK_ID>/<short-slug>`.

Минимальная команда:

```bash
gh pr create \
  --repo "$KOLIBRI_REPO" \
  --draft \
  --title "[Документация] Добавить GitHub Project ops manual" \
  --body-file pr.md \
  --project "$KOLIBRI_PROJECT_TITLE"
```

Если PR полностью закрывает issue, использовать `Closes #123`. Если только
связан, использовать `Refs #123`.

PR переводится из draft в ready только когда:

- acceptance выполнен;
- проверки запущены или честно указано, почему не запускались;
- нет скрытого blocker;
- PR body содержит Control Plane/task/artifact ссылки, если они есть.

## 11. Добавление существующего issue/PR в Project

Получить номер Project:

```bash
gh project list --owner "$KOLIBRI_PROJECT_OWNER"
```

Добавить item по URL:

```bash
gh project item-add "$KOLIBRI_PROJECT_NUMBER" \
  --owner "$KOLIBRI_PROJECT_OWNER" \
  --url "https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/123"
```

Посмотреть поля:

```bash
gh project field-list "$KOLIBRI_PROJECT_NUMBER" \
  --owner "$KOLIBRI_PROJECT_OWNER"
```

Посмотреть items:

```bash
gh project item-list "$KOLIBRI_PROJECT_NUMBER" \
  --owner "$KOLIBRI_PROJECT_OWNER" \
  --format json
```

Редактирование полей через CLI требует `project-id`, `item-id`, `field-id` и
option id. Если эти ID не подготовлены, агент обновляет issue/PR comment и
оставляет `Project field update: pending`.

Пример text-field update:

```bash
gh project item-edit \
  --id "$PROJECT_ITEM_ID" \
  --project-id "$PROJECT_ID" \
  --field-id "$ARTIFACTS_FIELD_ID" \
  --text "PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/123"
```

## 12. Синхронизация Control Plane artifacts

### 12.1 Источник факта

Для задач фабрики Control Plane является источником:

- `task_id`;
- lifecycle state;
- `node_id`;
- `attempt_id`;
- branch/commit/push status;
- `result_path`;
- `artifact-manifest.json`;
- stdout/stderr references;
- error type.

GitHub хранит безопасную выжимку и ссылки, а не все node-local payloads.

### 12.2 Команды чтения

```bash
ops/kolibri-dispatch --control-url "$KOLIBRI_CONTROL_URL" status "$TASK_ID" --full
curl "$KOLIBRI_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=200"
curl "$KOLIBRI_CONTROL_URL/v1/agent-messages?target=all&limit=100"
```

### 12.3 Что переносить в GitHub

В issue/PR comment или body переносить:

- `task_id`;
- `state`;
- `node_id` только если это полезно для диагностики;
- branch;
- commit;
- PR URL;
- result artifact reference;
- manifest reference;
- verification commands;
- blocker/error summary;
- next step.

Не переносить:

- секреты;
- auth file content;
- полные приватные logs без редактуры;
- персональные investor контакты;
- большие raw payloads;
- приватные local paths в owner-facing summary, если они не нужны для debug.

### 12.4 Project sync для completed task

1. Найти issue/PR по `task_id`.
2. Если нет issue/PR, создать issue или PR в зависимости от результата.
3. Добавить comment с result summary.
4. Обновить `Артефакты`.
5. Перевести `Статус`:
   - `completed` -> `На проверке`, если нужен review;
   - `completed` -> `Готово`, если acceptance закрыт и review не нужен;
   - `failed`/`dead_letter` -> `Заблокирована`.
6. Поставить `Следующий отчёт`, если item не `Готово`.

### 12.5 Artifact-first правило

Агент не пишет "готово" без artifact. Минимальный artifact reference:

```text
Control Plane task: KOL-DOCS-STEWARD-20260629
State: completed
Branch: agent/KOL-DOCS-STEWARD-20260629/docs
Commit: abc123
Result: /var/lib/kolibri-agent/artifacts/.../result.json
Manifest: /var/lib/kolibri-agent/artifacts/.../artifact-manifest.json
Verification: python3 -m compileall -q backend ops scripts
```

## 13. Инвесторский трек

### 13.1 Что вести в Project

В Project вести только operational items:

- подготовить one-pager;
- обновить data room index;
- собрать demo evidence;
- подготовить investor FAQ;
- закрыть technical diligence вопрос;
- подготовить follow-up после встречи.

Не вести в публичном issue:

- персональные телефоны, email, личные профили;
- условия сделки;
- конфиденциальные оценки, cap table, финансовые обещания;
- непроверенные claims.

### 13.2 Видимость

Каждый investor item должен иметь строку:

```text
Investor/docs visibility: public / private-summary / private-only
```

Правила:

- `public`: можно публиковать в issue/PR без редактуры;
- `private-summary`: в GitHub только краткая безопасная выжимка и ссылка на
  приватный источник;
- `private-only`: в GitHub только факт наличия follow-up без деталей.

### 13.3 Связь с artifacts

Investor claims должны ссылаться на:

- docs page;
- PR;
- CI result;
- demo URL;
- Control Plane result;
- sanitized report.

Если claim нельзя подтвердить artifact, он не попадает в investor message.

## 14. Документация

Документация ведётся на русском языке и должна быть проверяемой.

Docs item создаётся, когда:

- появилась новая API/CLI команда;
- изменился Control Plane contract;
- появился новый runbook или known gap;
- PR меняет пользовательский flow;
- investor/customer materials требуют публичной версии;
- automation обнаружила устаревший документ.

Docs PR должен содержать:

- какие документы изменены;
- откуда взят источник факта;
- как проверялись команды/ссылки;
- какие документы остались follow-up.

Если документ описывает поведение, которого ещё нет в коде, явно писать:

```text
Implementation status: planned / partial / implemented
```

## 15. CI и review

Для PR item:

- `На проверке` означает, что reviewer может действовать без дополнительного
  сбора контекста;
- красный CI переводит item в `В работе` или `Заблокирована`;
- внешний сбой CI описывается как blocker с ссылкой на job/log;
- после fix commit агент публикует короткий comment: что изменилось и какую
  проверку перезапустить.

Минимальный review-ready набор:

```text
PR URL:
Related issue:
Control Plane task:
Changed files:
Verification:
Known risks:
Reviewer request:
```

## 16. Handoff

Handoff обязателен, если:

- агент теряет доступ к нужному scope/секрету;
- node stale;
- задача переходит другому role_slot;
- item остаётся blocked дольше SLA;
- investor/docs follow-up должен делать другой владелец.

Handoff comment должен содержать:

- текущий статус;
- что уже проверено;
- что не трогать;
- какие файлы изменены;
- где artifacts;
- следующий конкретный шаг.

## 17. Шаблоны сообщений

### 17.1 Project update

```markdown
Status: В работе
Priority: P1
Direction: Фабрика
Agent: factory_sre / node-a
Next report: 2026-06-29 18:30 Europe/Moscow

Что сделано:
- Проверил `/v1/nodes` и очередь задач.
- Нашёл stale node и задачу в `leased` без свежего heartbeat.

Что проверено:
- `ops/kolibri-dispatch --control-url $KOLIBRI_CONTROL_URL nodes`
- `ops/kolibri-dispatch --control-url $KOLIBRI_CONTROL_URL status --limit 200`

Блокеры:
- Нет, продолжаю drain/retry.

Артефакты:
- Control Plane task: KOL-FACTORY-...
- Result/manifest: pending

Следующий шаг:
- Дождаться lease expiry, затем перевести item в `На проверке` или `Заблокирована`.
Project sync: done
```

### 17.2 Blocker report

```markdown
Status: Заблокирована
Priority: P0
Direction: GitHub/CI
Agent: github_project_operator
Next report: 2026-06-29 19:00 Europe/Moscow

Блокер:
- `gh project` не может добавить item: отсутствует OAuth scope `project`.

Что уже проверено:
- `gh auth status`
- `gh project item-add ...`

Влияние:
- Issues/PR создаются, но Project fields не обновляются автоматически.

Что нужно:
- Выполнить `gh auth refresh -s project` под владельцем токена.

Временный обход:
- Пишу отчёты в issue/PR comments с `Project sync: pending`.
```

### 17.3 Issue body

````markdown
## Контекст

Коротко: почему задача появилась и кто её запросил.

## Цель

Измеримый результат в 1-3 предложениях.

## Acceptance criteria

- [ ] Критерий 1.
- [ ] Критерий 2.
- [ ] Есть ссылка на artifact/result/PR.

## Control Plane

- Task: KOL-...
- State: queued/running/completed/failed
- Node/agent: ...
- Result/manifest: ...

## Проверка

```bash
command
```

## Риски и блокеры

- Риск:
- Блокер:

## Project

- Status: Новая
- Priority: P1
- Direction: ...
- Agent: ...
- Next report: YYYY-MM-DD HH:MM Europe/Moscow
- Project sync: done/pending
````

### 17.4 PR body

````markdown
## Что сделано

- ...

## Зачем

- ...

## Проверки

```bash
command
```

## Control Plane / artifacts

- Task: KOL-...
- Branch: agent/KOL-.../...
- Commit: ...
- Result: ...
- Manifest: ...

## Риски

- ...

## Блокеры

- Нет / ...

## Связанные items

Refs #123

## Project

- Status: На проверке
- Priority: P1
- Direction: ...
- Agent: ...
- Next report: YYYY-MM-DD HH:MM Europe/Moscow
- Project sync: done/pending
````

### 17.5 Control Plane result sync comment

```markdown
Control Plane sync:

- Task: KOL-...
- State: completed
- Attempt: KOL-...-attempt-1
- Agent/node: ...
- Branch: ...
- Commit: ...
- PR: ...
- Result: ...
- Manifest: ...

Verification:
- `...`

Decision:
- Перевожу Project item в `На проверке`, потому что нужен reviewer.
```

### 17.6 Investor update

```markdown
Status: В работе
Priority: P1
Direction: Инвесторы
Agent: investor_sales_operator
Next report: 2026-06-29 20:00 Europe/Moscow
Investor/docs visibility: private-summary

Что сделано:
- Подготовлен безопасный тезис для one-pager.
- Проверил, что claims связаны с docs/PR/artifacts.

Что не публикуем:
- Персональные контакты, условия сделки, конфиденциальные notes.

Артефакты:
- One-pager draft: ...
- Evidence PR/docs: ...

Следующий шаг:
- Подготовить follow-up без непроверенных claims.
Project sync: done
```

### 17.7 Docs update

```markdown
Status: На проверке
Priority: P2
Direction: Документация
Agent: docs_steward
Next report: 2026-06-30 12:00 Europe/Moscow
Implementation status: implemented

Что обновлено:
- `docs/...`

Источник факта:
- Код: `ops/...`
- Existing docs: `docs/...`
- Control Plane artifact: ...

Проверка:
- Ссылки/команды просмотрены.
- Mermaid/code fences не содержат секретов.

Follow-up:
- ...
Project sync: done
```

### 17.8 Handoff

```markdown
Handoff:

- Current status: Заблокирована
- Owner/agent: github_project_operator -> factory_sre
- Task/issue/PR: ...
- Что сделано: ...
- Что проверено: ...
- Что не трогать: ...
- Артефакты: ...
- Следующий шаг: ...
- Next report: YYYY-MM-DD HH:MM Europe/Moscow
```

## 18. Быстрый checklist агента

Перед завершением работы агент проверяет:

- [ ] Есть issue или PR для значимой работы.
- [ ] Project item добавлен или отмечен `Project sync: pending`.
- [ ] `Статус`, `Приоритет`, `Направление`, `Агент`, `Следующий отчёт`,
      `Артефакты` заполнены.
- [ ] Для Control Plane задачи указан `task_id`.
- [ ] Есть artifact/result/manifest или честный blocker.
- [ ] PR содержит проверки и риски.
- [ ] Investor/docs visibility указана, если item касается инвесторов.
- [ ] Нет секретов и приватных contact details.
- [ ] Чужие изменения не откатывались.
