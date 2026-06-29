# GitHub main sync report

Дата проверки: 2026-06-29, Europe/Moscow
Роль: Оператор GitHub main sync
Репозиторий: `rd8r8bkd9m-tech/kolibri-ai-platform`
Целевая PR-ветка: `codex/factory-autonomy-pwa-billing`
PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46

## Короткий вывод

`main` не отражает актуальное состояние PR-ветки потому, что PR #46 остается открытым и находится в draft-состоянии. Git-расхождение прямое: `origin/main` является merge-base и предком `origin/codex/factory-autonomy-pwa-billing`; в PR-ветке есть 25 коммитов поверх `origin/main`, а обратных коммитов в `main` нет.

Технически ветка готова к чистому merge по состоянию refs: `git merge-tree --write-tree origin/main origin/codex/factory-autonomy-pwa-billing` завершился успешно и вернул дерево результата `f2aeccf8893bfb861803babe4a5962172b93f2ac`. GitHub MCP также показывает `mergeable=true`.

Merge в `main` не выполнялся и не должен выполняться без отдельного явного разрешения владельца.

## Состояние refs после fetch

Команда обновления refs:

```bash
git fetch --prune origin '+refs/heads/main:refs/remotes/origin/main' '+refs/heads/codex/factory-autonomy-pwa-billing:refs/remotes/origin/codex/factory-autonomy-pwa-billing'
```

Текущее состояние:

- `origin/main`: `6d0317c52a9694448ee2c352dc196ce7a27b9487`
- Последний коммит `origin/main`: `6d0317c5 2026-06-28T03:15:03+03:00 Merge pull request #45 from rd8r8bkd9m-tech/codex/version-mesh-control-bridge`
- `origin/codex/factory-autonomy-pwa-billing`: `8222c179cc7df34caf60565c797ba8c55829dd78`
- Локальный `HEAD`: `8222c179cc7df34caf60565c797ba8c55829dd78`
- Текущая локальная ветка: `codex/factory-autonomy-pwa-billing`, tracking `origin/codex/factory-autonomy-pwa-billing`

Рабочее дерево до отчета было грязным в runtime/test/docs/ops файлах, не относящихся к этому заданию. Для merge-решения это не мешает, потому что сравнение выполнено по remote-tracking refs. Для любых локальных проверок перед merge нужен чистый временный worktree.

## Метаданные PR #46

Через GitHub MCP:

- URL: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46
- Title: `[codex] Factory autonomy, PWA billing, remote FormulaLM`
- State: `open`
- Draft: `true`
- Base: `main`
- Base SHA: `6d0317c52a9694448ee2c352dc196ce7a27b9487`
- Head: `codex/factory-autonomy-pwa-billing`
- Head SHA: `8222c179cc7df34caf60565c797ba8c55829dd78`
- GitHub `mergeable`: `true`
- PR commits: `25`
- Changed files: `232`
- Additions/deletions: `43223` / `700`
- GitHub tentative merge commit SHA: `32e7e31803a75f282a2292b91fcc0ad5e9ac1c51`

## Расхождение main и PR-ветки

Команды:

```bash
git merge-base origin/main origin/codex/factory-autonomy-pwa-billing
git rev-list --left-right --count origin/main...origin/codex/factory-autonomy-pwa-billing
git rev-list --ancestry-path --count origin/main..origin/codex/factory-autonomy-pwa-billing
git merge-base --is-ancestor origin/main origin/codex/factory-autonomy-pwa-billing
```

Результаты:

- Merge-base: `6d0317c52a9694448ee2c352dc196ce7a27b9487`
- Ahead/behind относительно `origin/main...origin/codex/factory-autonomy-pwa-billing`: `0 25`
- Ancestry path count: `25`
- `origin/main` является предком PR-ветки: exit code `0`

Коммиты, которые есть в PR-ветке и отсутствуют в `origin/main`:

