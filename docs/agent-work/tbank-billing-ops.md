# T-Банк billing/subscription operations pack

Дата: 2026-06-29  
Роль: `billing_tbank_operator`  
Область: тарифы, checkout, fallback lead, notification security, charge-due, lifecycle, QA, продуктовые статусы и клиентские сообщения для Kolibri AI Platform.

## 1. Краткий регламент

Kolibri продает подписки через панель `Контрол -> Подписки`. Backend отдает тарифы, создает первичный платеж в T-Банке или сохраняет fallback-заявку, принимает подписанные уведомления от T-Банка и запускает повторные списания через защищенный admin endpoint.

Рабочий контур считается готовым только когда выполнены четыре условия:

1. `/api/billing/plans` возвращает `provider: "tbank"` и `configured: true`.
2. `KOLIBRI_PUBLIC_URL` ведет на публичный HTTPS-адрес приложения, доступный T-Банку для `NotificationURL`.
3. Тестовый терминал T-Банка успешно проходит первичный платеж, HTTP(S)-уведомление и повторное списание через `Charge`.
4. Онлайн-касса, фискализация и юридические тексты подтверждены владельцем бизнеса. Текущий код не отправляет `Receipt`, поэтому нельзя обещать production-фискализацию без отдельного кассового контура.

Production blocker-кандидат: актуальная документация T-Банка описывает `OperationInitiatorType` как обязательный параметр для родительского CC-платежа. Backend отправляет `DATA.OperationInitiatorType` для первичного recurrent checkout и recurring charge init; это нужно подтвердить на тестовом терминале и, если Т-Банк ожидает другое значение для конкретного терминала, исправить до боевого запуска.

Если T-Банк не настроен, продукт не блокирует продажу: checkout сохраняет fallback lead и показывает клиенту сообщение о заявке. Активная подписка в этом режиме не создается.

P0 acceptance gaps, найденные 2026-06-29:

- первичный recurrent checkout должен отправлять `DATA.OperationInitiatorType = "1"` вместе с `Recurrent = "Y"`;
- recurring `Init` перед `Charge` должен отправлять `DATA.OperationInitiatorType = "R"`;
- successful notification может активировать или продлить подписку только если `TerminalKey` совпадает, `OrderId` известен, `PaymentId` не пустой и `Amount` совпадает с тарифом;
- повторный successful notification по тому же `OrderId`/`PaymentId` не должен повторно продлевать период;
- notification по recurring charge должен находить подписку через audit event нового `OrderId`, иначе повторные списания не продлевают lifecycle.

Эти пункты закреплены в backend-тестах без реальных финансовых операций. До production всё равно остаются внешние P0-блокеры: sandbox-платеж с реальным тестовым терминалом, проверка доставки notification через публичный HTTPS и отдельное решение по онлайн-кассе/фискализации.

## 2. Источники и текущая реализация

Локальные источники:

- `backend/billing.py` - тарифы, checkout, token signing, notification handler, charge-due.
- `backend/tests/test_billing.py` - текущие unit-тесты токена и fallback lead.
- `frontend/src/components/control/BillingPanel.jsx` - UI подписок.
- `frontend/src/App.jsx` - загрузка тарифов, checkout submit, success/fail сообщения после redirect.
- `docs/api.md` - публичные billing endpoints.

Официальные документы T-Банка, с которыми сверялся регламент:

- T-Банк Dev Portal, "Начало работы": `https://developer.tbank.ru/eacq/intro`
- T-Банк Dev Portal, `Init`: `https://developer.tbank.ru/eacq/api/init`
- T-Банк Dev Portal, `Charge`: `https://developer.tbank.ru/eacq/api/charge`
- T-Банк Dev Portal, "Токен": `https://developer.tbank.ru/eacq/intro/developer/token`
- T-Банк Dev Portal, "Уведомления об операциях": `https://developer.tbank.ru/eacq/intro/developer/notification`

## 3. Тарифы

Тарифы задаются в `PLANS` и возвращаются через `GET /api/billing/plans`.

