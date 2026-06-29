# Release notes, 2026-06-29

Краткий статус: это рабочий срез изменений в текущем worktree, а не объявление
production-релиза. Общий release readiness по документальному статусу:
`NO-GO`: локальные части подготовлены, но acceptance evidence и внешние проверки
ещё не закрыты.

## Runtime и factory

- Agent host начал публиковать события `task_started`, `task_completed` и
  `task_failed` в inter-agent feed через `/v1/agent-messages`.
- Control Plane получил быстрый compact summary для очереди через
  `queue_prefix`: ответ `/v1/tasks?summary=1&compact=1&limit=N` больше не
  обязан тащить всю историю задач.
- В summary добавлены показатели `queue_total`, `queue_truncated`,
  `active_total`, `expired_lease_total` и `lease_expiring_soon_total`.
- В live-контуре восстановлен запуск новых задач через свежий `main` worker;
  `KOL-P0-APP-QUEUE-UNBLOCK-RERUN-20260629` был взят `main:agent-host-main`.
- Зафиксирован новый read-only/owner-facing контракт desktop control без
  подключения к runtime routes: allowlist endpoint-ов, worker-only запреты,
  warnings для `full_autonomy` и redaction summary.

Ограничения: `server-kfrm` остаётся stale, большая часть нод не подтверждена
как fresh executor, целевые 80% мощности ещё не достигнуты, очередь требует
controlled drain/recovery.

## PWA и frontend

- Брендинг PWA переведён на `Фабрика Колибри`: `title`, manifest name,
  `application-name`, Apple title и description.
- Manifest и HTML meta обновлены под standalone PWA, light/system тему,
  safe-area viewport и maskable icons 192/512.
- В интерфейсе добавлены/улучшены light/system/dark theme contracts,
  responsive header, mobile composer, Control FAB offsets и ограничения против
  overlap на узких экранах.
- Добавлена landing shell / premium landing поверхность и living Kolibri
  компоненты в frontend worktree.

Ограничения: реальная Android/iOS установка, standalone режим и offline shell
на HTTPS/non-local preview не подтверждены. В PWA QA отмечен риск
landing first viewport: Playwright screenshots показывали страницу ниже
hero/nav, нужна ручная перепроверка.

## Billing

- Backend T-Банк flow усилен для recurrent-платежей:
  `DATA.OperationInitiatorType="1"` для первичного checkout и `"R"` для
  recurring init.
- Successful notification теперь проверяет `TerminalKey`, известный `OrderId`,
  непустой `PaymentId` и совпадение `Amount` с тарифом.
- Добавлена идемпотентность duplicate successful notification по
  `OrderId`/`PaymentId`.
- Recurring notification может находить подписку через audit event нового
  `OrderId`, чтобы callback после `Charge` продлевал lifecycle.
- Fallback lead mode остаётся безопасным: без T-Банк credentials создаётся
  заявка, но подписка не активируется.

Ограничения: production billing остаётся `NO-GO` без T-Банк sandbox evidence,
публичного HTTPS `NotificationURL`, signed notification, recurring `Charge`,
решения по онлайн-кассе/фискализации и защиты scheduler-а от параллельного
`charge-due`.

## Docs

- Добавлен русский docs hub в `docs/README.md` и отдельные документы по factory,
  GitHub/CI, FormulaLM, mobile/GoMesh, investors, living bird и subagent pool.
- Agent-work пакеты интегрированы как операционные источники: Product QA,
  T-Банк billing ops, FormulaLM remote R&D, GitHub Project ops, Mobile/GoMesh,
  legacy integration, living bird и investor outreach.
- README репозитория переписан под текущую русскоязычную архитектуру:
  AI-фабрика, SPA/PWA, Control Plane, подписки, FormulaLM и GitHub Project.
- Зафиксированы release-status и QA отчёты с явными blocker-ами вместо
  утверждения о готовом релизе.

## Проверки из текущих отчётов

Локально были зафиксированы зелёные проверки:

```text
backend/tests/test_billing.py: 8 passed
tests/test_factory_runtime_queue_contracts.py: 5 passed
tests/test_telegram_gateway.py: 41 passed
backend/tests/test_estimate_document_pdf_engines.py: 5 passed
npm --prefix frontend run build: passed, с существующим предупреждением о chunk >500 kB
npm --prefix frontend run test:mobile-layout --if-present: passed
git diff --check: clean в runtime rollout отчёте
```

Live/readiness blockers на момент документов:

- GitHub PR #46 был draft/open, опубликованный CI красный до push локальных
  исправлений и нового Actions run.
- `KOL-PRODUCT-QA-E2E-20260629` оставался queued.
- `server-kfrm` не имел fresh heartbeat/probe.
- PWA install/offline evidence на реальных Android/iOS устройствах отсутствует.
- T-Банк проверен только локальными mock/unit тестами, без реального sandbox
  checkout/notification/Charge.
