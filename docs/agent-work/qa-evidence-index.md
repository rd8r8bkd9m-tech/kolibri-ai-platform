# QA evidence index

Дата индекса: 2026-06-29  
Роль: сборщик QA evidence  
Scope: локальные и фабричные проверки, зафиксированные в `docs/agent-work`.

Этот индекс собран как desk-review по локальным отчетам. Новые тяжелые тесты,
FormulaLM, LLM/model workloads, SSH и Control Plane mutations не запускались.
Статусы ниже означают статус evidence в документах, а не результат нового
прогона в этом проходе.

## 1. Короткий вердикт

Общий релизный статус по evidence: `NO-GO`.

Локально есть зеленые targeted проверки для backend billing, deterministic
estimate PDF/golden path, Telegram gateway/report CLI, frontend build/mobile
layout, factory status guard и части Control Plane contracts. Но релизный
acceptance не закрыт: GitHub CI на опубликованном PR #46 остается красным на
старом head, `server-kfrm` stale, P0 product QA в Control Plane queued,
independent browser/PWA evidence неполный, T-Банк sandbox/prod не проверены,
FormulaLM только remote-only planned.

## 2. Локальные проверки с passed evidence

| Area | Команды / проверка | Статус | Артефакты / источники | Оставшиеся риски |
| --- | --- | --- | --- | --- |
| Release local P0 slice | `PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q backend/tests/test_billing.py` | `passed`: `8 passed` | `docs/agent-work/release-status-20260629.md`, `docs/agent-work/tbank-payments-engineer-report.md` | Только mock/unit; нет реального T-Банк sandbox checkout/notification/Charge. |
| Deterministic estimates PDF/golden | `PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q backend/tests/test_estimate_document_pdf_engines.py` | `passed`: `5 passed, 1 warning` | `docs/agent-work/release-status-20260629.md` | Golden path не закрывает полный P0 API/manifest/benchmark contract. |
| Factory status guard | `PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint` | `passed`: `1 passed` | `docs/agent-work/release-status-20260629.md`, `docs/agent-work/ci-failure-triage.md`, `docs/agent-work/pr46-ci-next-report.md` | Fix локальный/unpushed; GitHub CI на published head все еще red. |
| Telegram gateway | `PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q tests/test_telegram_gateway.py` | `passed`: `41 passed` | `docs/agent-work/release-status-20260629.md` | Live Telegram delivery smoke не выполнен; caller-provided title/agent/status требуют policy. |
| Telegram report CLI dry harness | `python3 -m py_compile ops/telegram_gateway.py`; manual harness без сети | `passed`: `py_compile` ok, `manual telegram report checks passed` | `docs/agent-work/telegram-reporting-final-check.md` | `pytest` недоступен в system Python; реальная отправка не выполнялась. |
| Frontend build | `npm --prefix frontend run build`; also `npm run build` in frontend reports | `passed` with existing Vite chunk-size warning | `docs/agent-work/release-status-20260629.md`, `docs/agent-work/pr46-ci-next-report.md`, `docs/agent-work/ux-chat-first-review.md`, `docs/agent-work/pwa-mobile-design-qa.md` | Build не заменяет browser/mobile/console/install evidence. |
| Frontend lint | `npm run lint` | `passed` with 3 warnings, 0 errors | `docs/agent-work/pr46-ci-next-report.md`, `docs/agent-work/ux-chat-first-review.md`, `docs/agent-work/frontend-lint-readiness.md` | Warnings remain: service worker unused `error`, `useMemo` deps, Fast Refresh export warning. |
| Mobile layout guard | `npm --prefix frontend run test:mobile-layout --if-present`; `npm run test:mobile-layout` | `passed`: mobile layout guard passed | `docs/agent-work/release-status-20260629.md`, `docs/agent-work/pr46-ci-next-report.md`, `docs/agent-work/pwa-mobile-design-qa.md`, `docs/agent-work/ux-chat-first-review.md` | Regex/CSS guard missed real viewport overflow in screenshots; need viewport guard. |
| PR #46 full local pytest | `/tmp/kolibri-pr46-ci-venv/bin/python -m pytest -q` | `passed`: `89 passed, 1 warning` | `docs/agent-work/pr46-ci-next-report.md` | Local worktree dirty; result not published to PR CI. |
| PR #46 compile | `/opt/homebrew/bin/python3.12 -m compileall -q backend infra scripts` | `passed` | `docs/agent-work/pr46-ci-next-report.md` | Does not cover ops files changed later unless rerun for that scope. |
| CI tail guards local reproduction | tracked JSON/YAML validation, secret scan, production secret path guard, backend smoke, frontend smoke | `passed` | `docs/agent-work/pr46-ci-next-report.md` | Local reproduction only; Actions on PR still red at old SHA. |
| Workspace JSON validation | Validate 21 workspace JSON files excluding `node_modules/.git/dist` | `passed` | `docs/agent-work/pr46-ci-next-report.md` | Does not imply envelope semantic acceptance. |
| Envelope JSON validation | `for f in ops/envelopes/*.json; do python3 -m json.tool "$f" >/dev/null; done` | `passed`: all parse | `docs/agent-work/control-plane-envelope-report.md` | Envelopes prepared locally; most were not submitted/executed. |
| Control Plane API P0 syntax/harness | `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile ops/factory_control.py ops/agent_host.py`; one-off compact listing harness | `passed`: harness printed `compact_task_listing harness passed` | `docs/agent-work/control-plane-api-p0-report.md` | Pytest blocked in system Python; bounded scan totals may be partial. |
| Factory P0 rollout local checks | `PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile ops/factory_control.py tests/test_factory_runtime_queue_contracts.py`; `/tmp/kolibri-p0-venv/bin/python -m pytest -q tests/test_factory_runtime_queue_contracts.py`; `git diff --check` | `passed`: `5 passed`, diff check clean | `docs/agent-work/factory-p0-live-repair-status.md` | Rollout improved queue visibility, but queue still has backlog and `server-kfrm` stale. |
| PWA static guards | Manifest JSON guard, icon file checks, service-worker/static guards | `passed` in document | `docs/agent-work/pwa-mobile-design-qa.md` | Real Android/iOS install/offline evidence absent; local preview disables SW registration. |
| API documentation review | Read-only `rg`/`sed` code/doc review | `passed` as docs review | `docs/agent-work/api-documentation-report.md` | Some endpoints documented as roadmap/placeholders, not live API. |
| Docs integration review | Markdown inventory and `inventory`/`GitHub API` searches | `passed` as docs review | `docs/agent-work/docs-integration-report.md` | Documentation integration is not product/runtime evidence. |