| Plan ID | Название | Цена по умолчанию | Env override | Лимит | Для кого | Highlights |
| --- | --- | ---: | --- | --- | --- | --- |
| `solo` | Solo | 4 900 ₽/мес | `KOLIBRI_PLAN_SOLO_KOPEKS` | до 30 смет в месяц | мастер или небольшой подрядчик | AI-сметы, КП и счет, экспорт PDF |
| `team` | Team | 14 900 ₽/мес | `KOLIBRI_PLAN_TEAM_KOPEKS` | до 150 смет в месяц | ремонтная бригада или отдел продаж | документы пакетом, база знаний, приоритетная фабрика |
| `studio` | Studio | 39 900 ₽/мес | `KOLIBRI_PLAN_STUDIO_KOPEKS` | безлимитный операционный контур | строительная компания или проектное бюро | свой шаблон документов, онбординг команды, выделенные сценарии |

Операционные правила:

- цены хранятся в копейках;
- `OrderId` ограничен 36 символами и создается как `sub_<plan_id>_<uuid-fragment>`;
- `CustomerKey` вычисляется из normalized email как `cust_<sha256(email)[:24]>`;
- апгрейды/даунгрейды в текущем коде не реализованы отдельным endpoint, поэтому проводятся как новая подписка или ручная операция владельца до появления change-plan flow.

## 4. Environment и provider status

Обязательные переменные для платежного режима:

```text
TBANK_TERMINAL_KEY
TBANK_PASSWORD
KOLIBRI_PUBLIC_URL
KOLIBRI_BILLING_ADMIN_TOKEN
```

Опционально:

```text
TBANK_API_URL=https://securepay.tinkoff.ru/v2
KOLIBRI_PLAN_SOLO_KOPEKS=490000
KOLIBRI_PLAN_TEAM_KOPEKS=1490000
KOLIBRI_PLAN_STUDIO_KOPEKS=3990000
```

Правила статуса:

| Условие | `/plans.configured` | Checkout mode | UI-кнопка | Операционное значение |
| --- | --- | --- | --- | --- |
| `TBANK_TERMINAL_KEY` и `TBANK_PASSWORD` заданы | `true` | `payment` | `Оплатить через Т-Банк` | можно создавать платежную ссылку |
| хотя бы одна переменная отсутствует | `false` | `lead` | `Сохранить заявку` | сохраняем лид, не создаем подписку |

## 5. Checkout flow

Endpoint: `POST /api/billing/checkout`

Запрос:

```json
{
  "plan_id": "team",
  "email": "client@company.ru",
  "name": "Алексей",
  "company": "Ремонтная компания",
  "phone": "+7..."
}
```

Валидация:

- `plan_id`: 2-32 символа, должен быть одним из `solo`, `team`, `studio`;
- `email`: 5-160 символов, базовый email pattern;
- `name`: до 80 символов;
- `company`: до 120 символов;
- `phone`: до 40 символов.

### 5.1 Payment mode

Когда T-Банк настроен, backend вызывает `/v2/Init` с:

- `TerminalKey`;
- `Amount`;
- `OrderId`;
- `Description = "Kolibri AI <Plan> на 1 месяц"`;
- `CustomerKey`;
- `Recurrent = "Y"`;
- `PayType = "O"`;
- `Language = "ru"`;
- `DATA.OperationInitiatorType = "1"`;
- `NotificationURL = <KOLIBRI_PUBLIC_URL>/api/billing/tbank/notification`;
- `SuccessURL = <KOLIBRI_PUBLIC_URL>/?payment=success&order=<order_id>`;
- `FailURL = <KOLIBRI_PUBLIC_URL>/?payment=fail&order=<order_id>`.

Успешный ответ backend:

```json
{
  "mode": "payment",
  "provider": "tbank",
  "subscription_id": "sub_...",
  "order_id": "sub_team_...",
  "payment_id": "123456789",
  "payment_url": "https://..."
}
```

Действия:

