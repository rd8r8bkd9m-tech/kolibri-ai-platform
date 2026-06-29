# PR #46 staging plan

Дата: 2026-06-29.
Ветка: `codex/factory-autonomy-pwa-billing`.
Правило: планировать staging для review/commit, но не выполнять `git add`,
`git commit` или `git push` из этого задания.

## Текущее состояние

`git status --short --untracked-files=all` показывает:

- 21 tracked-файл с изменениями относительно `HEAD`.
- Новый `docs/` tree с developer portal, agent-work пакетами, release notes и
  runbooks.
- Новые frontend файлы для landing/living bird и eslint config.
- Новые backend/ops/test файлы для desktop-control contract, agent messages и
  envelope packs.
- `.playwright-cli/page-*.yml` как неигнорируемые локальные Playwright snapshots.
  `.playwright-cli/console-*.log` уже игнорируются правилом `*.log`.

`git diff HEAD --stat` для tracked-файлов: 21 файл, 1849 insertions, 189
deletions. Обычный `git diff --stat` в этой worktree может быть пустым из-за
состояния index/stat; перед реальным staging стоит ориентироваться на
`git diff HEAD --stat` и затем выполнить `git status`.

## Рекомендуемый порядок staging

### 0. Не stage по умолчанию

Не включать в PR без отдельного решения:

```bash
.playwright-cli/page-2026-06-29T05-20-07-838Z.yml
.playwright-cli/page-2026-06-29T05-21-02-769Z.yml
.playwright-cli/page-2026-06-29T05-22-29-819Z.yml
```

Причина: это локальные browser snapshots, не source/evidence docs. Если нужны
как QA evidence, лучше перенести вручную в `docs/agent-work/` с коротким
описанием и тогда stage как documentation artifact.

### 1. Billing safety: T-Банк recurrent and notification hardening

Низко-связанный runtime slice с собственными unit tests.

```bash
git add backend/billing.py backend/tests/test_billing.py docs/agent-work/tbank-billing-ops.md docs/agent-work/tbank-payments-engineer-report.md docs/agent-work/tbank-subscription-readiness.md
```

Смысл группы:

- `DATA.OperationInitiatorType="1"` для initial recurrent checkout.
- `DATA.OperationInitiatorType="R"` для recurring init.
- `process_tbank_notification_payload()` как тестируемая точка входа.
- Проверки `TerminalKey`, known `OrderId`, non-empty `PaymentId`, `Amount`.
- Idempotency duplicate successful notification по `OrderId`/`PaymentId`.
- Mapping recurring callback через `billing_events`.

Проверки перед commit:

```bash
python3 -m compileall -q backend/billing.py backend/tests/test_billing.py
python3 -m pytest -q backend/tests/test_billing.py
```

Риск: production billing всё равно `NO-GO` без T-Банк sandbox evidence,
публичного HTTPS callback, фискализации и защиты scheduler-а `charge-due`.

### 2. Factory runtime observability: compact queue and agent feed

Runtime slice, который затрагивает Control Plane и Agent Host. Лучше держать
отдельно от Telegram CLI и frontend, чтобы rollback был понятным.

```bash
git add ops/factory_control.py ops/agent_host.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_agent_messages.py docs/agent-work/factory-runtime-rollout.md docs/agent-work/factory-control-rollout-check.md docs/agent-work/control-plane-api-p0-report.md docs/agent-work/control-plane-envelope-report.md docs/agent-work/control-plane-queue-unblock-report.md docs/agent-work/factory-p0-live-repair-status.md docs/agent-work/server-capacity-sre-report.md docs/agent-work/server-kfrm-app-run-plan.md docs/agent-work/server-kfrm-blocker-summary.md docs/agent-work/server-kfrm-queue-watch.md docs/agent-work/server-kfrm-runtime-recovery.md
```

Смысл группы:

- `/v1/tasks?summary=1&compact=1` ограничивает payload через queue prefix и
  лимиты.
- Summary показывает queue truncation, active tasks, expired leases и leases
  expiring soon.
- Новый `/v1/agent-messages` feed.
- Agent Host публикует `task_started`, `task_completed`, `task_failed`.

Проверки перед commit:

```bash
python3 -m compileall -q ops/agent_host.py ops/factory_control.py tests/test_factory_runtime_queue_contracts.py tests/test_factory_agent_messages.py
python3 -m pytest -q tests/test_factory_runtime_queue_contracts.py tests/test_factory_agent_messages.py
```

Риск: изменение runtime routes и worker publishing нужно деплоить
последовательно: сначала Control Plane с `/v1/agent-messages`, затем Agent Host,
иначе publish errors должны оставаться non-fatal.

### 3. Telegram report CLI and sanitization

Связанный ops slice с собственными tests; не смешивать с factory runtime.

```bash
git add ops/telegram_gateway.py tests/test_telegram_gateway.py docs/agent-work/telegram-document-report-review.md docs/agent-work/telegram-report-cli-qa.md docs/agent-work/telegram-report-letter-template.md docs/agent-work/telegram-reporting-final-check.md docs/agent-work/telegram-reporting-plan.md
```

