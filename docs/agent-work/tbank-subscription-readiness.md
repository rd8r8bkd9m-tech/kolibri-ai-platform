# Ревизия готовности Т-Банк подписок

Дата: 2026-06-29  
Агент: Ревизор готовности Т-Банк подписок  
Область: `backend/billing.py`, `backend/tests/test_billing.py`, `docs/agent-work/tbank-billing-ops.md`  
Ограничение ревизии: реальные API Т-Банка не вызывались, код не менялся.

## 1. Итоговый статус

Backend выглядит готовым к локальной проверке и sandbox-прогону подписок с тестовым терминалом. Для production запуск подписок еще не считается принятым: нужны sandbox evidence, боевые секреты, публичный HTTPS callback, решение по фискализации/онлайн-кассе, контролируемый запуск `charge-due` и подтверждение, что платные лимиты действительно завязаны на статус подписки в продукте.

Короткий gate:

| Контур | Статус | Что означает |
| --- | --- | --- |
| Local/mock | Ready | Токены, fallback, recurrent checkout, notification validation и recurring charge покрыты unit-тестами без внешних вызовов. |
| Sandbox | Conditional ready | Можно подключать тестовый терминал после env-разделения и публичного callback. Успех должен быть доказан реальным тестовым платежом. |
| Production | Blocked until acceptance | Нельзя включать автосписания без пройденного sandbox сценария, кассового решения, секретов prod и операционного runbook. |

## 2. Что уже реализовано

### 2.1 Тарифы и provider status

`PLANS` содержит три месячных тарифа:

| Plan | Цена по умолчанию | Env override | Лимит |
| --- | ---: | --- | --- |
| `solo` | 4 900 руб./мес | `KOLIBRI_PLAN_SOLO_KOPEKS` | до 30 смет в месяц |
| `team` | 14 900 руб./мес | `KOLIBRI_PLAN_TEAM_KOPEKS` | до 150 смет в месяц |
| `studio` | 39 900 руб./мес | `KOLIBRI_PLAN_STUDIO_KOPEKS` | безлимитный операционный контур |

`GET /api/billing/plans` возвращает `provider: "tbank"`, `configured` и список тарифов. `configured=true` только если заданы оба секрета `TBANK_TERMINAL_KEY` и `TBANK_PASSWORD`.

### 2.2 Checkout

`POST /api/billing/checkout` работает в двух режимах:

| Режим | Условие | Поведение |
| --- | --- | --- |
| `lead` | Нет `TBANK_TERMINAL_KEY` или `TBANK_PASSWORD` | Сохраняет заявку в `billing_leads`, не создает подписку, не вызывает Т-Банк. |
| `payment` | Оба секрета заданы | Вызывает `Init`, создает `pending_payment`, пишет `tbank_init`, возвращает `payment_url`. |

Для первичного recurrent checkout backend отправляет:

- `Recurrent = "Y"`;
- `PayType = "O"`;
- `Language = "ru"`;
- `CustomerKey` из normalized email;
- `DATA.OperationInitiatorType = "1"`;
- `NotificationURL`, `SuccessURL`, `FailURL` на базе `KOLIBRI_PUBLIC_URL` или request headers.

Важно: `SuccessURL` не активирует подписку. Доступ должен включаться только после валидного notification от Т-Банка.

### 2.3 Token и notification security

Реализована генерация и проверка токена:

- поле `Token` исключается;
- вложенные объекты, массивы и `null` не участвуют;
- boolean приводится к `true`/`false`;
- добавляется `Password`;
- значения сортируются по ключам и хэшируются SHA-256;
- сравнение выполняется case-insensitive через `hmac.compare_digest`.

`POST /api/billing/tbank/notification` принимает JSON или form payload. Обработка отклоняет payload без валидного токена, без `OrderId`, без `TerminalKey`, с чужим `TerminalKey`, без `PaymentId` для успешного платежа или с несовпадающей суммой.

### 2.4 Lifecycle подписки