1. Frontend перенаправляет клиента на `payment_url`.
2. Backend создает подписку `pending_payment`.
3. Backend пишет событие `tbank_init`.
4. Возврат клиента по `SuccessURL` не активирует подписку сам по себе; продукт показывает промежуточное сообщение и ждет подписанное уведомление T-Банка.

Pre-prod проверка `Init`: если тестовый терминал возвращает ошибку по `Recurrent`, `RebillId` или `OperationInitiatorType`, зафиксировать payload и исправить backend до production. Не обходить эту ошибку ручной активацией подписки.

### 5.2 Fallback lead mode

Когда T-Банк не настроен:

```json
{
  "mode": "lead",
  "provider": "tbank",
  "configured": false,
  "message": "Заявка сохранена. Для оплаты подключите TBANK_TERMINAL_KEY и TBANK_PASSWORD."
}
```

Действия:

1. Backend сохраняет запись в `billing_leads`.
2. Подписка не создается.
3. T-Банк не вызывается.
4. Оператор связывается с клиентом вручную и предлагает счет, демо, пилот или повторить оплату после включения терминала.

SLA fallback-лида:

- `0-2 часа`: проверить корректность контактов и тариф;
- `до конца рабочего дня`: отправить клиенту ручное подтверждение;
- `до 1 рабочего дня`: либо выставить альтернативный счет, либо вернуть клиента в checkout после включения T-Банка;
- после включения T-Банка: попросить клиента пройти checkout заново, чтобы появился `RebillId` для подписки.

## 6. Notification security

Endpoint: `POST /api/billing/tbank/notification`

Handler принимает `application/json` или form payload, затем проверяет `Token`.

Правила токена:

1. Исключить поле `Token`.
2. Исключить вложенные объекты, массивы, `null`.
3. Boolean привести к `true`/`false` в нижнем регистре.
4. Добавить `Password = TBANK_PASSWORD`.
5. Отсортировать ключи по алфавиту.
6. Склеить значения.
7. Посчитать SHA-256 UTF-8.
8. Сравнить с полученным `Token` через constant-time compare.

Безопасность и эксплуатация:

- `TBANK_PASSWORD` никогда не логировать и не возвращать в API;
- не считать `SuccessURL` доказательством оплаты;
- активировать доступ только по валидному T-Банк notification;
- отвечать `HTTP 200` и телом `OK` только после успешной обработки;
- при невалидном токене возвращать `400 Invalid T-Bank token`;
- хранить сырые payloads в `billing_events`, но перед внешней отправкой логов маскировать `Pan`, `CardId`, `RebillId`, `Token`, email и phone;
- ожидать дубли уведомлений: T-Банк может повторять доставку, если не получил `OK`;
- `NotificationURL` должен быть публичным HTTPS URL, порт 443 предпочтителен;
- при смене `TBANK_PASSWORD` проверить и исходящие подписи, и входящие notification tokens.

## 7. Subscription lifecycle

Таблица `billing_subscriptions` хранит:

- клиента: `customer_email`, `customer_name`, `company`, `phone`, `customer_key`;
- тариф: `plan_id`, `plan_name`, `amount_kopeks`, `currency`;
- платеж: `order_id`, `payment_id`, `rebill_id`, `payment_url`;
- период: `current_period_start`, `current_period_end`, `next_charge_at`;
- статус: `status`;
- аудит: `created_at`, `updated_at`.

Статусы:

| Статус | Кто ставит | Когда | Доступ клиенту | Операторское действие |
| --- | --- | --- | --- | --- |
| `pending_payment` | checkout | после успешного `Init`, до notification | еще не активировать платные лимиты | ждать notification, проверить оплату при задержке |
| `active` | notification | `AUTHORIZED`, `CONFIRMED` или `COMPLETED` + `Success=true` | включить платный тариф | убедиться, что `rebill_id` получен для автосписаний |
| `past_due` | notification | `REJECTED` | оставить grace period вручную или ограничить продление | написать клиенту, предложить повторить оплату |
| `canceled` | notification | `CANCELED`, `DEADLINE_EXPIRED`, `ATTEMPTS_EXPIRED`, `REVERSED`, `REFUNDED` | отключить продление, доступ по политике владельца | объяснить статус, предложить новый checkout |

