# План доработок Kolibri V3

Дата: 2026-08-08
Статус: утверждён к исполнению (поэтапно, каждый этап завершается зелёными
гейтами `npm run verify`).

## Журнал исполнения

- 2026-08-08, Этап 1 — завершён: ruff E402/F821 исправлены, мобильный срез
  редактора смет восстановлен (`data-slot="estimate-mobile-list"`), контрактный
  тест dev-стека обновлён под усиленный health-probe; `npm run verify`
  (quick) зелёный.
- 2026-08-08, Этап 2 — bridge переведён на dual-stack (127.0.0.1 + ::1),
  добавлены `npm run check:ui-gateway` и `npm run check:mobile-app`
  (регрессионные smoke), мобильное PWA открывается на phone-viewport без
  ошибок. Health-probe dev-стека усилен (2s/8 попыток) — ложные fence при
  перегрузке CPU исключены.
- 2026-08-08, Этап 3 — `dev-backend.sh` экспортирует провайдерские ключи
  (`OPENAI_API_KEY`, `DEEPSEEK_API_KEY` и др.), `config.py` принимает
  `KOLIBRI_V3_OPENAI_API_KEY`-алиасы, auto-резолюция не выбирает `codex-cli`
  для обычного чата, дефолт Qwen исправлен на `qwen-plus`.
- 2026-08-08, Этап 4 — DeepSeek интегрирован: конфиг, streaming runtime,
  каталог, platform-admin провайдер, `.env.example`, README, тесты (46 passed).
  Живой smoke — после предоставления `DEEPSEEK_API_KEY`.
- 2026-08-08, Этап 2.6 — мобильный скролл починен: react-native-web 0.21.2
  рендерит `pointerEvents: "box-none"` как невалидный CSS (обёртка питомца
  перехватывала wheel/touch); автоскролл переведён на прямой DOM-scroll
  (`getScrollableNode` + rAF). Проверено: автоскролл и wheel 0→474→474.
- 2026-08-08, Этап 5.2 — recurring/rebill T-Банк: миграция 059, RebillId,
  recurrent Init, продление подписки по CONFIRMED, `run_due_renewals`,
  auto-renew toggle, admin `renewals/run`. 426 backend-тестов зелёные.
- 2026-08-08, Composer — GPT-стиль (desktop+mobile): кнопка отправки только
  при тексте, авто-рост, дисклеймер, серое поле с радиусом (явные CSS-правила
  вместо негенерируемых Tailwind-утилит); slash commands и @-mentions на
  assistant-ui `Unstable_TriggerPopover`; чипы директив в сообщениях;
  e2e `tests/e2e/composer.spec.ts` (5 passed, 1 skip).
- 2026-08-08, Dev-стек — guard от двойного запуска (pid-файл), самовосстановление
  осиротевшего стека в `dev-persistent.sh`, редирект `localhost:3000` → gateway.
- 2026-08-08, Чат/DeepSeek — диагностирован блокер: `DEEPSEEK_API_KEY` не задан
  (OpenAI — нет кредитов, Qwen — задолженность, MIMO — не подключён).
  Ошибка `agent_profile_not_registered` для deepseek заменена на
  `deepseek_key_not_configured` с инструкцией; плейсхолдер добавлен в `.env.local`.
- 2026-08-08, Чат/DeepSeek (фикс) — найдена настоящая причина «запросы идут мимо»:
  платформенные/пользовательские модели (`platform:`/`user:`) были в каталоге и
  выбирались, но рантайм их НЕ выполнял — запрос уходил на дефолтного провайдера.
  Добавлены `_custom_model_credentials` (расшифровка ключа) и
  `_custom_model_response` (OpenAI-совместимый стриминг) в
  `backend/app/direct_model_runtime.py`, ветка в стандартном чат-исполнении.
  Проверено сквозно: выбор модели DeepSeek через админ-панель → чат → ответ
  стримится (RUN_FINISHED, браузер: «Да» за 3.4 с, ошибок нет). 44 backend-теста.
- 2026-08-08, Мобильная авторизация — причина «опять не работает»: мобильное PWA
  ходило на запечённый `http://127.0.0.1:8002` (на телефоне это сам телефон).
  Gateway теперь проксирует `/v1` и `/api` на backend, а мобильное приложение
  на web использует same-origin API (детект по cookie `kolibri_ui_client`).
  Проверено: регистрация 201 и вход 200 через gateway, чат и сессия работают.