Смысл группы:

- `--send-report` CLI path для отправки Markdown/text отчёта владельцу.
- Redaction tokens, auth/cookie headers, private paths and secret lines.
- Split Telegram text into bounded chunks.
- `TELEGRAM_OWNER_IDS` не нужен для one-shot report send при явном chat id.

Проверки перед commit:

```bash
python3 -m compileall -q ops/telegram_gateway.py tests/test_telegram_gateway.py
python3 -m pytest -q tests/test_telegram_gateway.py
```

Риск: live send требует `TELEGRAM_BOT_TOKEN` и owner/chat routing; unit tests не
подтверждают реальную доставку Telegram API.

### 4. Desktop control contract and MVP envelope

Contract/docs slice без подключения новых backend routes.

```bash
git add backend/desktop_control_contracts.py tests/test_desktop_control_contracts.py ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json docs/desktop-control-app.md docs/agent-work/desktop-control-app-mvp.md docs/agent-work/desktop-control-implementation-notes.md docs/agent-work/ubuntu-qa-runner-report.md
```

Смысл группы:

- Owner-facing allowlist Control Plane endpoints.
- Worker-only endpoints отделены от owner actions.
- Dangerous `permission_pack` warning.
- Redaction для owner summaries.
- MVP envelope для Ubuntu desktop control app.

Проверки перед commit:

```bash
python3 -m compileall -q backend/desktop_control_contracts.py tests/test_desktop_control_contracts.py
python3 -m pytest -q tests/test_desktop_control_contracts.py
python3 -m json.tool ops/envelopes/KOL-DESKTOP-CONTROL-APP-MVP-20260629.json >/dev/null
```

Риск: это контракт и задание, не готовый desktop app runtime.

### 5. Frontend premium landing, PWA polish and living bird

Крупный frontend slice. Лучше stage после успешного build/mobile guard и
визуального smoke check.

```bash
git add frontend/index.html frontend/public/manifest.webmanifest frontend/eslint.config.js frontend/src/App.css frontend/src/App.jsx frontend/src/components/AppHeader.jsx frontend/src/components/KolibriBird.jsx frontend/src/components/LandingShell.jsx frontend/src/components/LivingKolibri.jsx frontend/src/components/chat/ChatComposer.jsx frontend/src/components/chat/ChatWorkspace.jsx frontend/src/components/control/ControlFab.jsx frontend/src/components/control/ControlPanel.jsx frontend/src/assets/landing-hero.png docs/agent-work/frontend-lint-readiness.md docs/agent-work/premium-ui-standard.md docs/agent-work/pwa-mobile-design-qa.md docs/agent-work/ux-chat-first-review.md docs/agent-work/visual-preview-live-report.md docs/agent-work/kolibri-brand-asset-integration.md docs/agent-work/living-bird-rive-spec.md docs/agent-work/motion-bird-development-brief.md docs/living-bird.md
```

Смысл группы:

- `/` становится landing shell, `/app` остаётся chat-first product surface.
- PWA meta/manifest переведены на `Фабрика Колибри`.
- LivingKolibri controller реагирует на chat/network/factory/billing events.
- Header/composer/Control FAB получают mobile overflow и accessibility fixes.
- Добавлен eslint flat config.

Проверки перед commit:

```bash
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
```

Визуальная проверка перед push:

- `/` desktop 1440x900: first viewport, CTA, product visual, hint next section.
- `/` mobile 390x844 и 360x740: no horizontal overflow, no clipped Russian text.
- `/app` mobile: composer and right-bottom Control FAB do not overlap.

Риск: `frontend/src/assets/landing-hero.png` есть в worktree, но текущий
`LandingShell.jsx` не импортирует его. Перед staging решить: либо использовать
asset в hero, либо не stage asset.

### 6. Docs portal, policies and release notes

Большой documentation slice. Можно сделать одним docs commit после runtime
commits или разбить на docs portal и agent-work packs.

```bash
git add README.md docs/README.md docs/API-RU.md docs/api.md docs/deployment.md docs/factory.md docs/formulalm.md docs/github-ci.md docs/investors.md docs/kolibri-knowledge-map.md docs/mobile-gomesh.md docs/project-policy.md docs/quickstart.md docs/subagent-pool.md docs/RELEASE-NOTES-RU.md docs/agent-work/agent-registry-ru.md docs/agent-work/api-documentation-report.md docs/agent-work/automation-control-plane-10-pack.md docs/agent-work/automation-names-ru.md docs/agent-work/browser-preview-qa.md docs/agent-work/ci-after-push-watch.md docs/agent-work/ci-failure-triage.md docs/agent-work/design-director-development-brief.md docs/agent-work/design-team-roster.md docs/agent-work/deterministic-estimates-methodologist-report.md docs/agent-work/deterministic-estimates-methodology.md docs/agent-work/deterministic-estimates-p0-contract.md docs/agent-work/docs-integration-report.md docs/agent-work/docs-steward.md docs/agent-work/formulalm-remote-rd-pack.md docs/agent-work/github-api-inventory.md docs/agent-work/github-profile-readme.md docs/agent-work/github-project-operator-report.md docs/agent-work/github-project-ops.md docs/agent-work/github-project-sync-report.md docs/agent-work/github-telegram-status-ops.md docs/agent-work/investor-outreach-pack.md docs/agent-work/kolibri-legacy-integration-plan.md docs/agent-work/mobile-gomesh-integration-pack.md docs/agent-work/p0-runtime-watch-report.md docs/agent-work/post-commit-github-sync.md docs/agent-work/pr46-ci-next-report.md docs/agent-work/product-qa-pack.md docs/agent-work/production-preview-blocker.md docs/agent-work/release-status-20260629.md docs/agent-work/sales-investor-client-pipeline.md
```