События:

| Event type | Когда пишется | Что проверять |
| --- | --- | --- |
| `tbank_init` | создан первичный платеж | `PaymentURL`, `PaymentId`, `Status` |
| `tbank_notification` | пришел callback | token valid, `OrderId`, `PaymentId`, `Status`, `Success`, `RebillId` |
| `tbank_rebill_init_failed` | не удалось создать платеж для продления | ошибка T-Банка, терминал, лимиты, уникальность `OrderId` |
| `tbank_charge` | вызван `Charge` | `Success`, `Status`, `PaymentId`, наличие email |

Период:

- при активации `current_period_start = now`;
- `current_period_end = now + 30 days`;
- `next_charge_at = current_period_end`;
- точные календарные месяцы, proration и grace period пока не реализованы кодом.

## 8. Charge-due

Endpoint: `POST /api/billing/tbank/charge-due`

Защита:

```text
X-Kolibri-Billing-Token: <KOLIBRI_BILLING_ADMIN_TOKEN>
```

Запрос:

```json
{
  "limit": 20
}
```

Выборка подписок:

- `status = 'active'`;
- `rebill_id IS NOT NULL`;
- `next_charge_at IS NOT NULL`;
- `next_charge_at <= now`;
- сортировка по `next_charge_at ASC`;
- лимит 1-100.

Алгоритм списания:

1. Создать новый `OrderId`.
2. Вызвать `/v2/Init` для продления с тем же `CustomerKey`, суммой, тарифом и `DATA.OperationInitiatorType = "R"`.
3. Если `Init` успешен и вернул `PaymentId`, вызвать `/v2/Charge` с `PaymentId`, `RebillId`, `SendEmail=true`, `InfoEmail=<customer_email>`.
4. Записать `tbank_charge`.
5. Вернуть summary.

Операционный запуск:

- cron/systemd timer не чаще 1 раза в сутки, например 09:10 Europe/Moscow;
- в первые дни production запускать с `limit: 1`, затем повышать до 20;
- перед запуском убедиться, что нет массового incident по T-Банку или кассе;
- если `processed=0`, это нормальный результат, когда нет подписок к списанию;
- если много `charged=false`, остановить расписание и разобрать `billing_events`.

Важно: текущий `charge_due` не продлевает период по прямому ответу `Charge`; финальная активация/продление должна приходить через notification. До проверки production-webhook не считать повторные списания завершенными.

## 9. Product statuses

Эти статусы нужны для UI, support и QA.

| Product status | Источник | Клиентский смысл | Текстовая политика |
| --- | --- | --- | --- |
| `billing_unconfigured` | `/plans.configured=false` | оплата временно как заявка | не обещать мгновенный доступ |
| `plans_loaded` | `/plans.plans[]` | тарифы доступны | показать цены и лимиты |
| `checkout_ready` | выбран тариф + валидный email | можно отправлять форму | кнопка зависит от provider status |
| `lead_saved` | checkout `mode=lead` | заявка принята | оператор свяжется вручную |
| `payment_redirect` | checkout `payment_url` | клиент ушел на оплату | ждать redirect/notification |
| `payment_return_success` | `?payment=success` | банк вернул клиента после оплаты | сказать, что подписка активируется после подтверждения |
| `payment_return_fail` | `?payment=fail` | клиент не завершил оплату | предложить повторить checkout |
| `pending_payment` | DB subscription | платеж создан, не подтвержден | доступ не включать автоматически |
| `active` | valid notification | подписка активна | включить лимиты тарифа |
| `past_due` | rejected notification | списание не прошло | попросить обновить оплату |
| `canceled` | cancel/refund/expired notification | подписка не продлевается | предложить новый checkout |
| `charge_due_blocked` | 403/503 charge-due | admin token или credentials не готовы | не показывать клиенту, только ops |