- 2026-08-08, Этап 5.1–5.3 — recurring/rebill доведён до рабочего контура:
  провайдерский `RebillId`/`CustomerKey` сохраняются на intent и подписку,
  recurrent-списание продлевает период той же подписки (без новой строки),
  неудачные продления копят `renewal_attempts` и отключают автопродление
  после 5 попыток, пользовательский toggle `auto-renew`, owner-эндпоинт
  `POST /v1/platform-admin/billing/renewals/run` и CLI
  `python -m app.billing.renewals` (идеампотентный по периоду). Чеки 54-ФЗ
  передаются в Init как для initial, так и для recurrent (Receipt в payload,
  токен не покрывает вложенные поля — тест зафиксирован). Полный demo-цикл
  покрыт тестами `test_tbank_billing.py` (16 passed; весь backend 426 passed).
- 2026-08-08, Этап 5.x — стабильность и зелёные гейты: миграция
  `059_tbank_recurring.sql` не выставляла `user_version = 59`, из-за чего
  dev-стек падал на рестарте (`duplicate column name: kind` после частичного
  применения) — версия-сет добавлен в файл, dev-БД починена без потери
  данных (user_version 58→59); исправлен SyntaxError в
  `billing/service.py` (двойной `*` в `_provider_payload`); recurring-тесты
  устойчивы к wall-clock (окно +5s вместо точной секунды); контрактные тесты
  приведены к реальному коду (regex композера `!isRunning && !isEmpty`,
  ожидаемая миграция `059`, `user_version = 59`). `npm run verify` зелёный,
  backend 426 passed.
- 2026-08-08, Мобильный интерфейс (премиум/паритет/QA):
  - РЕАЛЬНЫЕ QA-тесты вместо статики: `scripts/qa-mobile-chat.mjs` чинит
    ложный FAIL (тест шёл 6 коротких сообщений, которые не переполняли
    viewport, и использовал TS-дженерик `querySelectorAll<HTMLElement>` в
    браузерном evaluate — это парсилось как сравнения и возвращало пустой
    список); теперь 12 длинных сообщений + проверка wheel-скролла вверх/вниз
    и автоскролла к новому сообщению, стабилен 2+ прогона.
    `scripts/qa-mobile-flow.mjs` — register → chat → reload (persist) →
    drawer → new thread → account → logout/login, каждый шаг с реальной
    проверкой. Подключены: `npm run test:qa:mobile[:chat|:flow]`.
  - Критические фиксы PWA: `Alert.alert` в react-native-web — no-op, из-за
    чего «Выйти», отмена правок и действия в списке задач молча не работали;
    добавлен `lib/dialogs.tsx` (confirmAsync + actionSheetAsync + DialogsHost),
    все 4 места переведены на него. Drawer: панель получала z-index ниже
    полноэкранного scrim — тапы на пункты drawer уходили в «Close drawer»;
    поднят zIndex панели.
  - Паритет: мобильный селектор модели/агента (`model-selector.tsx` +
    `src/models/client.ts`, каталог `/v1/models/catalog`, сохранение через
    PUT `/v1/profile/model-settings`) — проверен живым e2e (выбор OpenAI GPT
    обновляет pill, без ошибок); follow-up suggestions после ответа
    ассистента; мобильный парсер профиля допускает `:` для
    `platform:...`-моделей (реальный баг входа с выбранной платформенной
    моделью).
  - Нативный mobile billing UI (`native-billing-settings.tsx`): список
    тарифов, статус подписки, toggle автопродления, оплата через
    Linking.openURL(paymentUrl) + поллинг подтверждения, обновление
    entitlement. Web-контракт расширен autoRenew/renewalAttempts/
    rebillConfigured.
  - Экспорты: `export:web`, `export:ios`, `export:android` — все три прошли.
  - E2E: composer.spec.ts (slash-commands, @-mentions, stop, thread list,
    attachments) — 5 passed; устранено повреждение QA-сессии acceptance-сюита
    (browser.newContext в тестах наследует project storageState — теперь
    clearCookies перед регистрацией); desktop acceptance 17 passed / 3 flaky
    (ретраи 2, CPU-нагрузка dev-стека); `npm run verify` зелёный.
