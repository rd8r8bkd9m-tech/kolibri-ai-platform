# Отчет оператора GitHub Project

Дата проверки: 2026-06-29  
Роль: `github_project_operator`  
Репозиторий: `rd8r8bkd9m-tech/kolibri-ai-platform`  
Project: `#2`, `Kolibri AI Platform: фабрика ИИ и продукт на миллиарды`  
PR: `#46`, `[codex] Factory autonomy, PWA billing, remote FormulaLM`

Статус отчета: read-only сверка. GitHub Project, PR и issues не менялись.
Новые issues не создавались. FormulaLM/LLM эксперименты на Mac не запускались.

## 1. Что сверено

Проверены русские операционные документы:

- `docs/project-policy.md`;
- `docs/github-ci.md`;
- `docs/agent-work/github-project-ops.md`;
- `docs/agent-work/github-project-sync-report.md`;
- `docs/agent-work/github-telegram-status-ops.md`;
- `docs/agent-work/post-commit-github-sync.md`;
- смежные отчеты `docs/agent-work/release-status-20260629.md`,
  `docs/agent-work/ci-failure-triage.md`,
  `docs/agent-work/browser-preview-qa.md`,
  `docs/agent-work/server-kfrm-blocker-summary.md`.

Вывод: Project #2 и PR #46 уже отражены в русской операционной документации,
но часть документов описывает целевую русскую схему статусов
`Новая / В работе / На проверке / Заблокирована / Готово`, а фактическая схема
GitHub Project #2 сейчас имеет только `Todo / In Progress / Done`. До изменения
schema агенты должны использовать фактические значения поля `Status`, а
`review` и `blocked` фиксировать в issue/PR comments и поле `Артефакты`.

## 2. Read-only факты GitHub

Проверки через `gh` доступны: аккаунт авторизован, scope `project` есть.

Фактический Project #2:

- URL: `https://github.com/users/rd8r8bkd9m-tech/projects/2`;
- project id: `PVT_kwHODmcz_M4Bb728`;
- private, open;
- items: `10`;
- fields: `18`;
- поле `Status`: `Todo`, `In Progress`, `Done`;
- поля `Приоритет`, `Направление`, `Агент`, `Артефакты`,
  `Следующий отчёт` существуют.

Фактический PR #46:

- URL: `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46`;
- state: `OPEN`;
- draft: `true`;
- mergeable: `MERGEABLE`;
- head branch: `codex/factory-autonomy-pwa-billing`;
- head SHA на GitHub: `eadc04a07ca51812615f8b523c828d0fff1c136f`;
- base branch: `main`;
- commits: `2`;
- changed files: `56`;
- Project status: `Todo`;
- checks: два `Kolibri CI / ci` завершились `failure`;
- failed jobs:
  - `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28346968290/job/83972196451`;
  - `https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/actions/runs/28346987211/job/83972253483`.

## 3. Какие items используются

Project #2 сейчас содержит PR #46 и P0 issues:

| Item | Назначение | GitHub state | Project status сейчас | Операционный статус |
| --- | --- | --- | --- | --- |
| PR #46 | Общий PR для factory autonomy, PWA billing, remote FormulaLM и связанных docs | `OPEN`, draft | `Todo` | Должен быть `In Progress` до зеленого CI и review gate |
| Issue #47 | Документовод и developer portal на русском языке | `OPEN` | `Todo` | `In Progress`, пока docs в PR #46 не приняты |
| Issue #48 | Политика разработки Kolibri AI Platform | `OPEN` | `Todo` | `In Progress`, связать с policy/docs и этим отчетом |
| Issue #49 | Премиум-лендинг и SPA/PWA | `OPEN` | `Todo` | `In Progress`, блокируется build/visual/mobile evidence |
| Issue #50 | Живая птица Kolibri как state-machine персонаж | `OPEN` | `Todo` | `In Progress`, до runtime asset или принятого fallback evidence |
| Issue #51 | Инвесторский pipeline и outreach-пакет | `OPEN` | `Todo` | `In Progress`, external outreach не отправлять без owner review |
| Issue #52 | Runtime rollout фабрики и запуск серверных агентов | `OPEN` | `Todo` | `In Progress` с P0 blockers по node/runtime evidence |
| Issue #53 | Secondary Control Plane `/v1/tasks` summary timeout | `OPEN` | `Todo` | `In Progress` с blocker summary в `Артефакты` |
| Issue #54 | Desktop control app MVP | `OPEN` | `Todo` | `In Progress`, пока MVP/docs/envelope не приняты |
| Issue #55 | Stale `active_task` after lease expiry/dead_letter | `OPEN` | `Todo` | `In Progress` с blocker summary в `Артефакты` |

Ни один из этих items не должен переходить в `Done`, пока нет acceptance,
зеленых релевантных проверок, review/merge или явно принятого owner decision.

## 4. Что синхронизировать

Использовать только существующие поля Project. Не добавлять поля и не
переименовывать options без отдельного решения владельца.