## 10. Клиентские сообщения

### 10.1 Тарифы

Solo:

> Solo — для мастера или небольшого подрядчика. До 30 AI-смет в месяц, КП, счет и PDF-экспорт.

Team:

> Team — для ремонтной бригады или отдела продаж. До 150 смет в месяц, пакет документов, база знаний и приоритетная фабрика.

Studio:

> Studio — для строительной компании или проектного бюро. Безлимитный операционный контур, свои шаблоны документов, онбординг команды и выделенные сценарии.

### 10.2 Checkout

Оплата доступна:

> Перенаправляем в защищенную форму Т-Банка. После оплаты Kolibri активирует подписку, когда получит подтверждение от банка.

Fallback lead:

> Заявка сохранена. Сейчас платежный терминал подключается, поэтому мы свяжемся с вами вручную и поможем оформить оплату.

Некорректный email:

> Проверьте email: на него придет подтверждение и платежная информация.

Неизвестный тариф:

> Этот тариф сейчас недоступен. Выберите Solo, Team или Studio.

### 10.3 Redirect result

Success redirect:

> Оплата принята. Подписка активируется после подтверждения Т-Банка.

Fail redirect:

> Платеж не завершен. Откройте Контрол и попробуйте еще раз.

### 10.4 Lifecycle

Активирована:

> Подписка активна. Тариф включен, следующий расчетный период начнется после планового продления.

Не прошла оплата:

> Не удалось продлить подписку. Проверьте карту или повторите оплату через Контрол.

Отмена/истечение:

> Подписка не продлена. Чтобы продолжить работу на платном тарифе, оформите оплату заново.

Refund/reversal:

> Платеж отменен или возвращен. Доступ к платному тарифу будет пересчитан по условиям поддержки.

Security/support:

> Мы не запрашиваем и не храним данные карты в Kolibri. Оплата проходит на стороне Т-Банка.

## 11. Тесты

### 11.1 Уже покрыто

Команда:

```bash
pytest backend/tests/test_billing.py
```

Покрытие:

- генерация T-Банк токена из отсортированных flat values;
- case-insensitive проверка токена;
- tampering detection;
- fallback lead без вызова T-Банка;
- lead payload и отсутствие подписки в fallback mode;
- `OperationInitiatorType` для первичного recurrent checkout и recurring charge init;
- блокировка successful notification без `PaymentId`;
- блокировка successful notification с несовпадающей суммой;
- идемпотентность повторного successful notification по первичному платежу;
- привязка notification от recurring charge к подписке через audit event нового `OrderId`.

### 11.2 Обязательные automated tests перед production

Backend:

- `GET /api/billing/plans` возвращает 3 тарифа, `provider=tbank`, корректный `configured`;
- checkout с неизвестным `plan_id` возвращает 404;
- checkout с невалидным email возвращает 422;
- checkout payment mode с mock `tbank_post("Init")` создает `pending_payment`, `tbank_init`, возвращает `payment_url`;
- payment mode с `Success=false` от T-Банка возвращает 502 и не создает подписку;
- notification с валидным токеном и `Status=CONFIRMED`, `Success=true`, `RebillId` активирует подписку;
- notification с `Status=AUTHORIZED`, `Success=true` активирует подписку;
- successful notification с чужим `TerminalKey`, пустым `PaymentId`, неизвестным `OrderId` или несовпадающим `Amount` не активирует доступ;
- notification с `Status=REJECTED` переводит подписку в `past_due`;
- notification с `CANCELED`, `DEADLINE_EXPIRED`, `ATTEMPTS_EXPIRED`, `REVERSED`, `REFUNDED` переводит в `canceled`;
- notification без `OrderId` возвращает 400;
- notification с невалидным token возвращает 400 и не меняет подписку;
- повторная notification по тому же `OrderId` не ломает статус и пишет audit event;
- charge-due без `X-Kolibri-Billing-Token` возвращает 403;
- charge-due без T-Банк credentials возвращает 503;
- charge-due выбирает только `active` + `rebill_id` + due rows;
- charge-due с mock `Init` failure пишет `tbank_rebill_init_failed`;
- charge-due с mock `Init` + `Charge` пишет `tbank_charge`.

