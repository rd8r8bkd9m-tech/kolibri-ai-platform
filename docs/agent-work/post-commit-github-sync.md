# Post-commit GitHub sync packet

Роль: `post_commit_github_sync_operator`
Понятное название: Оператор GitHub Project после коммита
Дата подготовки: 2026-06-29
Репозиторий: `rd8r8bkd9m-tech/kolibri-ai-platform`
Project: `#2`, `Kolibri AI Platform: фабрика ИИ и продукт на миллиарды`
Статус этого файла: подготовлен локально. GitHub, PR, issues и Project не
изменялись. Код не менялся.

## 1. Когда использовать

Этот пакет применять только после появления следующего commit SHA и, если PR
синхронизируется через GitHub, после push в PR #46.

Перед публикацией заменить placeholders:

| Placeholder | Чем заменить |
| --- | --- |
| `<NEXT_COMMIT_SHA>` | полный SHA следующего коммита |
| `<NEXT_COMMIT_SHORT>` | короткий SHA |
| `<CI_STATUS>` | `pending`, `green`, `red`, `cancelled` |
| `<CI_RUN_URLS>` | ссылки на новые Actions runs или `pending` |
| `<VISUAL_PREVIEW_STATUS>` | `not_run`, `pass`, `fail`, `pending_backend` |
| `<VISUAL_PREVIEW_EVIDENCE>` | `/tmp/...`, artifact reference, PR screenshot ссылку или `pending` |
| `<TELEGRAM_REPORT_STATUS>` | `not_sent`, `sent`, `blocked` |
| `<NEXT_REPORT_AT>` | ближайшее время следующего отчета в MSK |

Не использовать `Done` для PR #46 или issues #47-#52 сразу после коммита.
Даже при зеленом CI остаются review, visual preview, server-kfrm и acceptance
gates.

## 2. Факты, на которых основан пакет

- PR #46 открыт, draft, Project item сейчас должен оставаться не финальным.
- Старый GitHub head `eadc04a07ca51812615f8b523c828d0fff1c136f` имел красный
  `Kolibri CI / ci` на push и pull_request.
- Зафиксированная причина CI: guard
  `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`
  ожидал строку `Фабрика Колибри` в `frontend/src/App.jsx`.
- Локальный worktree по предыдущему triage уже содержит узкий candidate fix:
  `PRODUCT_TITLE = "Фабрика Колибри"` и передачу заголовка в header.
- Project schema в фактическом снимке имеет `Status`: `Todo`, `In Progress`,
  `Done`. Отдельных `Blocked` и `Review` нет, поэтому blocker/review надо
  фиксировать в PR/issue comments и `Артефакты`.
- `server-kfrm` по локальному отчету остается blocker: старый heartbeat,
  `KOL-SERVER-KFRM-PROBE-20260629` должен завершиться именно на `server-kfrm`
  до тяжелой QA, app-run и FormulaLM.
- Telegram-report CLI существует как `ops/telegram_gateway.py --send-report`,
  но production отправка требует установленного Telegram token/chat id и
  owner-safe summary. Секреты и приватные пути не публиковать.
- Visual preview должен ссылаться на browser evidence, а не на обещание:
  screenshots или artifact path для `/`, `/app` и Control Panel.

## 3. Project field updates после коммита

Использовать только существующие поля Project. Новые поля не добавлять, option
names не переименовывать.