- 2026-08-11/12, Этап 7 (release-гейты) — восстановлен и доведён до зелёного
  полный контур:
  - `npm run verify:full` зелёный: backend `435 passed`, web `194 passed`,
    mobile `21 passed`, typecheck/lint/build, Rust fmt/clippy/tests;
    desktop E2E `20 passed / 0 failed` (composer stop стабилен без ретраев).
  - Исправлен флаки composer stop: фронтенд опрашивал
    `estimate/generation` без capability `construction.estimates.workspace`
    и получал 403 в консоли. Виджет теперь опрашивает только при наличии
    capability и молча останавливается на 403/404
    (`components/assistant-ui/product-widgets/estimate-generation-status.tsx`,
    `lib/estimate/generation.ts`).
  - Исправлен retry-контракт прямых провайдеров: `*_rate_limited` и
    `*_request_failed` помечены retryable (раньше durable-генерация падала с
    первой попытки), добавлен backoff (3 с в плане, 5 с в пуле задач). Живое
    подтверждение на dev-стеке: attemptCount 1 → 3, `retryable=1`.
  - QA-фикстура: `--provider codex-cli|mimo-code` выдаёт верифицированное
    провайдерское соединение QA-тенанту (`qa_tenant_fixture.py`); live-спека
    провайдер-нейтральна (codex-cli/mimo-code/openai/deepseek/qwen/gemini).
  - Внешний блокер live-прогона сметы: OpenAI `credit_balance_exhausted`
    (нет кредитов), MiMo `quota exhausted` (429), Codex CLI разлогинен
    (сессия ChatGPT удалена при проверке `codex exec`). Полный live-прогон
    «запрос → AI → смета → экспорт → редактирование» выполняется после
    предоставления рабочего провайдера.
- 2026-08-12, Этап 7 (фикс «DeepSeek не составляет сметы») — structured-
  вызовы DeepSeek/OpenAI/Qwen теперь передают модели точную JSON-схему и
  `response_format: {"type":"json_object"}`. Раньше адаптеры игнорировали
  `output_schema` и `mode="structured"`: модель возвращала Markdown-обёртку,
  план/разделы/ревью не парсились — в журнале run'ов это видно как
  `estimate_role_output_invalid` на стадии technology. Добавлены тесты
  payload-контракта (`test_agent_runtime.py`, +5). Backend `438 passed`.

## 1. Цель

Kolibri V3 — премиальный chat-first продукт: рабочие web и мобильный клиенты,
стабильные чаты с реальными моделями (включая DeepSeek), полностью
интегрированные платежи (T-Банк, подписки, чеки) и проходимые release-гейты.

## 2. Диагностика (проверено 2026-08-08 на работающем dev-стеке)

### 2.1. Мобильная версия не открывается

- Воспроизведение: `curl -A '<iPhone UA>' http://127.0.0.1:3103/app` → HTTP 502
  `ui_upstream_unavailable`.
- Причина: Expo web слушает только `[::1]:4104` (IPv6, `--host localhost`),
  а `scripts/dev-mobile-private-bridge.mjs` и `dev-stack.mjs` хардкодят upstream
  `127.0.0.1:4104` (IPv4). Bridge не может достучаться до Expo.
- Дополнительно: `lsof` показывает `[::1]:4104 (LISTEN)`, соединения по IPv4
  получают `ECONNREFUSED`.

### 2.2. Чат не работает с реальными моделями

Локальный AG-UI контур работает (SSE: RUN_STARTED → TEXT_MESSAGE_* →
RUN_FINISHED). Реальные вызовы моделей падают:

- `agentProfile: openai` → `agent_profile_not_registered`. Причина: `config.py`
  читает `OPENAI_API_KEY`, но `scripts/dev-backend.sh` экспортирует из
  `.env.local` только ключи `KOLIBRI_V3_*`/`KOLIBRI_PUBLIC_*`/`NEXT_PUBLIC_*`.
  OpenAI runtime не регистрируется.
- `agentProfile: qwen` → `qwen_request_failed` HTTP 400. Проверка напрямую:
  DashScope отвечает `Arrearage` (задолженность по аккаунту) — внешний фактор.
  Дефолт `qwen3.8-max` также не является валидным ID модели в compatible-mode.
- `agentProfile: auto` для обычного пользователя → `codex_login_required`:
  auto резолвится в `codex-cli` (зарегистрирован первым и есть provider
  connection владельца), а не в key-backed провайдера.

### 2.3. `npm run verify` (quick) не зелёный

