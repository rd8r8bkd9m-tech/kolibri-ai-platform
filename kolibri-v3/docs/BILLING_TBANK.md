# T-Банк (Т-Касса): серверный контур оплаты Kolibri V3

Статус: безопасный test-mode путь реализован, production выключен. Реальные
платежи, отмены и возвраты не выполнялись. Личный кабинет Т-Бизнес был только
прочитан и не изменялся.

## Источники и выбранный протокол

Интеграция основана только на актуальной официальной документации Т-Банка:

- [Инициировать платеж (`/v2/Init`)](https://developer.tbank.ru/eacq/api/init):
  сумма передается целым числом в копейках, `OrderId` должен быть уникальным,
  банк возвращает hosted payment URL;
- [формирование `Token`](https://developer.tbank.ru/eacq/intro/developer/token):
  участвуют только поля корневого объекта, добавляется `Password`, ключи
  сортируются, значения конкатенируются и хешируются SHA-256; вложенные
  `Receipt` и `DATA` не участвуют;
- [HTTP(S)-уведомления](https://developer.tbank.ru/eacq/intro/developer/notification):
  токен проверяется до обработки, успешный ответ — HTTP 200 с точным телом
  `OK`; банк повторяет недоставленные уведомления;
- [получение статуса (`/v2/GetState`)](https://developer.tbank.ru/eacq/api/get-state);
- [тестовая среда](https://developer.tbank.ru/eacq/intro/errors/test):
  `https://rest-api-test.tinkoff.ru/v2`, терминал без `DEMO`, IP источника
  должен быть добавлен в allowlist;
- [dashboard test cases](https://developer.tbank.ru/eacq/intro/errors/test-cases):
  терминал `DEMO` работает через `https://securepay.tinkoff.ru/v2`;
- [фискализация и чеки](https://developer.tbank.ru/eacq/scenarios/fiscalization);
- [отмена и возврат](https://developer.tbank.ru/eacq/scenarios/cancel_confirm/).

Kolibri использует банковскую hosted-форму только для web/PWA и прямых B2B
продаж. Приложение не принимает и не хранит PAN, CVV, срок действия карты или
3-D Secure данные.

MVP — только разовая покупка фиксированного периода с ручным продлением и
`PayType=O`. Запрос не содержит `Recurrent=Y`, `CustomerKey` или `RebillId`.
Автосписания требуют отдельного согласия пользователя, cancel/dunning UX,
повторных чеков и включения MIT COF менеджером банка; это отдельная phase 2.

Native iOS/Android не должны жестко вести пользователя в T‑Кассу для digital
SaaS. Будущий phase 2 добавит проверенные StoreKit/Google Play events как
provider adapters к общей server-owned entitlement authority. Клиентское
подтверждение покупки никогда не является authority.

Тип авторизации не определяет surface: Expo web/PWA может законно использовать
bearer. T‑Касса выбирается web checkout BFF и UI конкретной сборки; native
iOS/Android UI этот способ не показывает. Это продуктовая/store policy, а не
security boundary токена.

## Каноническая архитектура

Данные принадлежат V3 backend и append-only миграциям:

1. `billing_entitlement_catalog` — generic allowlist entitlement codes. Текущий
   `construction.estimates.use` добавлен как approved vertical data, а не
   зашит в CHECK schema.
2. `billing_plans` — утвержденный сервером каталог цены и фискальных атрибутов.
   После миграции таблица намеренно пуста.
3. `billing_payment_intents` — immutable snapshot тарифа, целая сумма в
   копейках, точный tenant/user, idempotency key, детерминированный для intent
   `OrderId`, среда терминала, `return_surface` (`web` или `pwa`) и состояние
   провайдера. Surface входит в idempotency hash: один ключ нельзя повторно
   использовать для другого landing flow.
4. `billing_notification_events` — digest и результат каждого проверенного
   уведомления без сырого payload и платежных реквизитов.
5. `billing_subscriptions` — фиксированный период доступа, созданный только после валидного
   `CONFIRMED`.
6. `billing_audit_events` — безопасный журнал intent/init/webhook/subscription.

Секрет терминала находится только в `KOLIBRI_V3_TBANK_PASSWORD`. В БД хранится
лишь 16-символьный SHA-256 fingerprint идентификатора терминала; сам пароль,
`Token` и callback nonce не сохраняются. HTTP-журнал V3 пишет только шаблон
маршрута, без query string и тела.

## Состояния и защита от replay

`AUTHORIZED` не активирует продукт. Доступ появляется только при одновременно
выполненных условиях:

- токен уведомления проверен constant-time сравнением;
- `TerminalKey`, `OrderId`, `PaymentId` и `Amount` совпали с локальным intent;
- `Success=true`, `ErrorCode=0`, `Status=CONFIRMED`;
- транзакция создала ровно одну подписку для payment intent;
- entitlement связан с теми же `tenant_id` и `user_id`.

Повтор одного notification digest возвращает `OK`, но не повторяет эффект.
Запоздалый `AUTHORIZED` не откатывает `CONFIRMED`; частичная отмена
`PARTIAL_REVERSED` и частичный возврат `PARTIAL_REFUNDED` сохраняют отдельное
состояние `partially_refunded` и не отзывают grant автоматически. `REFUNDED`
является более поздним состоянием и отзывает только grant с источником
`subscription_policy`, если нет другой действующей подписки. Истекший период перестает
проецироваться в browser/mobile session даже до фоновой уборки строки.

`SuccessURL` и `FailURL` содержат отдельный HMAC-derived nonce. Landing endpoint
игнорирует переданный банком результат и показывает только состояние V3,
полученное из проверенного webhook. Пока webhook не подтвержден, ответ — 202 и
entitlement не активен.

Неоднозначный timeout `Init` не повторяется автоматически: intent становится
`unknown`, чтобы сетевой retry не мог создать второе списание. Сверка такого
случая — отдельная операторская процедура; адаптер `GetState` подготовлен для
будущего reconciler, но клиент не может вызвать его произвольно.

## HTTP-контракты

Публичный production origin обслуживает Next BFF, а не Python-порт напрямую.
Внешние контракты проксируют запрос и ответ без изменения платежной authority:

- `GET /api/v3/billing/plans` — публичный read-only каталог для страницы цен;
- `POST /api/v3/billing/payment-intents`;
- `GET /api/v3/billing/payment-intents/{intentId}`;
- `GET /api/v3/billing/subscriptions`;
- `POST /api/v3/billing/tbank/notifications` — raw JSON bank callback;
- `GET /api/v3/billing/tbank/return/{intentId}`.

Подписанный webhook не использует browser CSRF: Next не добавляет доверие и
только ограниченно пересылает исходные JSON bytes и `Content-Type`; backend
сам проверяет T‑Bank `Token`. Канонический публичный callback:
`https://kolibriai.ru/api/v3/billing/tbank/notifications`.

Внутренние backend-контракты:

- `GET /v1/billing/plans` — публичный read-only каталог без пользовательских
  данных;
- `POST /v1/billing/payment-intents` с `Idempotency-Key`, optional
  `returnSurface: "web" | "pwa"` и browser CSRF либо authenticated bearer
  web/PWA-клиента;
- `GET /v1/billing/payment-intents/{intentId}` — строго свой tenant/user;
- `GET /v1/billing/subscriptions`;
- `POST /v1/billing/tbank/notifications` — публичный callback с обязательной
  подписью;
- `GET /v1/billing/tbank/return/{intentId}` — read-only проверка server state.

Platform owner получает redacted read models (payment URL исключен):

- `GET /v1/platform-admin/billing/config`;
- `GET /v1/platform-admin/billing/plans` — полный серверный каталог, включая
  неактивные тарифы, текущие ревизии и состояние entitlement (только чтение);
- `GET /v1/platform-admin/billing/payments`;
- `GET /v1/platform-admin/billing/subscriptions`;
- `GET /v1/platform-admin/billing/audit`.

Endpoint отмены/возврата намеренно отсутствует. Это исключает случайную
финансовую мутацию из UI или агента. Входящее подписанное уведомление о реально
сделанном в банке полном возврате корректно закрывает локальный доступ.

## Переменные окружения

Все ключи перечислены без секретов в `.env.example`.

```text
KOLIBRI_V3_TBANK_ENABLED=false
KOLIBRI_V3_TBANK_MODE=off|test|demo|production
KOLIBRI_V3_TBANK_TERMINAL_KEY=
KOLIBRI_V3_TBANK_PASSWORD=
KOLIBRI_V3_TBANK_NOTIFICATION_URL=https://kolibriai.ru/api/v3/billing/tbank/notifications
KOLIBRI_V3_TBANK_RETURN_ORIGIN=https://kolibriai.ru
KOLIBRI_V3_TBANK_TIMEOUT_SECONDS=10
KOLIBRI_V3_TBANK_RECEIPT_MODE=disabled|required
KOLIBRI_V3_TBANK_TAXATION=osn|usn_income|usn_income_outcome|esn|patent
KOLIBRI_V3_TBANK_PRODUCTION_CONFIRMED=false
```

Production требует одновременно `KOLIBRI_V3_ENV=production`, HTTPS callback
URL, `MODE=production`, не-DEMO терминал и
`KOLIBRI_V3_TBANK_PRODUCTION_CONFIRMED=true`. Одного случайно вставленного
пароля недостаточно для включения реальных списаний.

## Что нужно решить в личном кабинете Т-Бизнес

Эти значения нельзя определить из репозитория, поэтому агент не должен их
угадывать или менять без владельца:

На 2026-08-01 в кабинете наблюдалось: магазин `Kolibri` имеет статус
«Отклонён» и старый адрес `app.kolibriai.online`; DEMO и рабочий терминалы
выключены. Это read-only наблюдение, а не разрешение включить терминал.

1. какой магазин и какой терминал использовать;
2. какой безопасный тестовый путь выбрать первым:
   - `test` — реальный не-DEMO terminal в test environment + IP allowlist;
   - `demo` — dashboard test cases на DEMO terminal;
3. терминал должен быть одностадийным: реализация отправляет `PayType=O`;
4. подключена ли онлайн-касса; если да — ФФД, СНО, НДС, предмет и способ
   расчета для каждого тарифа должны быть подтверждены владельцем/бухгалтером;
5. подтвердить публичный HTTPS `NotificationURL`
   `https://kolibriai.ru/api/v3/billing/tbank/notifications` и return origin
   `https://kolibriai.ru`;
6. утвержденные `plan_code`, название, цена в копейках и срок доступа;
7. production terminal выбирается только после полного sandbox/demo acceptance
   и отдельного явного разрешения на реальные списания.
8. до повторной заявки на магазин на `kolibriai.ru` должны быть публично
   доступны утвержденные цены и условия, оферта, реквизиты продавца и политика
   возврата; старый отклоненный магазин не переиспользуется вслепую.

До этих решений `billing_plans` остается пустой,
`KOLIBRI_V3_TBANK_ENABLED=false`, а
production confirmation — `false`.

Web/PWA UI в личном кабинете показывает approved plan catalog, запускает intent
с `Idempotency-Key` и `returnSurface: "pwa"`, переходит только на
server-provided hosted `paymentUrl` и проверяет server status/subscription
после возврата. PWA возвращается в `/account?client=mobile`, desktop — в
`/app?account=billing`; оба landing route используют только заранее заданные
внутренние пути. После `CONFIRMED` PWA повторно получает server-owned профиль,
поэтому entitlement обновляется без повторного входа. До утверждения тарифов
интерфейс показывает «Оплата пока не подключена», а не подставляет тестовую
цену. Platform-specific native component возвращает `null`: iOS/Android
account этот способ оплаты не показывает.

## Проверка без сети

`backend/tests/test_tbank_billing.py` использует `httpx.MockTransport` и не
выходит в интернет. Тесты проверяют официальный token vector, пустой каталог,
CSRF/idempotency, hosted URL, неверную подпись, `CONFIRMED`, duplicate replay,
out-of-order `AUTHORIZED`, expiration, `REFUNDED`, tenant isolation и redacted
admin contracts.