```text
8222c179 2026-06-29T12:01:30+03:00 factory: speed up control plane task listing
aa3e551f 2026-06-29T11:56:12+03:00 factory: recover empty agent runner responses
801d28a2 2026-06-29T11:46:03+03:00 factory: make telegram reports readable
a062eeaa 2026-06-29T11:36:21+03:00 factory: alert on deliverable gate failures
5432ae6d 2026-06-29T11:28:52+03:00 factory: surface deliverable gate failures
d611ae2c 2026-06-29T11:11:52+03:00 factory: require deliverable evidence
fb7b4846 2026-06-29T11:06:08+03:00 factory: format telegram status messages
ed52d968 2026-06-29T10:58:21+03:00 factory: surface watchdog rollup in control panel
522b7e27 2026-06-29T10:51:49+03:00 factory: roll up lease watchdog history
b41ea75d 2026-06-29T10:46:58+03:00 factory: notify lease watchdog on action
23d431be 2026-06-29T10:41:44+03:00 factory: schedule lease watchdog
15e43258 2026-06-29T10:35:29+03:00 factory: sweep stuck task leases
bb6204b6 2026-06-29T10:30:03+03:00 factory: index task state queries
21cf9521 2026-06-29T10:18:58+03:00 factory: surface live cluster summary
cf1a6a2f 2026-06-29T09:46:01+03:00 factory: summarize canonical cluster nodes
4d20addd 2026-06-29T09:36:10+03:00 factory: capture runner-created git results
e5a5b941 2026-06-29T09:33:05+03:00 factory: report all agent check to telegram
3b03e542 2026-06-29T09:27:12+03:00 factory: record home runtime parity probes
972f38eb 2026-06-29T09:03:47+03:00 factory: refresh watchdog after task submit
d3920329 2026-06-29T09:02:58+03:00 factory: add execution reports and machine tasks
4fd32d3d 2026-06-29T08:40:35+03:00 factory: add self contained p0 verify task
a009c067 2026-06-29T08:34:07+03:00 factory: refresh watchdog and integration guidance
85b973cd 2026-06-29T08:33:04+03:00 factory: land autonomy pwa billing rollout bundle
eadc04a0 2026-06-29T06:36:34+03:00 factory: target eighty percent utilization
4ed99805 2026-06-29T06:35:46+03:00 factory: enable autonomous pwa and remote formulalm
```

Коммиты, которые есть в `origin/main` и отсутствуют в PR-ветке: нет.

## Конфликты и mergeability

Проверки:

```bash
git merge-tree --write-tree origin/main origin/codex/factory-autonomy-pwa-billing
git merge-tree $(git merge-base origin/main origin/codex/factory-autonomy-pwa-billing) origin/main origin/codex/factory-autonomy-pwa-billing
```

Результат:

- `merge-tree --write-tree`: exit code `0`, result tree `f2aeccf8893bfb861803babe4a5962172b93f2ac`
- Текстовых конфликтов не обнаружено.
- GitHub MCP: `mergeable=true`.

Так как `origin/main` является предком head PR-ветки, локально возможен fast-forward с `6d0317c5` на `8222c179`. Для безопасного GitHub-процесса предпочтительнее merge через PR #46 с expected head SHA, а не прямой update ref `main`.

## Наблюдаемые проверки

Через GitHub MCP для head SHA `8222c179cc7df34caf60565c797ba8c55829dd78`:

- Workflow: `Kolibri CI`
- Run number: `192`
- Status: `completed`
- Conclusion: `success`
- Workflow id: `302046771`
- Classic combined commit statuses: пустой список

Локальная patch sanity:

```bash
git diff --shortstat origin/main...origin/codex/factory-autonomy-pwa-billing
```

Результат: `232 files changed, 43223 insertions(+), 700 deletions(-)`.

```bash
git diff --check origin/main...origin/codex/factory-autonomy-pwa-billing
```

Результат: exit code `2`. Обнаружены trailing whitespace и blank line at EOF в ряде добавленных/измененных markdown-документов, например:

- `docs/agent-work/agent-registry-ru.md`
- `docs/agent-work/automation-control-plane-10-pack.md`
- `docs/agent-work/formulalm-remote-rd-pack.md`
- `docs/agent-work/pr46-green-ci-status.md`
- `docs/agent-work/sales-investor-client-pipeline.md`
- `docs/desktop-control-app.md`

Это не текстовый merge-конфликт и не runtime-код, но перед production merge стоит либо исправить docs whitespace отдельным docs-only follow-up commit в PR-ветке, либо явно принять это как не-блокирующий форматный долг, если branch protection не требует `git diff --check`.

## Проверки, нужные перед merge