- ruff E402: `backend/app/platform_models.py:159,160,231` — импорты не в начале
  файла.
- ruff F821: `backend/tests/test_direct_model_selection.py:155,157` — не
  импортированы `AgentRuntimeRequest`/`AgentRuntimeResult`.
- `npm test` (1 fail): `tests/design-contract.test.mjs:218` — рефакторинг
  `components/assistant-ui/product-widgets/estimate-editor.tsx` удалил мобильный
  срез (`data-slot="estimate-mobile-list"`, `matchMedia(max-width: 959px)`,
  `min-[960px]:hidden`, `hidden overflow-x-auto min-[960px]:block`).

Пройдено: `verify:structure`, `verify:architecture`, `compileall`, `typecheck`
(web + mobile), mobile lint, backend-тесты (выборочно 35 passed).

### 2.4. DeepSeek не интегрирован

Провайдер отсутствует в `config.py`, `direct_model_runtime.py`,
`model_catalog.py`, `platform_models.py`, фронтенд-контрактах. Ключа
`DEEPSEEK_API_KEY` нет ни в `.env.local`, ни в окружении.

### 2.5. Платежи: реализован базовый контур, не хватает «премиума»

Реализовано: T-Банк v2 (`backend/app/billing/`: payment intents, webhook с
проверкой подписи, return-обработка, refund, receipt-конфигурация, подписки и
entitlement-переходы, admin-представления), тариф `koli.launch` = 9900 ₽/мес в
БД, веб checkout-overlay и секция аккаунта, mobile web billing settings.

Не хватает: recurring/rebill (автопродление подписок), сквозного
демо-тестирования полного цикла, нативного mobile billing UI, полного
production-гейта и подтверждённых настроек терминала.

## 3. Порядок исполнения

### Этап 1. Зелёные гейты (быстрые фиксы)

| # | Задача | Файлы | Приёмка |
| --- | --- | --- | --- |
| 1.1 | Перенести импорты в начало модуля | `backend/app/platform_models.py` | ruff без E402 |
| 1.2 | Импортировать `AgentRuntimeRequest`, `AgentRuntimeResult` | `backend/tests/test_direct_model_selection.py` | ruff без F821 |
| 1.3 | Восстановить мобильный срез редактора смет (карточки для ширины < 960px) | `components/assistant-ui/product-widgets/estimate-editor.tsx` | `tests/design-contract.test.mjs` зелёный, десктопная таблица не изменена |
| 1.4 | Полный прогон | — | `npm run verify` (quick) зелёный |

### Этап 2. Мобильный рантайм

| # | Задача | Файлы | Приёмка |
| --- | --- | --- | --- |
| 2.1 | Dual-stack соединение bridge (IPv4 + IPv6) или принудительный `--host 127.0.0.1` у Expo | `scripts/dev-mobile-private-bridge.mjs`, `scripts/dev-mobile.mjs`, `scripts/dev-stack.mjs` | iPhone UA на `3103/app` → 200 и контент Expo |
| 2.2 | Регрессионный smoke-скрипт gateway (desktop + mobile UA) | `scripts/`, `tests/` | Проверка входит в verify или CI-скрипт |
| 2.3 | API base для мобильного web: same-origin через gateway (или документированный dev-контракт) | `apps/kolibri-mobile/src/auth/mobile-session.tsx`, gateway | Чат и авторизация работают с реального устройства в PWA |
| 2.4 | Сборки Expo: `export:web`, `export:ios`, `export:android` | — | Все три сборки проходят |
| 2.5 | Сквозной мобильный чат через gateway | — | Сообщение → SSE-ответ → история сохраняется |

### Этап 3. Чат

| # | Задача | Файлы | Приёмка |
| --- | --- | --- | --- |
| 3.1 | Экспорт провайдерских ключей из `.env.local` (или `KOLIBRI_V3_*`-алиасы в config) | `scripts/dev-backend.sh`, `backend/app/config.py` | `openai` профиль регистрируется и отвечает |
| 3.2 | Auto-резолюция: для standard chat не выбирать `codex-cli`; приоритет key-backed провайдеров | `backend/app/direct_model_runtime.py` | `auto` выбирает первый доступный key-backed runtime |
| 3.3 | Валидный дефолт Qwen (`qwen-plus`/`qwen-max`) и понятные ошибки провайдеров | `backend/app/config.py`, `direct_model_runtime.py` | Ошибки модели человекочитаемы, дефолт валиден |
| 3.4 | Сквозной тест чата: web + mobile, streaming, cancel, history, reload | `tests/` | Все сценарии проходят |