## 3. Factory / live read-only checks

| Area | Команды / проверка | Статус | Артефакты / источники | Оставшиеся риски |
| --- | --- | --- | --- | --- |
| Control Plane health | `curl http://10.99.0.2:9101/health` / `curl -fsS --max-time ... /health` | `passed`: `status=ok`, `redis=PONG`, `spool_count=0` in multiple snapshots | `docs/agent-work/release-status-20260629.md`, `docs/agent-work/ubuntu-qa-runner-report.md`, `docs/agent-work/control-plane-queue-unblock-report.md`, `docs/agent-work/server-kfrm-queue-watch.md` | Health does not prove runners are fresh or tasks are progressing. |
| Targeted server-kfrm probe status | `ops/kolibri-dispatch status KOL-SERVER-KFRM-PROBE-20260629 --full`; `GET /v1/tasks/KOL-SERVER-KFRM-PROBE-20260629` | `blocked`: `state=queued`, no lease, no result | `docs/agent-work/release-status-20260629.md`, `docs/agent-work/server-kfrm-queue-watch.md`, `docs/agent-work/server-kfrm-blocker-summary.md`, `docs/agent-work/ubuntu-qa-runner-report.md` | `server-kfrm` heartbeat stale; no node-local artifact; do not start app QA or FormulaLM. |
| Product QA envelope status | `ops/kolibri-dispatch status KOL-PRODUCT-QA-E2E-20260629 --full` | `blocked`: `state=queued` | `docs/agent-work/release-status-20260629.md`, `docs/agent-work/ubuntu-qa-runner-report.md` | No fresh non-draining `generic_implementation` runner at snapshot. |
| P0 app queue unblock status | `ops/kolibri-dispatch status KOL-P0-APP-QUEUE-UNBLOCK-20260629 --full` | `blocked`: `404 task_not_found` in release snapshot; rerun task later `running` | `docs/agent-work/release-status-20260629.md`, `docs/agent-work/factory-p0-live-repair-status.md` | Need collect final result for `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629`. |
| Queue summary before P0 fix | `GET /v1/tasks?summary=1&compact=1`; variants with `limit` and `state` | `blocked`: huge payload/timeouts/misleading counts | `docs/agent-work/control-plane-queue-unblock-report.md`, `docs/agent-work/ubuntu-qa-runner-report.md` | Broad task listing was not reliable as an operator gate before compact summary fix. |
| Queue summary after P0 rollout | `GET /v1/tasks?summary=1&compact=1&limit=5` | `passed`: `queue_length=71`, truncated prefix and bounded response | `docs/agent-work/factory-p0-live-repair-status.md` | Queue still large; needs controlled drain/recovery, not mass execution. |
| Agent messages endpoint | `GET /v1/agent-messages?target=all&limit=5` | `passed`: `status=200`, messages empty in smoke | `docs/agent-work/factory-p0-live-repair-status.md` | Endpoint smoke only; does not prove full owner/report workflow. |
| Node inventory / filesystem | `/v1/nodes`, `/v1/filesystem` | `passed` as read-only inventory | `docs/agent-work/ubuntu-qa-runner-report.md`, `docs/agent-work/server-capacity-sre-report.md`, `docs/agent-work/server-kfrm-queue-watch.md` | OS is not proven by Control Plane; Ubuntu/Linux must be proven inside lease with `uname`. |
| Runner capacity | Manual freshness matrix from `/health` and `/v1/nodes` | `blocked` for heavy QA: no fresh non-draining `generic_implementation` runner | `docs/agent-work/ubuntu-qa-runner-report.md`, `docs/agent-work/server-capacity-sre-report.md` | `qjns` is drained; `server-kfrm`, `highload`, `primary-candidate` stale or risky. |
| GitHub Project/PR read-only | `gh auth status`, `gh project view/field-list/item-list`, `gh pr view`, `gh pr checks`, `gh run view --log-failed` | `passed` as read-only inspection; outcome is blocked/red | `docs/agent-work/github-project-sync-report.md`, `docs/agent-work/github-project-operator-report.md`, `docs/agent-work/ci-failure-triage.md` | Project/PR not mutated; statuses still need sync after approved commit/push. |
| PR #46 GitHub checks | `gh pr checks 46` | `blocked`: two failed `Kolibri CI / ci` checks on head `eadc04a...` | `docs/agent-work/ci-failure-triage.md`, `docs/agent-work/pr46-ci-next-report.md`, `docs/agent-work/release-status-20260629.md` | Must commit/push local fix and wait for new green Actions run. |