| Item | Status | Приоритет | Направление | Агент | Следующий отчёт | Артефакты |
| --- | --- | --- | --- | --- | --- | --- |
| PR #46 | `In Progress` | `P0` | `GitHub/CI` | `github_project_operator`, `ci_failure_triage_agent` | ближайший P0 update | PR #46, head SHA, CI run URLs, `docs/agent-work/github-project-operator-report.md`, `docs/agent-work/ci-failure-triage.md` |
| #47 | `In Progress` | `P0` | `Документация` | `docs_steward` | ближайший P0 update | developer portal docs, PR #46, docs stewardship report |
| #48 | `In Progress` | `P0` | `Документация` | `docs_steward`, `github_project_operator` | ближайший P0 update | `docs/project-policy.md`, GitHub Project manuals, this report, PR #46 |
| #49 | `In Progress` | `P0` | `SPA/PWA` | `premium_ui_director`, `qa_lead` | ближайший P0 update | frontend files, build/mobile/visual evidence, PR #46 |
| #50 | `In Progress` | `P0` | `Живая птица` | `living_character_director` | ближайший P0 update | `docs/living-bird.md`, Rive/SVG fallback evidence, PR #46 |
| #51 | `In Progress` | `P0` | `Инвесторы` | `investor_sales_operator` | ближайший P0 update | `docs/investors.md`, outreach pack, PR #46, owner review state |
| #52 | `In Progress` | `P0` | `Фабрика` | `factory_runtime_sre`, `control_plane_envelope_integrator` | ближайший P0 update | rollout docs, node health evidence, #53, #55, PR #46 |
| #53 | `In Progress` | `P0` | `Фабрика` | `factory_runtime_sre` | ближайший P0 update | timeout evidence, `/health`, `/v1/nodes`, PR #46 |
| #54 | `In Progress` | `P0` | `Фабрика` | `desktop_control_operator` | ближайший P0 update | desktop MVP spec, envelope/report, related #49/#52 |
| #55 | `In Progress` | `P0` | `Фабрика` | `factory_runtime_sre` | ближайший P0 update | stale active_task evidence, related #53/#52, PR #46 |

Если CI остается красным, PR #46 остается `In Progress`; причина failure и
ссылки на jobs должны быть в PR comment и `Артефакты`. Если новая проверка
зеленая, PR можно переводить к review gate в комментариях, но Project status
остается `In Progress` до merge/acceptance, потому что отдельного `Review`
option нет.

## 5. Как агенты должны докладывать

Каждый агентский доклад в issue/PR должен быть на русском языке и содержать:

```text
Status: queued | running | review | blocked | done | cancelled
Project item: PR #46 / issue #...
Project sync: done | pending | blocked
Task: KOL-... или not_applicable
Report: docs/agent-work/...md
Что сделано: 1-3 факта
Что проверено: команды, CI/check URLs или "не запускалось" с причиной
Блокер: отсутствует или точная причина + кто снимает
Следующий шаг: одно действие
Следующий отчёт: дата/время Europe/Moscow
```

Для Project переносить только компактное:

- `Status`: `Todo`, `In Progress` или `Done`;
- `Приоритет`;
- `Направление`;
- `Агент`;
- `Следующий отчёт`;
- `Артефакты`: PR/issue/report/result/check URLs, без raw logs и секретов.

Telegram/owner-safe сводка, если нужна, не должна содержать `task_id`, node id,
локальные пути, raw stdout/stderr, traceback, секреты или OAuth details.

## 6. Правила статусов до изменения schema

| Канонический статус | Project #2 сейчас | Где писать подробность |
| --- | --- | --- |
| `queued` / `Новая` | `Todo` | issue/PR body |
| `running` / `В работе` | `In Progress` | issue/PR comment, `Агент`, `Следующий отчёт` |
| `review` / `На проверке` | `In Progress` | PR comment, reviewer/check evidence, `Артефакты` |
| `blocked` / `Заблокирована` | `In Progress` | issue/PR blocker comment, `Артефакты`, next owner/action |
| `done` / `Готово` | `Done` | только после acceptance evidence |
| `cancelled` | `Done` или `In Progress` | comment с owner decision |

Запрещено ставить `Done` для draft PR #46, issues #47-#55 или связанных P0
items только потому, что есть локальный отчет. Нужны GitHub-visible evidence,
review/merge или явное решение владельца.

## 7. Команды read-only проверки

Использованные проверки:

```bash
gh auth status
gh project view 2 --owner rd8r8bkd9m-tech --format json
gh project field-list 2 --owner rd8r8bkd9m-tech --format json
gh project item-list 2 --owner rd8r8bkd9m-tech --limit 100 --format json
gh pr view 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,isDraft,mergeable,url,headRefName,headRefOid,baseRefName,baseRefOid,commits,files,labels,reviewDecision,statusCheckRollup,projectItems
gh pr checks 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform
gh issue view 47 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
gh issue view 48 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
gh issue view 49 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
gh issue view 50 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
gh issue view 51 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
gh issue view 52 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
gh issue view 53 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
gh issue view 54 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
gh issue view 55 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,title,state,labels,assignees,comments,projectItems,url
```

Документационная проверка этого файла:

```bash
test -f docs/agent-work/github-project-operator-report.md
rg -n "Project #2|PR #46|Issue #55|Как агенты должны докладывать|Команды read-only" docs/agent-work/github-project-operator-report.md
```
