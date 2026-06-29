# Релизный статус P0 на 2026-06-29

Ответственный: Документовод релизного статуса.

Срез: 2026-06-29 07:50 MSK / 2026-06-29 04:50 UTC.

Scope: SPA/PWA, Telegram reports, `server-kfrm`, billing, deterministic
estimates, GitHub PR #46. Код в рамках этого отчета не менялся.

## Короткий вердикт

P0 сейчас не готов к release/owner handoff как единый продуктовый релиз.
Локально есть существенная готовность по frontend build, billing tests,
deterministic estimates tests и Telegram gateway tests, но релизный readiness
блокируют GitHub CI на опубликованном PR #46, отсутствие независимого E2E
product QA, stale `server-kfrm`, queued P0 QA task, отсутствие live evidence по
PWA/browser, внешние T-Банк проверки и неполный P0-контракт смет.

Нельзя писать "готово к релизу". Корректный статус: `NO-GO, локальные P0
части подготовлены, acceptance evidence не закрыт`.

## Матрица статуса

| Область | Текущий статус | Что готово | Queued / stale | Что блокирует readiness |
| --- | --- | --- | --- | --- |
| SPA/PWA | Частично готово локально, release NO-GO | Локальный `npm --prefix frontend run build` прошел; `test:mobile-layout` прошел; `/` и `/app` разделены в коде; `PRODUCT_TITLE = "Фабрика Колибри"` вернул локальный CI guard; PWA manifest обновлен в worktree. | Live `KOL-PRODUCT-QA-E2E-20260629` в Control Plane все еще `queued`; owner app task `TG-20260629003017-4711-up-telegram` stale-running на `9fts`; локальный `KOL-P0-APP-QUEUE-UNBLOCK-20260629.json` есть, но live task в Control Plane не найден. | Нет независимого browser/mobile evidence: desktop/mobile screenshots, PWA install/offline shell, console/network pass, deployed app proof. GitHub CI на PR #46 красный до push локального fix и нового Actions run. |
| Telegram reports | Частично готово локально, live delivery не доказан | Документы описывают owner-safe маршрут через Control Plane и `kolibri-telegram-gateway.service`; локально в `ops/telegram_gateway.py` есть `--send-report`, sanitizer, chunking, выбор chat id; `tests/test_telegram_gateway.py` прошел. | Доставка зависит от `TELEGRAM_BOT_TOKEN`, `TELEGRAM_OWNER_IDS`, сохраненного `owner_chat_id` или `TELEGRAM_REPORT_CHAT_ID`; live send в этом проходе не выполнялся. | Нет production smoke через реальный gateway. Поля `title/agent/status` у report letter остаются caller-controlled, поэтому перед публичной доставкой нужен либо строгий caller policy, либо дополнительный sanitizer contract. |
| `server-kfrm` | Заблокирован stale heartbeat | Нода зарегистрирована, имеет `generic_implementation`, `read_only_probe`, 8 CPU, около 27 GB available RAM и около 150 GB free disk; namespace `/kolibri/nodes/server-kfrm` описан. | Live heartbeat `server-kfrm`: `2026-06-28T20:17:15Z`, stale на момент среза `2026-06-29T04:50Z`; `KOL-SERVER-KFRM-PROBE-20260629` остается `queued`; FormulaLM remote bench envelope targeted to `server-kfrm`, но запускать его нельзя до fresh probe. | Нужен fresh heartbeat и completed read-only probe именно на `server-kfrm`. До этого нельзя запускать тяжелый app QA, FormulaLM 6h benchmark или релизный remote smoke. Дополнительно нет no-model `app_smoke` runner; `generic_implementation` зависит от model runner/auth. |
| Billing | Локальный backend-контракт зеленый, production blocked | `backend/tests/test_billing.py`: 8 passed. Локально покрыты fallback lead без активации подписки, T-Банк token rules, `OperationInitiatorType`, successful notification safety, amount/payment checks, idempotency и recurring order lookup. | Внешний T-Банк sandbox/prod контур не проверен в этом проходе. | Нужны test terminal credentials, публичный HTTPS `NotificationURL`, sandbox checkout, signed notification, recurring `Charge`, проверка `RebillId`, admin token и решение по онлайн-кассе/фискализации. Без этого billing не production-ready. |
| Deterministic estimates | Golden P0 demo зеленый, продуктовый P0 не закрыт | `backend/tests/test_estimate_document_pdf_engines.py`: 5 passed. Golden case `100 м2 штукатурки в Татарстане` стабилен по текущему движку: `EST-A1B5B0B498`, `kolibri-ru-2026q2-v1`, grand total `161035.00`. | Полный API/manifest контракт пока документирован, но не закрыт как продуктовая поверхность. | Нужны canonical request schema/API, immutable pricebook manifest с hash, `region_code`/version envelope, rules/profile versions, validation/publish gates, revisions и benchmark dataset. Claim 98-99% нельзя делать без frozen dataset и метрик. |
| GitHub PR #46 | Открыт, draft, CI red | PR: https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46. GitHub показывает `OPEN`, `draft=true`, `mergeable=MERGEABLE`, head `eadc04a07ca51812615f8b523c828d0fff1c136f`, 56 changed files. Локальный targeted guard `tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint` прошел после uncommitted fix. | GitHub Actions на опубликованном head `eadc04a...` красные: push run `28346968290`, pull_request run `28346987211`. PR comments/reviews отсутствуют. | Нужно commit/push локальные исправления, дождаться нового зеленого CI, обновить PR/Project status и только потом переводить PR из draft/review path. Пока PR #46 не является release-ready. |