## 4. Browser, visual, and PWA evidence

| Area | Команды / проверка | Статус | Артефакты / источники | Оставшиеся риски |
| --- | --- | --- | --- | --- |
| Dev visual preview | `http://127.0.0.1:5173/`, `/app`, manifest | `partial`: dev routes `200 OK` in visual report | `docs/agent-work/visual-preview-live-report.md` | Backend `8000` and production preview `4173` were unavailable in that report. |
| Browser preview protocol | `npm --prefix frontend ci`; `npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173`; backend uvicorn; build/preview commands | `planned/regression protocol` | `docs/agent-work/browser-preview-qa.md` | Protocol only unless screenshots/console/network evidence are attached. |
| PWA production-like preview | `npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173`; `curl -I` for `/`, `/app`, manifest, SW | `passed` in PWA mobile report | `docs/agent-work/pwa-mobile-design-qa.md` | Localhost preview is not sufficient install/offline evidence because SW registration is disabled on local hosts. |
| PWA screenshots | Playwright screenshots to `/tmp/kolibri-pwa-mobile-design-qa-20260629/` | `partial`: screenshots saved | `docs/agent-work/pwa-mobile-design-qa.md` | Screenshots show landing starts below hero; Control Panel open state missing. |
| UX screenshots | Chrome headless screenshots to `/tmp/kolibri-ux-chat-first-review/*.png` | `blocked`: screenshots reveal P0 issues | `docs/agent-work/ux-chat-first-review.md` | Mobile horizontal overflow and landing auto-scroll must be fixed before merge. |
| Console/network checks | DevTools console/network checklist | `planned/blocked` | `docs/agent-work/visual-preview-live-report.md`, `docs/agent-work/browser-preview-qa.md`, `docs/agent-work/product-qa-pack.md` | No full console/network pass with backend and production preview evidence. |
| Android/iOS install/offline | Real device install, standalone, offline reload, safe areas | `blocked/not run` | `docs/agent-work/pwa-mobile-design-qa.md`, `docs/agent-work/product-qa-pack.md` | Required for release sign-off; needs HTTPS/non-local preview or devices. |

## 5. Remote-only and blocked workloads