Состояния, которые ставит текущий backend:

| Статус | Когда ставится | Эффект |
| --- | --- | --- |
| `pending_payment` | После успешного `Init` | Платежная ссылка создана, доступ не должен включаться. |
| `active` | `AUTHORIZED`, `CONFIRMED` или `COMPLETED` + `Success=true` + валидные проверки | Период ставится на 30 дней, `next_charge_at = current_period_end`, `rebill_id` сохраняется при наличии. |
| `past_due` | `REJECTED` | Списание не прошло. |
| `canceled` | `CANCELED`, `DEADLINE_EXPIRED`, `ATTEMPTS_EXPIRED`, `REVERSED`, `REFUNDED` | Подписка не продлевается. |

Повторный successful notification по тому же `OrderId` и `PaymentId` не должен повторно продлевать период. Notification по recurring charge ищет подписку через audit event нового `OrderId`.

### 2.5 Повторные списания

`POST /api/billing/tbank/charge-due` защищен header:

```text
X-Kolibri-Billing-Token: <KOLIBRI_BILLING_ADMIN_TOKEN>
```

Endpoint выбирает только подписки:

- `status = 'active'`;
- `rebill_id IS NOT NULL`;
- `next_charge_at IS NOT NULL`;
- `next_charge_at <= now`.

Для продления backend сначала вызывает `Init` с `DATA.OperationInitiatorType = "R"`, затем `Charge` с `PaymentId`, `RebillId`, `SendEmail=true`, `InfoEmail=<customer_email>`. Прямой ответ `Charge` пишет `tbank_charge`, но период продлевается только по последующему notification.

### 2.6 Тестовое покрытие

`backend/tests/test_billing.py` покрывает:

- генерацию token из sorted flat values;
- case-insensitive verification и tampering detection;
- lead fallback без вызова Т-Банка;
- сохранение lead payload и отсутствие подписки в fallback mode;
- `OperationInitiatorType = "1"` для первичного checkout;
- отклонение successful notification при mismatch amount;
- отклонение successful notification без `PaymentId`;
- идемпотентность duplicate notification;
- `OperationInitiatorType = "R"` для recurring `Init`;
- привязку recurring notification к подписке через audit event.

## 3. Sandbox env

Sandbox должен быть полностью отделен от production. Не использовать prod terminal, prod password, prod DB или prod admin token.

Обязательные переменные:

| Env | Значение для sandbox | Проверка |
| --- | --- | --- |
| `TBANK_TERMINAL_KEY` | Тестовый terminal key из кабинета Т-Банка | `/api/billing/plans.configured=true` вместе с password. |
| `TBANK_PASSWORD` | Тестовый password terminal-а | Notification token проходит локальную проверку. |
| `TBANK_API_URL` | Явно заданный URL для тестового контура или официальный endpoint, разрешенный для тестового terminal-а | Не полагаться молча на default; зафиксировать в deploy env. |
| `KOLIBRI_PUBLIC_URL` | Публичный HTTPS адрес sandbox приложения | `NotificationURL` должен быть доступен Т-Банку снаружи. |
| `KOLIBRI_BILLING_ADMIN_TOKEN` | Отдельный sandbox admin token | `charge-due` без header возвращает 403, с header работает. |
| `KOLIBRI_DB_PATH` | Отдельная sandbox SQLite DB | Sandbox платежи не попадают в prod DB. |

Опционально, но желательно:

- `KOLIBRI_PLAN_SOLO_KOPEKS`, `KOLIBRI_PLAN_TEAM_KOPEKS`, `KOLIBRI_PLAN_STUDIO_KOPEKS` с тестовыми или утвержденными sandbox суммами;
- отдельный домен вида `https://sandbox.<domain>`;
- отдельные backend logs и DB backup;
- ручной список тестовых сценариев: successful payment, rejected payment, duplicate notification, recurring charge.

Sandbox acceptance:

1. `/api/billing/plans` возвращает `provider=tbank`, `configured=true`, все три тарифа.
2. Checkout создает `mode=payment`, `pending_payment`, `tbank_init` и `payment_url`.
3. Тестовый первичный платеж возвращает клиента на `?payment=success`, но доступ не активируется до notification.
4. Backend получает notification, отвечает `OK`, переводит подписку в `active`, сохраняет `RebillId`.
5. Негативные notification с невалидным token, чужим `TerminalKey`, пустым `PaymentId` или другой `Amount` не активируют подписку.
6. Due-подписка с `rebill_id` проходит `charge-due` с `limit=1`; создается `tbank_charge`.
7. Notification после recurring charge продлевает период и обновляет `payment_id`.
8. В отдельном запуске без T-Банк env checkout уходит в `lead` mode и не вызывает provider.

## 4. Production env

Production env должен быть включен только после sandbox acceptance.

Обязательные переменные:

| Env | Значение для production | Gate |
| --- | --- | --- |
| `TBANK_TERMINAL_KEY` | Боевой terminal key | Хранится в secret store, не совпадает с sandbox. |
| `TBANK_PASSWORD` | Боевой terminal password | Rotation/runbook есть у владельца. |
| `TBANK_API_URL` | Боевой endpoint, явно подтвержденный перед запуском | Не менять без deploy note. |
| `KOLIBRI_PUBLIC_URL` | Боевой HTTPS URL приложения | Не localhost, не private IP, callback доступен извне. |
| `KOLIBRI_BILLING_ADMIN_TOKEN` | Боевой high-entropy token | Доступен только scheduler/operator-у. |
| `KOLIBRI_DB_PATH` | Persistent prod DB | Backup, permissions и restore path подтверждены. |

Production dependencies вне env:

- recurrent payments и `Charge` разрешены для боевого terminal-а;
- online cashbox/фискализация/чеки согласованы, потому что текущий код не отправляет `Receipt`;
- юридические тексты, оферта, политика возвратов и клиентские сообщения согласованы;
- scheduler для `charge-due` единственный, отключаемый, с первым запуском `limit=1`;
- мониторинг ошибок checkout, notification 400/502, массовых `charged=false`, отсутствующих `RebillId`;
- support procedure для `pending_payment`, `past_due`, refund/reversal и ручных лидов;
- доступ к `billing_events.payload_json` ограничен, внешние логи маскируют платежные поля.

## 5. Риски и блокеры

| Риск | Серьезность | Почему важно | Gate/mitigation |
| --- | --- | --- | --- |
| Нет production фискализации в коде | Blocker | `Init` и `Charge` не отправляют `Receipt`; нельзя обещать корректные чеки без отдельного кассового контура. | До prod согласовать онлайн-кассу или добавить fiscal receipt path. |
| Sandbox flow не прогнан с реальным тестовым terminal-ом | Blocker | Unit-тесты не доказывают, что Т-Банк примет `Recurrent`, `OperationInitiatorType`, `Charge` и пришлет `RebillId`. | Провести end-to-end sandbox payment и recurring charge. |
| `KOLIBRI_PUBLIC_URL` может быть не задан | High | Тогда URL строится из request headers и может стать внутренним/невалидным для callback. | В prod/sandbox задавать явный HTTPS public URL. |
| Recurring `Init` не задает `NotificationURL` | High | Если terminal-level notification не настроен, продление может не получить callback, а период не продлится. | В sandbox подтвердить recurring notification; при необходимости менять код отдельной задачей. |
| `charge-due` без распределенной блокировки | High | Два параллельных запуска могут выбрать одни и те же due rows и вызвать списания повторно. | Единственный scheduler, ручной запуск с `limit=1`, потом добавить lock/idempotency. |
| Прямой ответ `Charge` не продлевает период | Medium | При сбое notification клиент может быть списан, но период останется прежним. | Monitoring `tbank_charge` без последующего successful notification. |
| Raw provider payload хранится в `billing_events` | Medium | В payload могут оказаться чувствительные поля вроде `Token`, `RebillId`, card metadata, email/phone. | Ограничить доступ к DB, маскировать перед внешними логами. |
| Нет change-plan/cancel/customer portal flow | Medium | Апгрейд, отмена и повторная оплата требуют ручной поддержки. | Зафиксировать support policy до продаж. |
| Entitlement enforcement не подтвержден в изученных файлах | Medium | `active` статус бесполезен, если лимиты продукта не читают billing state. | Перед prod проверить код доступа/лимитов отдельно. |
| Цены управляются env | Low | Ошибка в копейках может изменить стоимость. | Перед prod сверить `/plans` с утвержденной коммерческой моделью. |