Frontend:

- billing panel показывает три тарифные карточки;
- выбранный тариф меняет `plan_id`;
- при `configured=false` кнопка `Сохранить заявку`;
- при `configured=true` кнопка `Оплатить через Т-Банк`;
- fallback response показывает сообщение;
- payment response с `payment_url` вызывает redirect;
- `?payment=success` добавляет сообщение "Оплата принята...";
- `?payment=fail` добавляет сообщение "Платеж не завершен...".

Security:

- секреты не попадают в stdout, browser console, `billing_events.payload_json` в виде `TBANK_PASSWORD` или `KOLIBRI_BILLING_ADMIN_TOKEN`;
- notification token проверяется до изменения подписки;
- admin charge endpoint недоступен без header;
- `KOLIBRI_PUBLIC_URL` не может быть внутренним host/IP в production;
- payloads с `Pan`, `Token`, `RebillId` маскируются перед отправкой во внешние системы логирования.

### 11.3 Manual T-Банк sandbox/prod-readiness QA

1. Создать/проверить тестовый терминал в личном кабинете T-Бизнес.
2. Убедиться, что включен recurrent flow и метод `Charge` разрешен для терминала.
3. Настроить публичный HTTPS `NotificationURL`.
4. Запустить приложение с тестовыми `TBANK_TERMINAL_KEY`, `TBANK_PASSWORD`, `TBANK_API_URL`.
5. Открыть `Контрол -> Подписки`, выбрать Solo, заполнить email.
6. Убедиться, что checkout возвращает `mode=payment`.
7. Пройти тестовую оплату на платежной форме.
8. Проверить redirect `?payment=success`.
9. Проверить, что backend получил notification и вернул `OK`.
10. Проверить `billing_subscriptions.status=active`.
11. Проверить, что `rebill_id` сохранен.
12. Вручную сделать due подписку в тестовой БД или дождаться due date.
13. Запустить `charge-due` с `limit=1` и admin header.
14. Проверить `tbank_charge` event.
15. Проверить повторное notification по списанию.
16. Проверить negative path: невалидный token, отказ платежа, истекшая ссылка.
17. Проверить, что клиентские сообщения не обещают активацию до notification.

## 12. Incident runbook

### `/plans.configured=false`

Симптомы:

- UI показывает `Сохранить заявку`;
- checkout возвращает `mode=lead`.

Действия:

1. Проверить `TBANK_TERMINAL_KEY` и `TBANK_PASSWORD`.
2. Проверить restart backend после обновления env.
3. Проверить, что не подменен `KOLIBRI_DB_PATH`.
4. Обработать накопившиеся `billing_leads`.

### Checkout 502

Симптомы:

- T-Банк `Init` вернул `Success=false`;
- нет `PaymentURL` или `PaymentId`;
- frontend показывает ошибку оплаты.

Действия:

1. Посмотреть response в `billing_events`, если событие успело записаться, или backend logs.
2. Проверить сумму, уникальность `OrderId`, terminal key, test/prod API URL.
3. Проверить доступность T-Банк API.
4. Не создавать подписку вручную без подтверждения оплаты.

### Notification 400

Симптомы:

- T-Банк callback получает 400;
- подписка остается `pending_payment`.

Действия:

1. Проверить `TBANK_PASSWORD` и алгоритм токена.
2. Проверить, не пришли ли form fields с измененным регистром.
3. Проверить, что payload не был модифицирован reverse proxy.
4. После исправления запросить повторную отправку notification из архива T-Банка или провести новый тестовый платеж.

### Нет `RebillId`

Симптомы:

- подписка активна, но `rebill_id` пустой;
- charge-due не выбирает подписку.

Действия:

