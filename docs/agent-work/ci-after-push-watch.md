# CI after-push watch: PR #46

Роль: `ci_after_push_watch`
Понятное русское название: Наблюдатель CI после push
Дата подготовки: 2026-06-29
Репозиторий: `rd8r8bkd9m-tech/kolibri-ai-platform`
PR: `#46`
Статус этого файла: подготовлен локально. GitHub не вызывался, код не менялся.

## 1. Назначение

Этот пакет нужен после того, как главный агент сделает commit и push в ветку
PR #46. Наблюдатель должен дождаться checks именно на новом SHA, отличить
новые результаты от старого красного head и дать короткий, безопасный статус в
GitHub и Telegram.

Не называть PR готовым, пока нет нового зеленого `Kolibri CI / ci` на новом
SHA и пока не приложены обязательные evidence для review path.

## 2. Исходные локальные факты

Источник фактов: локальные документы `docs/agent-work/ci-failure-triage.md`,
`docs/agent-work/github-project-sync-report.md`,
`docs/agent-work/post-commit-github-sync.md` и текущий worktree.

- PR #46 открыт для ветки `codex/factory-autonomy-pwa-billing`.
- Последний известный опубликованный GitHub head: `eadc04a07ca51812615f8b523c828d0fff1c136f`.
- На этом head были красные runs одного workflow/job:
  - `Kolibri CI / ci`, event `push`, run `28346968290`, job `83972196451`.
  - `Kolibri CI / ci`, event `pull_request`, run `28346987211`, job `83972253483`.
- Оба падения были в шаге `Pytest tests`.
- Root cause: `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`
  ожидал строку `Фабрика Колибри` в `frontend/src/App.jsx`.
- В текущем локальном worktree fix уже присутствует:
  - `frontend/src/App.jsx` содержит `const PRODUCT_TITLE = "Фабрика Колибри"`.
  - `PRODUCT_TITLE` передается в `AppHeader`.
  - `frontend/src/components/AppHeader.jsx` рендерит `productTitle`.
- Локальная targeted-проверка, зафиксированная ранее в Python 3.12 venv:
  `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`
  прошла как `1 passed`.
- Важно: локальный default `python3` может быть Python 3.14, это не CI-equivalent
  среда для pinned backend dependencies. Для CI-сопоставимой проверки нужен
  Python 3.12, как в GitHub Actions.

## 3. Что смотреть после нового SHA

Сначала получить новый SHA от главного агента:

```bash
git rev-parse HEAD
```

Дальше все проверки должны относиться к `<NEW_SHA>`, а не к старому
`eadc04a07ca51812615f8b523c828d0fff1c136f`.

Основной check:

- Workflow: `Kolibri CI`.
- Job/check name: `ci`, отображается как `Kolibri CI / ci`.
- Events, которые ожидаем после push:
  - `push` на ветку `codex/factory-autonomy-pwa-billing`;
  - `pull_request` для PR #46.

Внутри job смотреть шаги по порядку:

1. `Checkout`.
2. `Set up Python`, Python `3.12`.
3. `Python syntax compile`.
4. `Pytest tests`.
5. `Set up Node`, если есть `frontend/package.json`.
6. `JavaScript and TypeScript checks`.
7. `JSON and YAML validation`.
8. `Secret scan`.
9. `Production secret path guard`.
10. `Local component smoke`.

Если `Pytest tests` снова красный, сначала искать regression в:

- `tests/test_factory_status.py`;
- `frontend/src/App.jsx`;
- `frontend/src/components/AppHeader.jsx`;
- строках `Фабрика Колибри`, `/api/factory/status`, `/cluster/status`,
  `на базе 5 серверов`.

Если pytest зеленый, но падает дальше, уже смотреть следующий фактический шаг:
frontend build/lint, JSON/YAML, secret scan, production secret path guard или
smoke.

## 4. Безопасные `gh` команды для будущего оператора

Команды ниже read-only или watch-only. В этом docs-only проходе они не
запускались.

```bash
gh auth status
gh pr view 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform \
  --json number,url,title,headRefName,headRefOid,baseRefName,isDraft,state,mergeable,statusCheckRollup
gh pr checks 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform \
  --json name,state,bucket,link,startedAt,completedAt,workflow
gh pr checks 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform --watch
gh run list --repo rd8r8bkd9m-tech/kolibri-ai-platform \
  --branch codex/factory-autonomy-pwa-billing --limit 10 \
  --json databaseId,displayTitle,event,headSha,status,conclusion,workflowName,url,createdAt,updatedAt
gh run view <RUN_ID> --repo rd8r8bkd9m-tech/kolibri-ai-platform \
  --json databaseId,name,workflowName,status,conclusion,event,headSha,url,jobs
gh run view <RUN_ID> --repo rd8r8bkd9m-tech/kolibri-ai-platform --log-failed
```

Допустимый локальный фильтр логов после `gh run view ... --log-failed`:

```bash
rg -C 8 "FAILED|ERROR|test_frontend_uses_live_factory_status_endpoint|Фабрика Колибри|Secret scan failed|Production secret path guard failed|npm ERR|vite"
```

Не выполнять из этого watch без отдельного подтверждения владельца или главного
агента:

- `gh run rerun`, `gh run cancel`;
- `gh workflow run`;
- `gh pr comment`, `gh issue comment`, `gh pr review`;
- `gh pr ready`, `gh pr merge`, `gh pr close`;
- любые Project write/update команды;
- любые token/auth refresh/login команды.

## 5. Локальные проверки перед push или сразу после commit

Эти команды не требуют GitHub и полезны главному агенту перед push:

```bash
/tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint
/tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q tests/test_factory_status.py
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
```

