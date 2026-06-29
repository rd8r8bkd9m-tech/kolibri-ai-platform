# GitHub Project sync report

Дата проверки: 2026-06-29 07:32 MSK / 2026-06-29 04:32 UTC  
Роль: `github_project_sync_operator`  
Репозиторий: `rd8r8bkd9m-tech/kolibri-ai-platform`  
Project: `#2`, `Kolibri AI Platform: фабрика ИИ и продукт на миллиарды`

Статус: подготовлен пакет синхронизации после текущего коммита. GitHub Project,
PR и issues не изменялись. Issues не закрывались. Project schema не менялась.
Новые токены не создавались.

## Что проверено

- `gh auth status`: активный аккаунт `rd8r8bkd9m-tech`, scopes включают
  `repo`, `project`, `read:org`, `workflow`.
- `gh project view 2 --owner rd8r8bkd9m-tech`: Project открыт, private,
  `items.totalCount=7`, `fields.totalCount=18`.
- `gh project field-list 2 --owner rd8r8bkd9m-tech`: схема уже содержит
  `Status`, `Приоритет`, `Направление`, `Агент`, `Артефакты`,
  `Следующий отчёт`.
- `gh project item-list 2 --owner rd8r8bkd9m-tech --limit 100`: в Project
  сейчас 7 items: PR #46 и P0 issues #47-#52.
- `gh pr view 46`, GitHub app PR metadata, PR comments и review threads:
  PR открыт, draft, mergeable, комментариев и review threads нет.
- `gh pr checks 46` и `gh run view ... --log-failed`: оба текущих Actions run
  красные из-за одного pytest guard.
- P0 issues #47-#52: все `OPEN`, без assignees и без комментариев.

## Текущее состояние GitHub

### Project #2

Фактические статусы всех 7 items сейчас: `Todo`.

Фактическая схема `Status` имеет только:

- `Todo`
- `In Progress`
- `Done`

В схеме нет отдельных `Blocked` или `Review`. Поэтому блокеры и ожидание review
нужно фиксировать комментариями/полем `Артефакты`, не добавляя новые поля и не
меняя schema.

### PR #46

- URL: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46
- Title: `[codex] Factory autonomy, PWA billing, remote FormulaLM`
- State: `OPEN`
- Draft: `true`
- Mergeable: `MERGEABLE`
- Base: `main` at `6d0317c52a9694448ee2c352dc196ce7a27b9487`
- Current GitHub head: `eadc04a07ca51812615f8b523c828d0fff1c136f`
- Commits on GitHub: 2
- Changed files on GitHub: 56
- PR comments: none
- Reviews/review threads: none
- Current Project status: `Todo`

CI at current GitHub head is red:

- push run `28346968290`, job `83972196451`: failed.
- pull_request run `28346987211`, job `83972253483`: failed.
- Root cause in both: `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`
  expected `Фабрика Колибри` inside `frontend/src/App.jsx`.
- Current local worktree already contains `const PRODUCT_TITLE = "Фабрика Колибри"`
  in `frontend/src/App.jsx`.
- Targeted verification in existing Python 3.12 venv passed:
  `/tmp/kolibri-ci-triage-312-venv/bin/python -m pytest tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint -q`
  -> `1 passed`.
- Default local `python3` points to Python 3.14 and has no `pytest`; do not use
  that as CI-equivalent evidence.

### P0 issues

All P0 issues are open, unassigned, uncommented and currently `Todo` in
Project #2:

| Issue | Labels | Current Project status | Local/current artifacts relevant after commit |
| --- | --- | --- | --- |
| #47 `P0: Документовод и developer portal на русском языке` | `P0`, `docs` | `Todo` | `docs/README.md`, `docs/api.md`, `docs/quickstart.md`, `docs/deployment.md`, `docs/agent-work/docs-steward.md` |
| #48 `P0: Закрепить политику разработки Kolibri AI Platform` | `P0`, `factory`, `docs` | `Todo` | `docs/project-policy.md`, `docs/agent-work/github-project-ops.md`, PR #46 |
| #49 `P0: Премиум-лендинг и SPA/PWA без потери chat-first продукта` | `P0`, `design` | `Todo` | `frontend/src/*`, `frontend/public/manifest.webmanifest`, `docs/agent-work/premium-ui-standard.md`, `docs/agent-work/product-qa-pack.md` |
| #50 `P0: Живая птица Kolibri как state-machine персонаж` | `P0`, `design` | `Todo` | `docs/living-bird.md`, `docs/agent-work/living-bird-rive-spec.md`, `frontend/src/components/KolibriBird.jsx`, `frontend/src/components/LivingKolibri.jsx` |
| #51 `P0: Инвесторский pipeline и outreach-пакет на миллиарды` | `P0`, `investors` | `Todo` | `docs/investors.md`, `docs/agent-work/investor-outreach-pack.md` |
| #52 `P0: Runtime rollout фабрики и запуск серверных агентов` | `P0`, `factory` | `Todo` | `docs/agent-work/factory-runtime-rollout.md`, `docs/agent-work/control-plane-envelope-report.md`, `ops/envelopes/*.json` |