1. Проверить, что первичный `Init` отправлял `Recurrent=Y` и `CustomerKey`.
2. Проверить настройки терминала и разрешение recurrent payments.
3. Связаться с поддержкой T-Банка, если `RebillId` не приходит в `AUTHORIZED`/`CONFIRMED`.
4. Не запускать автосписание по такой подписке.

### Массовые `charged=false`

Симптомы:

- `charge-due` обработал много подписок, но `charged=false`;
- есть `tbank_rebill_init_failed` или ошибки `Charge`.

Действия:

1. Остановить расписание charge-due.
2. Сгруппировать ошибки по `Message`, `Details`, `ErrorCode`.
3. Проверить, не заблокирован ли `Charge` на терминале.
4. Не делать повторные массовые списания до выяснения.
5. Уведомить клиентов только после понимания причины.

## 13. QA checklist

### Product readiness

- [ ] `GET /api/billing/plans` возвращает `provider=tbank`.
- [ ] В `/plans` есть `solo`, `team`, `studio`.
- [ ] Цены соответствуют утвержденной коммерческой модели.
- [ ] UI показывает корректные лимиты и highlights.
- [ ] При `configured=false` сохраняется lead, подписка не создается.
- [ ] При `configured=true` создается платежная ссылка.
- [ ] Success redirect не активирует подписку без notification.
- [ ] Клиентские тексты не обещают хранение карты в Kolibri.

### Security

- [ ] `TBANK_PASSWORD` хранится только в env/secret store.
- [ ] `KOLIBRI_BILLING_ADMIN_TOKEN` задан и не пустой.
- [ ] `charge-due` без header возвращает 403.
- [ ] Notification с невалидным `Token` возвращает 400.
- [ ] Token generation исключает вложенные объекты и массивы.
- [ ] Token compare case-insensitive и constant-time.
- [ ] Production `NotificationURL` использует HTTPS.
- [ ] Внешние логи маскируют `Token`, `Pan`, `CardId`, `RebillId`, phone, email.

### Lifecycle

- [ ] `pending_payment` создается после успешного `Init`.
- [ ] `active` ставится только по valid notification с `Success=true`.
- [ ] `current_period_end` и `next_charge_at` ставятся на 30 дней.
- [ ] `past_due` ставится по `REJECTED`.
- [ ] `canceled` ставится по cancel/expired/refund statuses.
- [ ] Duplicate notification не ломает подписку.
- [ ] `billing_events` содержит audit trail для init, notification и charge.

### Charge-due

- [ ] В выборку попадают только due active subscriptions с `rebill_id`.
- [ ] `limit` ограничен диапазоном 1-100.
- [ ] `Init` failure пишет `tbank_rebill_init_failed`.
- [ ] `Charge` пишет `tbank_charge`.
- [ ] Первый production запуск идет с `limit=1`.
- [ ] Расписание можно быстро отключить при incident.

### T-Банк readiness

- [ ] Тестовый терминал создан.
- [ ] Recurrent payments включены.
- [ ] Метод `Charge` разрешен.
- [ ] `Init` с `Recurrent=Y` проходит без ошибки по `OperationInitiatorType`.
- [ ] `NotificationURL` задан в запросе и/или личном кабинете.
- [ ] Backend отвечает `OK` на успешные уведомления.
- [ ] Проверен отказ платежа.
- [ ] Проверен повтор notification.
- [ ] Онлайн-касса/фискализация согласованы отдельно.

## 14. Acceptance criteria для billing_tbank_operator

Работа считается принятой, когда:

- оператор может объяснить разницу между `payment` и `lead` mode;
- есть подтвержденный список тарифов и цен;
- есть подтвержденный public callback URL;
- notification token проверяется до любых изменений доступа;
- charge-due защищен admin token и запускается контролируемо;
- QA checklist выше пройден без blocker-ов;
- клиентские сообщения согласованы с продуктом и не обещают больше, чем делает backend;
- все incidents имеют понятный первый шаг диагностики.