Если Python 3.12 venv отсутствует, создать новый вне репозитория:

```bash
/opt/homebrew/bin/python3.12 -m venv /tmp/kolibri-ci-watch-312-venv
/tmp/kolibri-ci-watch-312-venv/bin/python -m pip install -r backend/requirements.txt pytest
/tmp/kolibri-ci-watch-312-venv/bin/python -m pytest -q tests/test_factory_status.py
```

## 6. Как интерпретировать результат CI

### Зеленый на новом SHA

Условия:

- `gh pr view 46 ... headRefOid` равен `<NEW_SHA>`.
- `Kolibri CI / ci` завершился `success` для нового `<NEW_SHA>`.
- Старые красные runs на `eadc04a...` не используются как текущий статус.

Вывод:

- Старый known failure считается снятым.
- PR #46 можно держать в `In Progress` или переводить в review path, но не
  `Done`, пока нет review/acceptance evidence.

### Красный на новом SHA

Условия:

- `headRefOid` равен `<NEW_SHA>`.
- `Kolibri CI / ci` завершился `failure`, `cancelled` или `timed_out`.

Действие:

- Зафиксировать failing step и run URL.
- Не закрывать P0 issues.
- Не ставить Project `Done`.
- Если ошибка снова в `test_frontend_uses_live_factory_status_endpoint`, явно
  указать, что локальный title fix не попал в pushed SHA или был сломан новым
  изменением.

### Pending долго

Условия:

- Новый SHA виден в PR, но checks еще `pending` или runs не появились.

Действие:

- Писать `CI pending on <NEW_SHA>`.
- Не делать rerun/cancel без отдельного решения.
- Следующий отчет поставить через 15-30 минут MSK.

## 7. GitHub comment templates

### PR #46, pending

```markdown
CI watch after push for `<NEW_SHA>`.

Status: pending
Report: `docs/agent-work/ci-after-push-watch.md`

Previous red head: `eadc04a07ca51812615f8b523c828d0fff1c136f`.
Previous root cause: `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint` expected `Фабрика Колибри` in `frontend/src/App.jsx`.

Current action: waiting for new `Kolibri CI / ci` checks on `<NEW_SHA>`.
Project recommendation: keep PR #46 `In Progress`, not `Done`.
Next report: `<NEXT_REPORT_AT_MSK>`.
```

### PR #46, green

```markdown
CI watch after push for `<NEW_SHA>`.

Status: green
Report: `docs/agent-work/ci-after-push-watch.md`

`Kolibri CI / ci` is green on the new SHA.
The previous pytest guard failure from `eadc04a07ca51812615f8b523c828d0fff1c136f` is cleared.

Remaining gates before ready/done: review path, visual/browser evidence, server-kfrm blocker status if release readiness is being claimed.
Project recommendation: keep/move PR #46 to `In Progress` with review/CI evidence, not `Done` until acceptance is complete.
```

### PR #46, red

```markdown
CI watch after push for `<NEW_SHA>`.

Status: red
Report: `docs/agent-work/ci-after-push-watch.md`

Failing check: `<CHECK_NAME>`
Failing step: `<FAILING_STEP>`
Run: `<RUN_URL>`
Root cause summary: `<ONE_OR_TWO_SENTENCES>`

Known old failure:
- Old head `eadc04a07ca51812615f8b523c828d0fff1c136f` failed because `Фабрика Колибри` was missing from `frontend/src/App.jsx`.
- Local worktree had a candidate fix before push. If the same guard failed again, verify that `<NEW_SHA>` includes `PRODUCT_TITLE = "Фабрика Колибри"`.

Next action: `<OWNER_OR_AGENT_AND_COMMAND>`
Next report: `<NEXT_REPORT_AT_MSK>`
Project recommendation: keep PR #46 `In Progress`, not `Done`.
```

## 8. Telegram templates

Telegram получает только owner-safe summary. Не писать task ids, node ids,
локальные пути, logs, scopes, stack traces, токены или внутренние run payloads.

Pending:

```text
На проверке. Новый коммит отправлен, я жду свежие CI-проверки PR #46 и не буду называть задачу готовой до зеленого результата.
```

Green:

```text
CI зеленый на новом коммите PR #46. Старое падение проверки снято; дальше остается review и продуктовые evidence перед статусом "готово".
```

Red:

```text
CI снова красный на новом коммите PR #46. Я зафиксировал упавший шаг в GitHub и веду разбор причины; статус остается "в работе".
```

Pending too long:

```text
CI для нового коммита PR #46 еще не завершился. Я продолжаю наблюдение и вернусь со статусом после результата проверок.
```

## 9. Что не писать

- Не писать `готово`, `release-ready`, `можно мержить` только из-за одного
  локального targeted test.
- Не смешивать старые красные runs `eadc04a...` с новым SHA.
- Не публиковать raw logs в Telegram.
- Не публиковать секреты, env names, auth scopes, локальные абсолютные пути или
  внутренние node identifiers.
- Не обещать server-kfrm, visual QA, billing или Telegram live delivery как
  закрытые, если проверка относится только к GitHub CI.

## 10. Проверка этого файла

Локальные docs-only проверки:

```bash
test -f docs/agent-work/ci-after-push-watch.md
rg -n "Наблюдатель CI после push|PR #46|Kolibri CI / ci|gh pr checks|Фабрика Колибри|Telegram" docs/agent-work/ci-after-push-watch.md
git diff -- docs/agent-work/ci-after-push-watch.md
git status --short docs/agent-work/ci-after-push-watch.md
```

Ограничение этого прохода: GitHub не вызывался, поэтому live status PR #46 и
новые Actions runs должны быть проверены только после фактического push.