## Синхронизация после текущего коммита

Не синхронизировать до появления нового commit SHA и пуша в PR #46. Все тексты
ниже используют placeholder `<COMMIT_SHA>`, который нужно заменить фактическим
SHA текущего коммита.

Рекомендуемые Project field updates после коммита:

| Item | Status | Приоритет | Направление | Агент | Следующий отчёт | Артефакты |
| --- | --- | --- | --- | --- | --- | --- |
| PR #46 | `In Progress` | `P0` | `GitHub/CI` | `github_project_sync_operator`, `ci_failure_triage_agent` | `2026-06-29 08:00 MSK` or +30m from sync time | PR #46, `<COMMIT_SHA>`, CI run URLs, `docs/agent-work/ci-failure-triage.md` |
| #47 | `In Progress` | `P0` | `Документация` | `docs_steward` | `2026-06-29 08:00 MSK` or +30m | docs portal files, `docs/agent-work/docs-steward.md`, PR #46 |
| #48 | `In Progress` | `P0` | `Документация` | `docs_steward`, `factory_runtime_sre` | `2026-06-29 08:00 MSK` or +30m | `docs/project-policy.md`, `docs/agent-work/github-project-ops.md`, PR #46 |
| #49 | `In Progress` | `P0` | `SPA/PWA` | `premium_ui_director`, `qa_lead` | `2026-06-29 08:00 MSK` or +30m | frontend changes, `docs/agent-work/premium-ui-standard.md`, `docs/agent-work/product-qa-pack.md`, PR #46 |
| #50 | `In Progress` | `P0` | `Живая птица` | `living_character_director` | `2026-06-29 08:00 MSK` or +30m | `docs/living-bird.md`, `docs/agent-work/living-bird-rive-spec.md`, frontend character components, PR #46 |
| #51 | `In Progress` | `P0` | `Инвесторы` | `investor_sales_operator` | `2026-06-29 08:00 MSK` or +30m | `docs/investors.md`, `docs/agent-work/investor-outreach-pack.md`, PR #46 |
| #52 | `In Progress` | `P0` | `Фабрика` | `factory_runtime_sre`, `control_plane_envelope_integrator` | `2026-06-29 08:00 MSK` or +30m | rollout plan, envelope report, `ops/envelopes/*.json`, PR #46 |

Do not use `Done` for any of these items yet. PR #46 is still draft and CI on
GitHub is currently red at the old head. Issues should stay open until PR
review/merge and acceptance evidence exist.

## PR comment to post after commit

Target: PR #46 conversation.

```markdown
Project sync after commit `<COMMIT_SHA>`.

- Project #2 recommendation: set PR #46 to `In Progress`, `P0`, direction `GitHub/CI` until the new Actions run is green.
- Previous GitHub head `eadc04a07ca51812615f8b523c828d0fff1c136f` had two red `Kolibri CI / ci` runs. Both failed on the same guard: `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint` expected `Фабрика Колибри` in `frontend/src/App.jsx`.
- Current commit restores the product title in `App.jsx`; targeted local verification in Python 3.12 passed: `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint`.
- P0 issues #47-#52 should be moved from `Todo` to `In Progress` with comments below, not closed.
- Next step: wait for the new CI run on `<COMMIT_SHA>`, then update PR/Project with the actual check result.

Project sync: pending CI on `<COMMIT_SHA>`.
```

## Issue comments to post after commit

### Issue #47

