# Factory result integration plan

Дата: 2026-06-29  
Task: `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629`  
Result branch: `agent/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629/app-unblock`  
Base ref from envelope: `origin/main`  
Local working branch at handoff time: `codex/factory-autonomy-pwa-billing`

Цель: безопасно забрать результат factory task после статуса `completed`, сравнить его с текущими локальными frontend-изменениями и интегрировать без потери чужой работы. Не трогать live серверы, не запускать FormulaLM/LLM на Mac, не делать `stage/commit/push` до отдельного решения владельца.

## 0. Read-only preflight

Из корня репозитория:

```bash
cd /Users/kolibri/.codex/worktrees/6ff4/kolibri-ai-platform

bash -n scripts/factory_result_integration_check.sh
scripts/factory_result_integration_check.sh || true
git status --short --branch
```

Ожидаемое состояние для начала интеграции:

- task `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629` помечен как `completed` во внешнем источнике статуса;
- remote branch виден через `git ls-remote`;
- текущие локальные изменения осознаны и не будут перезаписаны;
- нет необходимости делать deploy, restart, SSH, Control Plane mutation или любые live-проверки.

Если branch еще не виден, остановиться. Не заменять это ручным `reset`, force-fetch или перезапуском factory task.

## 1. Зафиксировать локальный frontend baseline без stage/commit

Перед fetch/integration сохранить read-only снимки локального состояния:

```bash
mkdir -p /tmp/kolibri-factory-integration

git status --short --branch > /tmp/kolibri-factory-integration/status.before.txt
git diff -- frontend > /tmp/kolibri-factory-integration/local-frontend.before.patch
git diff --name-status -- frontend > /tmp/kolibri-factory-integration/local-frontend.files.txt
git diff --stat -- frontend > /tmp/kolibri-factory-integration/local-frontend.stat.txt
```

Если есть untracked frontend-файлы, отдельно записать список:

```bash
git ls-files --others --exclude-standard frontend > /tmp/kolibri-factory-integration/local-frontend.untracked.txt
```

Правило: не выполнять `git checkout`, `git reset`, `git clean` или операции, которые могут удалить untracked файлы в текущем worktree.

## 2. Получить result branch без переключения текущего worktree

После подтвержденного `completed`:

```bash
RESULT_BRANCH='agent/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629/app-unblock'
RESULT_REF="refs/remotes/origin/${RESULT_BRANCH}"

git ls-remote --heads origin "${RESULT_BRANCH}"
git fetch --no-tags origin "${RESULT_BRANCH}:${RESULT_REF}"
git log --oneline --decorate --max-count=12 "${RESULT_REF}"
git diff --name-status origin/main..."${RESULT_REF}"
```

Эти команды обновляют только remote-tracking ref результата и не меняют файлы текущего worktree.

## 3. Сравнить result branch с локальными frontend-изменениями

Сначала увидеть, что менял factory task:

```bash
git diff --stat origin/main..."${RESULT_REF}"
git diff --name-status origin/main..."${RESULT_REF}"
git diff -- frontend
git diff --name-status -- frontend
git diff --name-status origin/main..."${RESULT_REF}" -- frontend
```

Затем проверить пересечение файлов:

```bash
comm -12 \
  <(git diff --name-only -- frontend | sort) \
  <(git diff --name-only origin/main..."${RESULT_REF}" -- frontend | sort)
```

Если список пустой, риск frontend-конфликта ниже, но все равно проверить поведенческие контракты `/app`, PWA manifest, chat-first surface и right-bottom Control entrypoint.

Если список не пустой, открыть каждый файл обеими сторонами:

```bash
git diff -- frontend/src/App.jsx
git diff origin/main..."${RESULT_REF}" -- frontend/src/App.jsx
```

Заменить `frontend/src/App.jsx` на каждый файл из пересечения.

## 4. Интегрировать в отдельном worktree

Рекомендуемый путь: отдельный integration worktree, чтобы не трогать текущий грязный worktree.

