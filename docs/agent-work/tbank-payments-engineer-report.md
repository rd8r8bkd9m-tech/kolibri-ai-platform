# Отчет инженера платежей Т-Банк

Дата: 2026-06-29  
Роль: инженер платежей Т-Банк  
Область проверки: `backend/billing.py`, `backend/tests/test_billing.py`  
Ограничения: секреты не читались и не менялись, реальные платежи и вызовы API Т-Банка не выполнялись.

## Итог

Интеграция backend сейчас выглядит готовой для локального mock-тестирования и следующего sandbox-прогона с тестовым терминалом Т-Банка. Для production-подписок статус остается `NO-GO`: нет evidence реального sandbox checkout/notification/Charge, нет подтвержденного кассового/фискального контура, нет защиты от параллельного запуска `charge-due` и не подтверждено, что продуктовые лимиты читают `billing_subscriptions.status`.

Короткий gate:

| Контур | Статус | Комментарий |
| --- | --- | --- |
| Local/mock | `GO` | Unit-тесты покрывают подпись, fallback, recurrent init, notification safety и recurring mapping без внешних платежей. |
| Sandbox | `GO with conditions` | Можно подключать тестовый terminal только с отдельной DB, публичным HTTPS `KOLIBRI_PUBLIC_URL` и отдельными sandbox secrets. |
| Production | `NO-GO` | Нужны sandbox evidence, фискализация/чеки, мониторинг, scheduler discipline и operational acceptance. |

## Что проверено в `backend/billing.py`

- Тарифы `solo`, `team`, `studio` заданы в копейках и отдаются через `/api/billing/plans`; `configured=true` зависит только от наличия `TBANK_TERMINAL_KEY` и `TBANK_PASSWORD`.
- При отсутствии T-Банк credentials `checkout` сохраняет lead в `billing_leads`, не создает `billing_subscriptions` и не вызывает provider.
- При наличии credentials первичный checkout вызывает `Init` с `Recurrent="Y"` и `DATA.OperationInitiatorType="1"`, создает `pending_payment` и сохраняет audit event `tbank_init`.
- Token logic исключает `Token`, вложенные структуры и `null`, добавляет `Password`, сортирует ключи и проверяет SHA-256 через `hmac.compare_digest`.
- Successful notification активирует подписку только после валидного token, известного `OrderId`, совпадающего `TerminalKey`, непустого `PaymentId` и совпадающей `Amount`.
- Дубликат successful notification по тому же `OrderId`/`PaymentId` не продлевает период повторно.
- Recurring списание через `/api/billing/tbank/charge-due` защищено `X-Kolibri-Billing-Token`, выбирает только due active subscriptions с `rebill_id`, делает `Init` с `DATA.OperationInitiatorType="R"`, затем `Charge`.
- Recurring notification мапится обратно к подписке через `billing_events` по новому `OrderId`, поэтому продление периода зависит от callback, а не от прямого ответа `Charge`.

## Что проверено в `backend/tests/test_billing.py`

Покрытие релевантно подпискам Т-Банк:

- генерация token из sorted flat values;
- case-insensitive token verification и detection tampering;
- fallback lead mode без вызова Т-Банка и без создания подписки;
- primary recurrent checkout с `OperationInitiatorType="1"`;
- блокировка activation при amount mismatch;
- блокировка activation без `PaymentId`;
- идемпотентность duplicate successful notification;
- recurring `Init` с `OperationInitiatorType="R"` и обработка recurring notification.

Тесты не выполняют сетевых вызовов к Т-Банку: provider замокан через `monkeypatch`.

## Production blockers

| Блокер | Почему важно | Что нужно сделать |
| --- | --- | --- |
| Нет реального sandbox evidence | Unit-тесты не доказывают, что конкретный terminal примет `Recurrent`, `OperationInitiatorType`, `Charge` и вернет `RebillId`. | Пройти initial payment, signed notification и recurring charge на тестовом терминале. |
| Нет фискализации/чеков в коде | `Init` и `Charge` не отправляют `Receipt`; для боевого запуска это юридический и операционный риск. | Подтвердить кассовый контур или добавить передачу receipt данных отдельной задачей. |
| `charge-due` без lock/idempotency на выборку due rows | Два scheduler-а или ручной двойной запуск могут инициировать повторные списания. | До production держать один scheduler и первый запуск `limit=1`; затем добавить lock/idempotency. |
| Recurring `Init` не задает `NotificationURL` | Если callback не настроен на уровне terminal-а, recurring charge может списать деньги без продления периода в продукте. | Проверить в sandbox; при необходимости добавить `NotificationURL` для recurring init. |
| Raw provider payload хранится в `billing_events` | Payload может содержать `Token`, `RebillId`, card metadata и контакты. | Ограничить доступ к DB и маскировать данные перед внешними логами/экспортами. |
| Entitlement path не подтвержден в этой проверке | Подписка `active` полезна только если продуктовые лимиты и доступ реально ее читают. | Отдельно проверить enforcement доступа и лимитов. |

## Sandbox checklist

- [ ] Отдельные sandbox `TBANK_TERMINAL_KEY`, `TBANK_PASSWORD`, `KOLIBRI_BILLING_ADMIN_TOKEN`.
- [ ] Отдельный `KOLIBRI_DB_PATH`, не prod DB.
- [ ] Явный публичный HTTPS `KOLIBRI_PUBLIC_URL`, доступный Т-Банку.
- [ ] `/api/billing/plans` возвращает `provider=tbank` и `configured=true`.
- [ ] Checkout возвращает `mode=payment`, `payment_url`, создает `pending_payment` и `tbank_init`.
- [ ] Signed notification переводит подписку в `active`, сохраняет `RebillId`, выставляет период на 30 дней.
- [ ] Invalid token, чужой `TerminalKey`, пустой `PaymentId`, неверная `Amount` не активируют подписку.
- [ ] `charge-due` с `limit=1` создает recurring `Init` и `Charge`.
- [ ] Notification после recurring charge продлевает период и обновляет `payment_id`.

## Проверки в рамках отчета

Выполнены локальные проверки без секретов и без реальных платежей:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile backend/billing.py
PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-tbank-audit-py312-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_billing.py
```

Результат: `py_compile` прошел, `backend/tests/test_billing.py` - `8 passed in 3.73s`. Системный `python3` не имел установленного `pytest`, поэтому тесты запускались из временного venv на Python 3.12 в `/tmp`.

## Решение

Разрешаю следующий шаг только для sandbox: подключить тестовый terminal Т-Банка и пройти checklist выше. Боевой запуск подписок запрещен до закрытия production blockers и появления артефакта sandbox-прогона.