```markdown
Project sync after commit `<COMMIT_SHA>`.

- Status recommendation: `In Progress`, priority `P0`, direction `Документация`. Issue stays open.
- Current artifact set prepared in PR #46: `docs/README.md`, `docs/api.md`, `docs/quickstart.md`, `docs/deployment.md`, plus `docs/agent-work/docs-steward.md`.
- Scope covered: Russian developer portal baseline, API outline, quickstart, deployment/runbook direction, task-envelope/inter-agent documentation package.
- Blocker/next gate: wait for new CI on `<COMMIT_SHA>` and review whether the portal should remain as top-level docs or be split into `docs/developer-portal/*`.

Project sync: in progress, not complete.
```

### Issue #48

```markdown
Project sync after commit `<COMMIT_SHA>`.

- Status recommendation: `In Progress`, priority `P0`, direction `Документация` while the policy/doc artifacts are under PR review. Issue stays open.
- Current artifact set prepared in PR #46: `docs/project-policy.md` and `docs/agent-work/github-project-ops.md`.
- Policy now captures remote-first work, 80% factory utilization, Project/CI rules, P0 blocker visibility, docs/investor/design/FormulaLM boundaries, and no-secret/no-token guardrails.
- Blocker/next gate: PR #46 must pass CI and be reviewed before this can be considered accepted policy.

Project sync: in progress, not complete.
```

### Issue #49

```markdown
Project sync after commit `<COMMIT_SHA>`.

- Status recommendation: `In Progress`, priority `P0`, direction `SPA/PWA`. Issue stays open.
- Current artifact set prepared in PR #46: frontend landing/app changes, PWA manifest update, `docs/agent-work/premium-ui-standard.md`, and QA gates in `docs/agent-work/product-qa-pack.md`.
- The intended product split is `/` landing and `/app` chat-first SPA with Control preserved as the secondary workspace entry.
- Blocker/next gate: new CI on `<COMMIT_SHA>`, frontend build, and mobile/desktop visual QA evidence. Do not mark done before screenshots/build logs are attached or summarized.

Project sync: in progress, visual QA pending.
```

### Issue #50

```markdown
Project sync after commit `<COMMIT_SHA>`.

- Status recommendation: `In Progress`, priority `P0`, direction `Живая птица`. Issue stays open.
- Current artifact set prepared in PR #46: `docs/living-bird.md`, `docs/agent-work/living-bird-rive-spec.md`, and frontend character component work.
- The documented direction is Rive state machine as primary runtime with SVG fallback and no fake claim that a `.riv` asset is already complete.
- Blocker/next gate: implement/attach actual Rive asset or keep SVG fallback explicitly accepted for this slice, then run mobile performance/accessibility QA.

Project sync: in progress, asset/runtime evidence pending.
```

### Issue #51

```markdown
Project sync after commit `<COMMIT_SHA>`.

- Status recommendation: `In Progress`, priority `P0`, direction `Инвесторы`. Issue stays open.
- Current artifact set prepared in PR #46: `docs/investors.md` and `docs/agent-work/investor-outreach-pack.md`.
- Pack includes RU/EN one-pager draft, outreach templates, CRM/status guidance, and explicit guardrails: no invented contacts, no guessed emails, no unsupported fundraising/model claims, no external sending from this task.
- Blocker/next gate: owner review of claims/evidence and verified contact source before any outreach leaves the repo.

Project sync: in progress, external outreach not sent.
```

### Issue #52

```markdown
Project sync after commit `<COMMIT_SHA>`.

- Status recommendation: `In Progress`, priority `P0`, direction `Фабрика`. Issue stays open.
- Current artifact set prepared in PR #46: `docs/agent-work/factory-runtime-rollout.md`, `docs/agent-work/control-plane-envelope-report.md`, and Control Plane task envelopes under `ops/envelopes/`.
- Important distinction: rollout/envelopes are prepared locally, but Control Plane tasks were not submitted from this sync pass and live runtime health was not changed.
- Known blockers remain: live Control Plane/Agent Hosts may still be on older runtime, stale node handling still needs deployment/heartbeat evidence, and `server-kfrm` needs fresh probe before remote FormulaLM work.
- Next gate: after PR #46 commit/CI, deploy or submit the rollout/probe envelopes through Control Plane and attach node/task status evidence.

Project sync: in progress, rollout execution pending.
```

## Reference IDs for later automated sync

Project id: `PVT_kwHODmcz_M4Bb728`

Status field:

- field id: `PVTSSF_lAHODmcz_M4Bb728zhWocZs`
- `Todo`: `f75ad846`
- `In Progress`: `47fc9ee4`
- `Done`: `98236657`

Priority field:

- field id: `PVTSSF_lAHODmcz_M4Bb728zhWocks`
- `P0`: `542d9863`
- `P1`: `9de3c29f`
- `P2`: `8d0ae970`

Direction field:

- field id: `PVTSSF_lAHODmcz_M4Bb728zhWocoI`
- `Фабрика`: `6cd8e561`
- `SPA/PWA`: `90b3e186`
- `FormulaLM`: `1a777df8`
- `Сметы`: `9702b542`
- `Инвесторы`: `8d83468e`
- `GitHub/CI`: `c01d1588`
- `Документация`: `3699f66d`
- `Живая птица`: `414023d1`
- `Мобильный слой`: `377a3a4c`

Project item ids:

- PR #46: `PVTI_lAHODmcz_M4Bb728zgxGfyU`
- Issue #52: `PVTI_lAHODmcz_M4Bb728zgxGgUE`
- Issue #48: `PVTI_lAHODmcz_M4Bb728zgxGgUI`
- Issue #47: `PVTI_lAHODmcz_M4Bb728zgxGgUM`
- Issue #49: `PVTI_lAHODmcz_M4Bb728zgxGgUQ`
- Issue #51: `PVTI_lAHODmcz_M4Bb728zgxGgUY`
- Issue #50: `PVTI_lAHODmcz_M4Bb728zgxGgYs`

Text/date fields:

- `Агент`: `PVTF_lAHODmcz_M4Bb728zhWockk`
- `Артефакты`: `PVTF_lAHODmcz_M4Bb728zhWocko`
- `Следующий отчёт`: `PVTF_lAHODmcz_M4Bb728zhWocsY`

## Do not do in this sync

- Do not close P0 issues #47-#52.
- Do not mark Project items as `Done` before PR review/merge and acceptance
  evidence.
- Do not add Project fields or rename options.
- Do not create/refresh GitHub tokens.
- Do not post comments before replacing `<COMMIT_SHA>` with the actual pushed
  commit SHA.
- Do not claim runtime rollout, investor outreach, Rive asset completion or
  visual QA completion until corresponding artifacts/checks exist.