### Этап 4. DeepSeek

| # | Задача | Файлы | Приёмка |
| --- | --- | --- | --- |
| 4.1 | Конфигурация провайдера (ключ, base URL `https://api.deepseek.com`, модель `deepseek-chat`) | `backend/app/config.py`, `.env.example` | `DEEPSEEK_API_KEY` читается |
| 4.2 | Runtime: `_deepseek_response` (OpenAI-совместимый streaming) и `_deepseek_runtime_adapter`; регистрация с высоким приоритетом auto | `backend/app/direct_model_runtime.py` | Профиль `deepseek` отвечает стримингом |
| 4.3 | Каталог и подключение: availability, profile entry, env-key fallback | `backend/app/model_catalog.py`, `direct_model_runtime.py` | `auto` выбирает DeepSeek при наличии ключа |
| 4.4 | Admin-провайдер (опционально платформенная модель) | `backend/app/platform_models.py` | `_PROVIDER_DEFAULTS["deepseek"]` |
| 4.5 | Фронтенд: контракты и label | `lib/models/client.ts`, `lib/identity/contracts.ts`, `components/assistant-ui/model-profile-selector-control.tsx` | Модель видна в селекторе |
| 4.6 | Тесты: config, catalog, runtime registration, live smoke (нужен ключ) | `backend/tests/` | Новые тесты + живой запрос |

### Этап 5. Платежи — премиум-контур

| # | Задача | Файлы | Приёмка |
| --- | --- | --- | --- |
| 5.1 | Сквозной demo-цикл T-Банк: intent → return → webhook → entitlement | `backend/app/billing/`, `backend/tests/` | Полный цикл в demo-режиме автоматизирован |
| 5.2 | Автопродление подписок (recurring/rebill) | миграция, `billing/service.py`, `billing/tbank.py` | Recurrent-платежи продлевают подписку |
| 5.3 | 54-ФЗ чеки: отправка и retry при успешном платеже | `billing/service.py` | Receipt-запись + audit |
| 5.4 | Нативный mobile billing UI (подписка, статус, возврат) | `apps/kolibri-mobile/` | Покупка с телефона |
| 5.5 | Production-гейт: терминал, HTTPS, `KOLIBRI_V3_TBANK_PRODUCTION_CONFIRMED`, rehearsal | `deploy/portable/`, `billing/config.py` | Проверенный rollback-сценарий |
| 5.6 | Admin UI планов и возвратов (если нет) | `components/kolibri-shell/` | Управление из интерфейса |

### Этап 6. Премиум-полировка

- `docs/DESKTOP_UX_ARCHITECTURE_AUDIT.md`: collapsible sidebar, корректный
  zoom 200%, виртуализация смет (1000+ строк), batch edit / copy-paste.
- Мобильный UX: пустые/loading/error-состояния, клавиатура, safe areas,
  reduced motion, accessibility.
- Производительность: размеры бандлов Next/Expo, latency streaming.
- Локализация RU/EN (по решению владельца).

### Этап 7. Релиз

- `npm run verify:full` зелёный (build, mobile typecheck/lint/test).
- e2e desktop acceptance + mobile smoke.
- Expo export ios/android; portable release rehearsal.
- Release evidence → R2; обновить `docs/PROJECT_MAP.md`,
  `docs/SOURCE_OF_TRUTH.md`, README, CHANGELOG.

## 4. Риски и внешние зависимости

- `DEEPSEEK_API_KEY` отсутствует: интеграция делается полностью, живой smoke
  — после предоставления ключа.
- Qwen-аккаунт в arrears: внешний фактор, не блокирует (DeepSeek/OpenAI
  становятся основными провайдерами).
- T-Банк: нужны demo-терминал и (для production) подтверждённые настройки;
  production-гейт без ключей не выполняется.
- Изменения dev-рантайма требуют `npm run dev:persistent:restart` и не должны
  ломать существующий стек.

## 5. Решение по объёму

Этапы 1–4 выполняются сразу (фиксы + DeepSeek). Этапы 5–7 требуют внешних
ключей/решений владельца по объёму платёжных методов (T-Банк-only или
мультипровайдер) и запускаются после согласования.