## Проверки, выполненные этим проходом

Команды запускались локально, без правок кода и без мутаций Control Plane:

```text
PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q backend/tests/test_billing.py
8 passed

PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q backend/tests/test_estimate_document_pdf_engines.py
5 passed, 1 warning

PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q tests/test_factory_status.py::test_frontend_uses_live_factory_status_endpoint
1 passed

PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-ci-triage-312-venv/bin/python -m pytest -q tests/test_telegram_gateway.py
41 passed

npm --prefix frontend run build
passed, with existing >500 kB chunk warning

npm --prefix frontend run test:mobile-layout --if-present
mobile layout guard passed
```

Read-only live checks:

```text
curl http://10.99.0.2:9101/health
status=ok, redis=PONG, spool_count=0

ops/kolibri-dispatch status KOL-SERVER-KFRM-PROBE-20260629 --full
state=queued

ops/kolibri-dispatch status KOL-PRODUCT-QA-E2E-20260629 --full
state=queued

ops/kolibri-dispatch status KOL-P0-APP-QUEUE-UNBLOCK-20260629 --full
404 task_not_found
```

GitHub checks:

```text
gh pr checks 46 --repo rd8r8bkd9m-tech/kolibri-ai-platform
ci fail, ci fail

gh pr view 46 --json ...
OPEN, draft=true, mergeable=MERGEABLE, head=eadc04a07ca51812615f8b523c828d0fff1c136f
```

## Главные блокеры readiness

1. Опубликовать локальный fix для PR #46 и получить новый зеленый GitHub CI.
2. Провести независимый product QA по `KOL-PRODUCT-QA-E2E-20260629` или явно
   снять blocker, почему live QA не может взять lease.
3. Восстановить `server-kfrm`: fresh heartbeat, completed
   `KOL-SERVER-KFRM-PROBE-20260629`, node-local artifact evidence.
4. Получить browser/PWA evidence: desktop/mobile screenshots, install/offline
   shell, console/network без blocker errors.
5. Проверить T-Банк sandbox end-to-end: checkout, signed notification,
   recurring charge, fiscalization decision.
6. Для deterministic estimates закрыть не только golden test, но и P0 API /
   manifest / validation / publish / benchmark contract.
7. Для Telegram reports провести live safe delivery smoke через gateway с
   owner chat id и без утечки секретов/внутренних путей.

## Следующий честный статус

Следующий статус можно перевести из `NO-GO` в `GO WITH EXCEPTION` только после
нового зеленого PR CI, локального browser evidence и понятного решения по live
factory QA. Полный `GO` возможен только после закрытия `server-kfrm`, billing
sandbox, Telegram live smoke и deterministic estimates P0 contract.