| Item | Status | Приоритет | Направление | Агент | Следующий отчет | Артефакты |
| --- | --- | --- | --- | --- | --- | --- |
| PR #46 | `In Progress` | `P0` | `GitHub/CI` | `post_commit_github_sync_operator`, `ci_failure_triage_agent` | `<NEXT_REPORT_AT>` | `PR #46`, `<NEXT_COMMIT_SHA>`, `<CI_RUN_URLS>`, `docs/agent-work/post-commit-github-sync.md`, `docs/agent-work/ci-failure-triage.md`, `visual:<VISUAL_PREVIEW_STATUS>`, `telegram:<TELEGRAM_REPORT_STATUS>` |
| Issue #47 | `In Progress` | `P0` | `Документация` | `docs_steward` | `<NEXT_REPORT_AT>` | `docs/README.md`, `docs/api.md`, `docs/quickstart.md`, `docs/deployment.md`, `docs/agent-work/docs-steward.md`, `PR #46`, `<NEXT_COMMIT_SHA>` |
| Issue #48 | `In Progress` | `P0` | `Документация` | `docs_steward`, `github_project_operator` | `<NEXT_REPORT_AT>` | `docs/project-policy.md`, `docs/agent-work/github-project-ops.md`, this report, `PR #46`, `<NEXT_COMMIT_SHA>` |
| Issue #49 | `In Progress` | `P0` | `SPA/PWA` | `premium_ui_director`, `qa_lead` | `<NEXT_REPORT_AT>` | frontend app/landing files, `docs/agent-work/browser-preview-qa.md`, `<VISUAL_PREVIEW_EVIDENCE>`, `PR #46`, `<NEXT_COMMIT_SHA>` |
| Issue #50 | `In Progress` | `P0` | `Живая птица` | `living_character_director` | `<NEXT_REPORT_AT>` | `docs/living-bird.md`, `docs/agent-work/living-bird-rive-spec.md`, frontend character components, `PR #46`, `<NEXT_COMMIT_SHA>` |
| Issue #51 | `In Progress` | `P0` | `Инвесторы` | `investor_sales_operator` | `<NEXT_REPORT_AT>` | `docs/investors.md`, `docs/agent-work/investor-outreach-pack.md`, `PR #46`, `<NEXT_COMMIT_SHA>` |
| Issue #52 | `In Progress` | `P0` | `Фабрика` | `factory_runtime_sre`, `control_plane_envelope_integrator` | `<NEXT_REPORT_AT>` | `server-kfrm blocker`, `KOL-SERVER-KFRM-PROBE-20260629`, `docs/agent-work/server-kfrm-app-run-plan.md`, `docs/agent-work/ubuntu-qa-runner-report.md`, `ops/envelopes/*.json`, `PR #46`, `<NEXT_COMMIT_SHA>` |

Project API reference ids из последнего локального sync report:

```text
Project id: PVT_kwHODmcz_M4Bb728
Status field: PVTSSF_lAHODmcz_M4Bb728zhWocZs
Status options: Todo=f75ad846, In Progress=47fc9ee4, Done=98236657
Priority field: PVTSSF_lAHODmcz_M4Bb728zhWocks
Direction field: PVTSSF_lAHODmcz_M4Bb728zhWocoI
Agent field: PVTF_lAHODmcz_M4Bb728zhWockk
Artifacts field: PVTF_lAHODmcz_M4Bb728zhWocko
Next report field: PVTF_lAHODmcz_M4Bb728zhWocsY
PR #46 item: PVTI_lAHODmcz_M4Bb728zgxGfyU
Issue #47 item: PVTI_lAHODmcz_M4Bb728zgxGgUM
Issue #48 item: PVTI_lAHODmcz_M4Bb728zgxGgUI
Issue #49 item: PVTI_lAHODmcz_M4Bb728zgxGgUQ
Issue #50 item: PVTI_lAHODmcz_M4Bb728zgxGgYs
Issue #51 item: PVTI_lAHODmcz_M4Bb728zgxGgUY
Issue #52 item: PVTI_lAHODmcz_M4Bb728zgxGgUE
```

## 4. PR #46 comment

Target: PR #46 conversation.