1. Еще раз обновить refs непосредственно перед решением:

```bash
git fetch --prune origin '+refs/heads/main:refs/remotes/origin/main' '+refs/heads/codex/factory-autonomy-pwa-billing:refs/remotes/origin/codex/factory-autonomy-pwa-billing'
git rev-parse origin/main origin/codex/factory-autonomy-pwa-billing
```

2. Если `origin/main` или head PR изменились, повторить:

```bash
git merge-base origin/main origin/codex/factory-autonomy-pwa-billing
git rev-list --left-right --count origin/main...origin/codex/factory-autonomy-pwa-billing
git merge-tree --write-tree origin/main origin/codex/factory-autonomy-pwa-billing
```

3. Проверить, что PR #46 больше не draft или владелец явно разрешил перевод в ready state. Текущее состояние `draft=true`, поэтому merge преждевременен как governance-шаг.

4. Проверить required checks GitHub branch protection именно на текущем head SHA. На момент проверки `Kolibri CI` #192 успешен для `8222c179...`, но statuses API пустой, поэтому нужно свериться с UI branch protection / PR checks.

5. Запустить проверки в чистом временном worktree, потому что текущий локальный checkout содержит чужие незакоммиченные изменения:

```bash
git worktree add /tmp/kolibri-pr46-verify 8222c179cc7df34caf60565c797ba8c55829dd78
cd /tmp/kolibri-pr46-verify
git diff --check origin/main...HEAD
python3 -m compileall backend ops scripts tests
bash -n ops/install_codex_cli.sh ops/bootstrap_factory_node.sh scripts/deploy_readiness_gate.sh scripts/factory_result_integration_check.sh scripts/server_kfrm_submission_guard.sh scripts/worktree_cleanup_preview.sh
python3 -m pytest -q tests/test_factory_runtime.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_autonomy_contracts.py tests/test_factory_lease_watchdog.py tests/test_telegram_gateway.py tests/test_factory_status.py tests/test_github_pr_gate.py backend/tests/test_billing.py backend/tests/test_estimate_document_pdf_engines.py backend/tests/test_factory_status_fast_health.py
npm --prefix frontend ci
npm --prefix frontend run build
```

6. Для runtime-sensitive частей дополнительно подтвердить smoke на staging/Control Plane после merge или перед rollout:

- backend health/API smoke;
- PWA build artifacts and service worker sanity;
- billing endpoints in configured and fallback modes;
- Control Plane task list fast path `/v1/tasks?limit=3`;
- Telegram report formatting path;
- factory lease watchdog path.

## Безопасный процесс приведения main в актуальное состояние

Рекомендуемый процесс без прямого push в `main`:

1. Оставить `main` неизменным до явного разрешения владельца.
2. Добиться ready state PR #46: снять draft только после review/approval владельца.
3. Перед merge зафиксировать expected head SHA: `8222c179cc7df34caf60565c797ba8c55829dd78`.
4. Убедиться, что GitHub checks на этом SHA зеленые и branch protection не требует дополнительных проверок.
5. Если docs whitespace считается блокером, добавить отдельный docs-only commit в PR-ветку, затем повторить все сравнения и CI для нового head SHA.
6. Выполнить merge через GitHub PR #46 с expected head SHA. Предпочтительный метод для аудита: обычный merge commit через PR. Он сохранит историю 25 коммитов и создаст merge commit в `main`.
7. Не использовать force update и не двигать `main` напрямую через `_update_ref`, кроме отдельного явного решения владельца о fast-forward ref update.
8. После merge:

```bash
git fetch origin '+refs/heads/main:refs/remotes/origin/main'
git merge-base --is-ancestor 8222c179cc7df34caf60565c797ba8c55829dd78 origin/main
git log --oneline -n 3 origin/main
```

Критерий успеха: `origin/main` содержит `8222c179...` в истории, а PR #46 закрыт как merged. Если требуется буквальное `origin/main == 8222c179...`, нужен отдельный fast-forward ref update approval, потому что GitHub PR merge обычно добавляет merge commit поверх head.

## Что не делалось

- Merge в `main` не выполнялся.
- Runtime-код не менялся.
- Чужие незакоммиченные изменения в рабочем дереве не откатывались и не редактировались.
- GitHub PR state не менялся: PR остался `open`, `draft=true`.