## 6. Acceptance для подключения подписок

### 6.1 Local acceptance

- [ ] `pytest backend/tests/test_billing.py` проходит без внешних API.
- [ ] `python3 -m py_compile backend/billing.py` проходит.
- [ ] В локальном fallback mode checkout сохраняет `billing_leads` и не создает `billing_subscriptions`.
- [ ] В mocked payment mode checkout отправляет `Recurrent=Y` и `DATA.OperationInitiatorType="1"`.
- [ ] Successful notification не активирует подписку без валидных `Token`, `OrderId`, `TerminalKey`, `PaymentId`, `Amount`.
- [ ] Duplicate successful notification не продлевает период второй раз.
- [ ] Recurring charge `Init` отправляет `DATA.OperationInitiatorType="R"` и notification мапится обратно к подписке.

### 6.2 Sandbox acceptance

- [ ] Sandbox secrets отделены от prod.
- [ ] Sandbox public URL доступен извне по HTTPS.
- [ ] `/plans.configured=true`.
- [ ] Тестовый initial recurrent payment успешно создает `PaymentURL`.
- [ ] Тестовый successful notification приходит в backend и получает `OK`.
- [ ] Подписка становится `active`, period = 30 дней, `next_charge_at` заполнен.
- [ ] `RebillId` сохранен после initial payment.
- [ ] `charge-due` с `limit=1` создает recurring `Init` и `Charge`.
- [ ] Notification после recurring charge продлевает период.
- [ ] Negative paths проверены: rejected payment, invalid token, amount mismatch, duplicate notification.
- [ ] В логах и внешних системах нет `TBANK_PASSWORD`, `KOLIBRI_BILLING_ADMIN_TOKEN`, raw `Token`.

### 6.3 Production acceptance

- [ ] Есть ссылка/артефакт sandbox run с датой, payload IDs и результатами.
- [ ] Prod secrets загружены через secret store и не совпадают с sandbox.
- [ ] `KOLIBRI_PUBLIC_URL` - боевой HTTPS domain.
- [ ] `TBANK_API_URL` подтвержден для боевого terminal-а.
- [ ] Онлайн-касса, чеки и юридические тексты приняты владельцем.
- [ ] Support знает ручные действия для lead, pending, past_due, canceled, refund.
- [ ] Entitlement/лимиты продукта читают billing state или есть временная ручная процедура включения доступа.
- [ ] Scheduler `charge-due` запускается одним механизмом; первый запуск `limit=1`.
- [ ] Есть alert на notification 400, checkout 502, отсутствие `RebillId`, массовые `charged=false`.
- [ ] Есть rollback: выключить `TBANK_TERMINAL_KEY`/`TBANK_PASSWORD` и вернуться в lead mode без потери заявок.

## 7. Go/no-go решение

Go для sandbox: можно выдавать задачу на подключение тестового terminal-а и выполнять end-to-end сценарии.

No-go для production прямо сейчас: кодовая база готова как каркас, но нет доказанного sandbox-прогона, фискализации, prod env evidence, operational locking/monitoring и подтвержденного entitlement path.

Следующий практический шаг: поднять sandbox env с отдельной DB и секретами, пройти acceptance из раздела 6.2, затем открыть отдельную production go-live задачу с артефактами sandbox run.