```markdown
Post-commit sync for `<NEXT_COMMIT_SHA>`.

Status: На проверке / В работе
Report: `docs/agent-work/post-commit-github-sync.md`
Project sync: pending until Project fields are updated
Telegram report: `<TELEGRAM_REPORT_STATUS>`

CI:
- Previous GitHub head `eadc04a07ca51812615f8b523c828d0fff1c136f` had red `Kolibri CI / ci` runs on push and pull_request.
- Root cause was `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`: it expected `Фабрика Колибри` in `frontend/src/App.jsx`.
- `<NEXT_COMMIT_SHA>` is the next candidate with the narrow frontend title fix.
- New CI status: `<CI_STATUS>`.
- New CI runs: `<CI_RUN_URLS>`.

Visual preview:
- Status: `<VISUAL_PREVIEW_STATUS>`.
- Evidence: `<VISUAL_PREVIEW_EVIDENCE>`.
- Required before owner-facing ready claim: `/`, `/app`, `/app` with Control Panel, desktop and mobile screenshots or equivalent artifact references.

server-kfrm / factory blocker:
- `server-kfrm` remains a blocker unless `KOL-SERVER-KFRM-PROBE-20260629` has completed on `server-kfrm` with node-local artifacts.
- Do not run heavy product QA, app-run or FormulaLM workloads on `server-kfrm` until the probe and heartbeat are fresh.

Project recommendation:
- Keep PR #46 as `In Progress`, `P0`, direction `GitHub/CI`.
- Move/keep issues #47-#52 as `In Progress`, not `Done`.
- Store blockers and review state in comments and `Артефакты`, because Project #2 currently has only `Todo`, `In Progress`, `Done`.

Next step:
- If CI is green and visual preview passes, prepare PR #46 for review but do not mark Project `Done` before review/merge and issue acceptance.
- If CI is red, keep PR #46 `In Progress`, add the failing check URL/root cause, and set the next report to `<NEXT_REPORT_AT>`.
```

## 5. Issue comments

### Issue #47

```markdown
Post-commit sync for `<NEXT_COMMIT_SHA>`.

Status recommendation: `In Progress`, priority `P0`, direction `Документация`. Issue stays open.

Artifacts now tied to PR #46:
- `docs/README.md`
- `docs/api.md`
- `docs/quickstart.md`
- `docs/deployment.md`
- `docs/agent-work/docs-steward.md`
- `docs/agent-work/post-commit-github-sync.md`

CI: `<CI_STATUS>` (`<CI_RUN_URLS>`)

Next gate:
- Keep the documentation portal under review until PR #46 passes CI and owner/reviewer accepts the docs structure.

Project sync: in progress, not complete.
```

### Issue #48

```markdown
Post-commit sync for `<NEXT_COMMIT_SHA>`.

Status recommendation: `In Progress`, priority `P0`, direction `Документация`. Issue stays open.

Artifacts now tied to PR #46:
- `docs/project-policy.md`
- `docs/agent-work/github-project-ops.md`
- `docs/agent-work/github-project-sync-report.md`
- `docs/agent-work/github-telegram-status-ops.md`
- `docs/agent-work/post-commit-github-sync.md`

Project policy note:
- Project #2 currently has only `Todo`, `In Progress`, `Done`; blocker/review state must be written in PR/issue comments and `Артефакты`, not by adding schema fields.

Next gate:
- After CI and review, decide whether to keep this as policy docs or split operational packets into separate automation-owned docs.

Project sync: in progress, not complete.
```

### Issue #49

```markdown
Post-commit sync for `<NEXT_COMMIT_SHA>`.

Status recommendation: `In Progress`, priority `P0`, direction `SPA/PWA`. Issue stays open.

Visual preview:
- Status: `<VISUAL_PREVIEW_STATUS>`.
- Evidence: `<VISUAL_PREVIEW_EVIDENCE>`.
- Required views: `/`, `/app`, `/app` with Control Panel.
- Required viewports: desktop and 390px mobile at minimum.

CI:
- `<CI_STATUS>` (`<CI_RUN_URLS>`)

Blocker rule:
- Do not mark this issue done until build/lint/mobile-layout evidence and visual screenshots are attached or summarized.
- Backend-offline visual preview may be accepted only as `GO WITH EXCEPTION`, with the backend offline condition written explicitly.

Project sync: in progress, visual preview gate pending until evidence is attached.
```

### Issue #50

```markdown
Post-commit sync for `<NEXT_COMMIT_SHA>`.

Status recommendation: `In Progress`, priority `P0`, direction `Живая птица`. Issue stays open.

Artifacts tied to PR #46:
- `docs/living-bird.md`
- `docs/agent-work/living-bird-rive-spec.md`
- frontend character component work

Current gate:
- Keep the issue open until the actual runtime asset or accepted SVG fallback has evidence.
- Do not claim a complete Rive asset unless a `.riv` or equivalent runtime artifact is attached and checked.

CI: `<CI_STATUS>` (`<CI_RUN_URLS>`)

Project sync: in progress, asset/runtime evidence pending.
```