Смысл группы:

- Русский docs hub и README репозитория.
- API/deployment/factory/GitHub/FormulaLM/mobile/investor/policy docs.
- Agent-work packs как операционные источники для ролей и QA.
- Release notes с явными `NO-GO`/blocker формулировками.

Проверки перед commit:

```bash
rg -n "ghp_|BEGIN .*PRIVATE KEY|Authorization:|Cookie:|Set-Cookie:|TBANK_PASSWORD|TELEGRAM_BOT_TOKEN" README.md docs
```

Риск: некоторые docs содержат локальные пути как sanitized knowledge/context
references. Перед публичным PR отдельно подтвердить, что такие пути допустимы
для repository docs или заменить на redacted placeholders.

### 7. Control Plane envelopes and role catalog

Операционный slice для задач фабрики. Его удобно держать после docs, потому что
envelopes ссылаются на docs/agent-work пакеты.

```bash
git add ops/factory_role_catalog.json ops/envelopes/KOL-FORMULALM-REMOTE-BENCH-6H-20260629.json ops/envelopes/KOL-PRODUCT-QA-E2E-20260629.json ops/envelopes/KOL-DOCS-STEWARD-20260629.json ops/envelopes/KOL-GITHUB-PROJECT-OPS-20260629.json ops/envelopes/KOL-INVESTOR-OUTREACH-20260629.json ops/envelopes/KOL-LIVING-BIRD-RD-20260629.json ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-20260629.json ops/envelopes/KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629.json ops/envelopes/KOL-PREMIUM-LANDING-UI-20260629.json ops/envelopes/KOL-SUBAGENT-POOL-SUPERVISOR-20260629.json ops/hourly-sync-report.md ops/secondary-control-plane-watchdog.md
```

Смысл группы:

- Новые role slots: docs steward, premium UI director, living character director.
- Completed subagent policy.
- Envelopes для docs, GitHub Project, investor outreach, living bird, premium
  landing, subagent pool, P0 app unblock/rerun, desktop control, product QA and
  FormulaLM.
- Ops reports for sync/watchdog state.

Проверки перед commit:

```bash
python3 -m json.tool ops/factory_role_catalog.json >/dev/null
for f in ops/envelopes/*.json; do python3 -m json.tool "$f" >/dev/null || exit 1; done
python3 -m compileall -q ops
```

Риск: envelopes with `permission_pack=full_autonomy` are powerful task specs;
PR review should validate scope, target nodes, source docs and no-secret policy
before submitting them to Control Plane.

## Финальный pre-push набор проверок

После staging/commits, но до push PR #46:

```bash
git status --short
git diff --check HEAD
python3 -m compileall -q backend ops tests
python3 -m pytest -q backend/tests tests
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
python3 -m json.tool ops/factory_role_catalog.json >/dev/null
for f in ops/envelopes/*.json; do python3 -m json.tool "$f" >/dev/null || exit 1; done
rg -n "ghp_|BEGIN .*PRIVATE KEY|Authorization:|Cookie:|Set-Cookie:|TBANK_PASSWORD|TELEGRAM_BOT_TOKEN" README.md docs backend ops frontend
```

Если локальный Python не имеет `pytest`, использовать temporary venv или тот же
интерпретатор, который использует CI. Не считать PR готовым только по
`compileall`.

## Коммитная раскладка

Рекомендуемый порядок commit titles:

1. `billing: harden tbank recurrent notifications`
2. `factory: add compact task summary and agent feed`
3. `ops: add telegram report letter cli`
4. `desktop: document control app contract`
5. `frontend: add landing shell and living kolibri`
6. `docs: add russian developer portal and agent packs`
7. `factory: add role catalog updates and task envelopes`

Если нужно уменьшить review size, docs group можно разбить:

- `docs: add developer portal`
- `docs: add agent work packs`
- `docs: add release and ops reports`

## Контрольные замечания для PR curator

- Не смешивать billing runtime и frontend polish в одном commit.
- Не смешивать factory runtime route changes и envelope/task specs.
- Не stage `.playwright-cli/` snapshots без отдельного решения.
- Перед staging frontend asset `landing-hero.png` проверить, используется ли он
  в коде; сейчас он выглядит как orphan asset.
- Все группы должны оставаться совместимыми с правилом: Mac только control/edit
  surface, FormulaLM/model benchmarks только на remote Linux factory nodes.