| Workload | Commands / expected checks | Статус | Артефакты / источники | Оставшиеся риски |
| --- | --- | --- | --- | --- |
| Ubuntu QA lease | `uname -a`; `test "$(uname -s)" != "Darwin"`; `npm --prefix frontend ci/lint/build/test:mobile-layout`; `python3 -m compileall -q backend ops tests`; `python3 -m pytest backend/tests tests`; focused pytest list; optional Playwright screenshots | `planned/blocked` | `docs/agent-work/ubuntu-qa-runner-report.md`, `docs/agent-work/server-kfrm-app-run-plan.md` | Must run inside Ubuntu factory lease, not on Mac; blocked by runner capacity. |
| server-kfrm app run | Read-only gate via Control Plane, then node-local build/test/smoke on `server-kfrm` | `blocked` | `docs/agent-work/server-kfrm-app-run-plan.md`, `docs/agent-work/server-kfrm-queue-watch.md` | Needs fresh heartbeat and completed read-only probe with node-local artifact. |
| FormulaLM 6h benchmark | `ops/kolibri-dispatch submit --file ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json` only after gates | `blocked/planned` | `docs/agent-work/formulalm-remote-rd-pack.md`, `docs/agent-work/ubuntu-qa-runner-report.md`, `docs/agent-work/control-plane-envelope-report.md` | Remote-only; do not run on Mac; wait for `server-kfrm` probe and no pending release QA. |
| Product QA E2E | Envelope `KOL-PRODUCT-QA-E2E-20260629` | `blocked`: already live queued, do not resubmit | `docs/agent-work/product-qa-pack.md`, `docs/agent-work/ubuntu-qa-runner-report.md`, `docs/agent-work/release-status-20260629.md` | Needs independent QA result, screenshots, console/network, GO/NO-GO decision. |
| T-Банк sandbox | `/api/billing/plans`, checkout, signed notification, recurring `charge-due`, negative notifications | `blocked/not run` | `docs/agent-work/tbank-payments-engineer-report.md`, `docs/agent-work/tbank-subscription-readiness.md`, `docs/agent-work/tbank-billing-ops.md` | Requires sandbox secrets, public HTTPS callback, separate DB, fiscalization decision. |
| Telegram live delivery | Gateway `--send-report` with real owner chat id/token | `blocked/not run` | `docs/agent-work/telegram-reporting-final-check.md`, `docs/agent-work/telegram-reporting-plan.md`, `docs/agent-work/telegram-document-report-review.md` | Needs safe production smoke without leaking tokens/paths. |

## 6. Source coverage

Evidence-bearing files reviewed for this index:

- `api-documentation-report.md`
- `browser-preview-qa.md`
- `ci-after-push-watch.md`
- `ci-failure-triage.md`
- `control-plane-api-p0-report.md`
- `control-plane-envelope-report.md`
- `control-plane-queue-unblock-report.md`
- `factory-control-rollout-check.md`
- `factory-p0-live-repair-status.md`
- `factory-runtime-rollout.md`
- `formulalm-remote-rd-pack.md`
- `frontend-lint-readiness.md`
- `github-project-operator-report.md`
- `github-project-sync-report.md`
- `github-telegram-status-ops.md`
- `post-commit-github-sync.md`
- `pr46-ci-next-report.md`
- `product-qa-pack.md`
- `production-preview-blocker.md`
- `pwa-mobile-design-qa.md`
- `release-status-20260629.md`
- `server-capacity-sre-report.md`
- `server-kfrm-app-run-plan.md`
- `server-kfrm-blocker-summary.md`
- `server-kfrm-queue-watch.md`
- `server-kfrm-runtime-recovery.md`
- `tbank-billing-ops.md`
- `tbank-payments-engineer-report.md`
- `tbank-subscription-readiness.md`
- `telegram-document-report-review.md`
- `telegram-report-cli-qa.md`
- `telegram-reporting-final-check.md`
- `telegram-reporting-plan.md`
- `ubuntu-qa-runner-report.md`
- `ux-chat-first-review.md`
- `visual-preview-live-report.md`

Docs with mostly planning/spec/roster content and no independent executable QA
result were treated as supporting context, not green evidence: agent registry,
automation packs/names, design briefs/rosters, desktop-control packs, estimate
methodology/contract docs, docs steward, GitHub API inventory/ops, investor
outreach, brand/legacy/living-bird/mobile-gomesh/motion specs, premium UI
standard, sales pipeline, and Telegram letter templates.

## 7. Next evidence needed

1. Commit/push the PR #46 CI fix and wait for fresh green `Kolibri CI / ci`.
2. Get `server-kfrm` fresh heartbeat and completed
   `KOL-SERVER-KFRM-PROBE-20260629` with node-local artifact.
3. Run `KOL-PRODUCT-QA-E2E-20260629` on a fresh Ubuntu factory runner and attach
   build/test/browser/mobile artifacts.
4. Fix or explicitly exception the visual P0 issues: mobile overflow and landing
   auto-scroll below hero.
5. Collect production-like browser evidence: `/`, `/app`, Control Panel,
   console/network, manifest/SW, desktop and mobile screenshots.
6. Complete real Android/iOS PWA install/offline checks.
7. Complete T-Банк sandbox acceptance and Telegram live safe delivery smoke.
8. Keep FormulaLM remote-only and last, after release QA capacity is clear.