```bash
BASE_BRANCH="$(git branch --show-current)"
INTEGRATION_BRANCH="codex/integrate-KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629"
INTEGRATION_DIR="../kolibri-ai-platform-integrate-KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629"

git worktree add -b "${INTEGRATION_BRANCH}" "${INTEGRATION_DIR}" "${BASE_BRANCH}"
cd "${INTEGRATION_DIR}"
```

Если `git worktree add` откажется из-за уже существующей директории или branch, не удалять ее автоматически. Проверить вручную:

```bash
git worktree list
git branch --list "${INTEGRATION_BRANCH}"
```

## 5. Cherry-pick или merge strategy

Предпочтение:

1. `cherry-pick` отдельных result commits, если branch линейный и содержит небольшие reviewable commits.
2. `merge --no-ff` result branch, если result содержит несколько связанных commits, merge commit или важно сохранить точную factory history.
3. Не использовать squash до ревью, если в result branch есть диагностические commits или blocker artifacts, которые помогают понять решение.

Осмотреть историю:

```bash
git log --oneline --decorate origin/main.."${RESULT_REF}"
git diff --stat origin/main..."${RESULT_REF}"
```

Cherry-pick dry run:

```bash
git cherry-pick --no-commit <commit-sha-1> <commit-sha-2>
git diff --check
git diff --stat
```

Если нужен merge:

```bash
git merge --no-ff --no-commit "${RESULT_REF}"
git diff --check
git diff --stat
```

После `--no-commit` остается возможность проверить результат до commit. Не делать commit/stage/push без отдельного разрешения.

## 6. Conflict rules

Правила разрешения конфликтов:

- Не использовать массово `--ours` или `--theirs` по всему frontend.
- Сохранять текущие локальные frontend-изменения, если они относятся к premium landing, PWA/mobile shell, billing UI или уже измененному chat-first UX, пока factory result не доказывает более узкий fix.
- Сохранять factory result, если он чинит P0 owner-facing `/app` path, Telegram Mini App compatibility, routing, runtime boot или минимальный unblock, и это не ломает текущие frontend-контракты.
- Для `frontend/src/App.jsx`, `frontend/src/App.css`, `frontend/index.html`, `frontend/public/manifest.webmanifest` проверять итог вручную, потому что это файлы с высоким риском пересечения.
- Не удалять untracked файлы из текущей разработки: `frontend/eslint.config.js`, новые компоненты, assets и docs считаются чужой работой, пока явно не доказано обратное.
- Не принимать generated/cache artifacts: `.playwright-cli/`, `dist/`, `node_modules/`, coverage, временные screenshots.
- Не менять ops queue state, envelopes других задач, live server configs или systemd/deploy файлы в рамках интеграции result branch.
- Если conflict связан с owner-facing UX, итог должен сохранить `/app` как chat-first surface и правый нижний Control entrypoint.
- Если смысл обеих сторон не ясен за 10-15 минут, остановиться и записать файл, конфликтующие hunks и варианты решения в integration notes.

После ручного разрешения:

```bash
git diff --check
git diff --name-only --diff-filter=U
git status --short
```

Список unresolved conflicts должен быть пустым.

## 7. Post-merge tests

Минимальный набор из task envelope:

```bash
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
python3 -m compileall -q backend ops
```

Дополнительные локальные проверки без live серверов:

```bash
python3 -m pytest tests/test_factory_runtime_queue_contracts.py tests/test_telegram_gateway.py -q
git diff --check
```

Если frontend dependencies не установлены:

```bash
npm --prefix frontend install
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
```

Не запускать FormulaLM/LLM benchmark на Mac. Не запускать deploy scripts. Не выполнять live HTTP checks, restart сервисов или Control Plane mutations в этой integration pass.

## 8. Review package перед stage/commit

Перед тем как просить разрешение на stage/commit/push:

```bash
git status --short --branch
git diff --stat
git diff --check
git diff --name-status
```

Сводка для владельца должна включать:

- result branch SHA;
- chosen strategy: cherry-pick или merge;
- список файлов, где были конфликты;
- что сохранено из локальных frontend-изменений;
- что принято из factory result;
- результаты post-merge tests;
- оставшиеся риски и rollback notes.

Stage/commit/push выполняются только после отдельного явного разрешения.