### Issue #51

```markdown
Post-commit sync for `<NEXT_COMMIT_SHA>`.

Status recommendation: `In Progress`, priority `P0`, direction `Инвесторы`. Issue stays open.

Artifacts tied to PR #46:
- `docs/investors.md`
- `docs/agent-work/investor-outreach-pack.md`

Guardrails:
- No invented contacts.
- No guessed emails.
- No unsupported fundraising, revenue or model-performance claims.
- No external outreach sent from this sync pass.

Next gate:
- Owner review of claims/evidence and verified contact source before any external message is sent.

Project sync: in progress, external outreach not sent.
```

### Issue #52

```markdown
Post-commit sync for `<NEXT_COMMIT_SHA>`.

Status recommendation: `In Progress`, priority `P0`, direction `Фабрика`. Issue stays open.

Factory/server-kfrm blocker:
- `server-kfrm` is still considered blocked until its heartbeat is fresh and `KOL-SERVER-KFRM-PROBE-20260629` completes on `server-kfrm`.
- Do not start heavy product QA, app-run or FormulaLM on `server-kfrm` until the probe has node-local result/artifact evidence.
- Do not resubmit already live queued tasks such as `KOL-PRODUCT-QA-E2E-20260629`; use targeted status reads first.
- Do not use SSH, SCP, systemd/nginx changes, drain/cancel/retry or lease surgery from this sync pass.

Artifacts:
- `docs/agent-work/server-kfrm-app-run-plan.md`
- `docs/agent-work/ubuntu-qa-runner-report.md`
- `ops/envelopes/KOL-SERVER-KFRM-PROBE-20260629.json`
- `ops/envelopes/KOL-PRODUCT-QA-E2E-20260629.json`
- PR #46 at `<NEXT_COMMIT_SHA>`

CI:
- `<CI_STATUS>` (`<CI_RUN_URLS>`)

Next gate:
- Read-only Control Plane check of `KOL-SERVER-KFRM-PROBE-20260629`, then update this issue with `probe_completed` or `probe_blocked` evidence.

Project sync: in progress, server-kfrm blocker remains unless the probe evidence says otherwise.
```

## 6. Telegram-report CLI после коммита

Telegram не является источником результата. Он получает короткую owner-safe
сводку и безопасную ссылку на PR/report. Не публиковать `task_id`, node id,
local paths, logs, token/scopes или stack traces в owner-facing summary.

Owner-safe summary для Telegram:

```text
На проверке. После нового коммита я обновляю GitHub Project, CI, визуальную проверку и серверный blocker; готово назову только после зеленых проверок и evidence.
```

Команда для production-only отправки после коммита, если token/chat id уже
настроены на control node:

```bash
python3 ops/telegram_gateway.py \
  --send-report docs/agent-work/post-commit-github-sync.md \
  --report-title "GitHub Project sync после коммита <NEXT_COMMIT_SHORT>" \
  --report-agent "Оператор GitHub Project после коммита" \
  --report-status "На проверке" \
  --report-summary "На проверке. После нового коммита я обновляю GitHub Project, CI, визуальную проверку и серверный blocker; готово назову только после зеленых проверок и evidence."
```

Если CLI не отправлялся:

```text
Telegram report: not_sent
Reason: post-commit sync prepared locally; live Telegram send requires configured token/chat id and is not part of this local docs-only task.
```

Если CLI заблокирован QA gap:

```text
Telegram report: blocked
Reason: report CLI QA gaps remain; use GitHub PR/issue comments as the authoritative owner-visible trail.
```

## 7. Visual preview после коммита

Минимальная команда evidence перед owner-facing ready claim:

```bash
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173
```

Минимум screenshots/artifacts:

```text
landing-desktop-1440.png
app-desktop-1440.png
app-control-desktop-1440.png
landing-mobile-390.png
app-mobile-390.png
app-control-mobile-390.png
console-notes.md
```

Если preview не запускался, писать:

```text
Visual preview: not_run
Reason: no post-commit browser evidence yet.
```

Если backend не поднят, но frontend визуально проверен:

```text
Visual preview: GO WITH EXCEPTION
Exception: backend intentionally offline; frontend must show degraded/offline state without crash.
Evidence: <VISUAL_PREVIEW_EVIDENCE>
```

## 8. CI fix handling

После push следующего SHA:

1. Дождаться новых runs на `<NEXT_COMMIT_SHA>`.
2. Если `Kolibri CI / ci` зеленый, обновить PR comment:

```text
CI: green on <NEXT_COMMIT_SHA>
Runs: <CI_RUN_URLS>
Previous red guard is cleared.
```

3. Если CI снова красный, не закрывать issue и не ставить Project `Done`.
   Добавить в PR comment:

```text
CI: red on <NEXT_COMMIT_SHA>
Failing check: <check name>
Run: <run URL>
Root cause: <1-2 sentence summary>
Next action: <fix owner and next command>
Next report: <NEXT_REPORT_AT>
```

4. Если CI pending дольше ожидаемого SLA:

```text
CI: pending on <NEXT_COMMIT_SHA>
Next action: wait/watch Actions; no Project Done transition until conclusion.
Next report: <NEXT_REPORT_AT>
```

## 9. server-kfrm blocker handling

Targeted read-only checks for the later operator:

```bash
export KOLIBRI_FACTORY_CONTROL_URL="http://10.99.0.2:9101"

curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/health"
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" nodes
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  status KOL-SERVER-KFRM-PROBE-20260629 --full
ops/kolibri-dispatch --control-url "$KOLIBRI_FACTORY_CONTROL_URL" \
  collect KOL-SERVER-KFRM-PROBE-20260629
```

If probe is not completed:

```text
server-kfrm: blocked
Reason: KOL-SERVER-KFRM-PROBE-20260629 has not completed on server-kfrm with node-local artifacts.
Allowed next action: read-only status/watch or operator-approved recovery.
Forbidden: SSH, resubmit live tasks, drain/cancel/retry, heavy QA, app-run, FormulaLM benchmark.
```

If probe is completed:

```text
server-kfrm: probe_completed
Evidence: <result/artifact reference>
Next action: schedule product QA/app-run through Control Plane only, using node-local artifacts and no SSH.
```

## 10. Suggested post-commit command order

These commands are for the later operator. They were not run while preparing
this local document.

```bash
git rev-parse HEAD
git status --short
gh pr view 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform --json number,url,title,headRefOid,isDraft,state
gh pr checks 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform --watch
```

After replacing placeholders in the prepared comment files, publish in this
order:

1. PR #46 comment with CI, visual preview, Telegram and server-kfrm status.
2. Issue #52 comment if server-kfrm remains blocked or probe evidence changed.
3. Issue #49 comment with visual preview evidence.
4. Issue comments #47, #48, #50, #51.
5. Project field updates for PR #46 and issues #47-#52.
6. Telegram-report CLI only after GitHub trail exists and safe summary is final.

## 11. Do not do

- Do not change GitHub before `<NEXT_COMMIT_SHA>` exists.
- Do not close P0 issues #47-#52 from this sync.
- Do not mark Project items `Done` before CI, review/merge and acceptance
  evidence.
- Do not add Project fields or rename options.
- Do not create or refresh GitHub tokens.
- Do not send Telegram messages that include task ids, node ids, local paths,
  logs, token/scopes or private data.
- Do not run SSH/SCP/systemd/nginx or mutate Control Plane leases while
  handling server-kfrm blocker.
- Do not claim visual readiness without screenshots/artifact references.

## 12. Local verification for this document

Docs-only verification:

```bash
test -f docs/agent-work/post-commit-github-sync.md
rg -n "PR #46|Issue #52|Telegram-report|Visual preview|server-kfrm|CI" docs/agent-work/post-commit-github-sync.md
git diff -- docs/agent-work/post-commit-github-sync.md
git status --short
```

If `docs/` is still untracked:

```bash
git diff --no-index /dev/null docs/agent-work/post-commit-github-sync.md
```
