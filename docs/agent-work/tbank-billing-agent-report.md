# T-Банк billing implementation gap report

Дата: 2026-06-29  
Роль: инженер платежей Т-Банк  
Область исполнения: `backend/billing.py`, `backend/tests/test_billing.py`,
`frontend/src/App.jsx`, `frontend/src/components/control/BillingPanel.jsx`,
`frontend/src/plugins/controlPlugins.jsx`, `docs/API-RU.md`, `docs/api.md`.  
Ограничения: секреты не читались, не печатались и не менялись; реальные
платежи, sandbox/prod API-вызовы Т-Банка и charge operations не выполнялись.

## 1. Executive summary

T-Банк billing реализация в репозитории присутствует. Это backend-каркас
подписок с fallback lead mode, recurrent `Init`, signed notification handler и
admin `charge-due` для повторных списаний. Текущий статус:

| Контур | Решение | Причина |
| --- | --- | --- |
| Local/mock | `GO` | Есть backend tests без сети; provider мокается. |
| Sandbox | `GO with conditions` | Можно проверять только с отдельными sandbox secrets, отдельной DB и публичным HTTPS callback. |
| Production | `NO-GO` | Нет real sandbox evidence, фискализации/чеков, lock/idempotency для `charge-due`, мониторинга и подтвержденного entitlement enforcement. |

Главный вывод: код уже не является заглушкой, но это еще не production-ready
платежный контур. Реализация безопасно деградирует в lead mode без T-Банк
credentials и не активирует подписку без подписанного notification.

## 2. Где текущая реализация

| Компонент | Файл | Фактическое состояние |
| --- | --- | --- |
| Backend router | `backend/billing.py` | `APIRouter(prefix="/api/billing")`; подключен в `backend/main.py`. |
| Тарифы | `backend/billing.py` | `solo`, `team`, `studio`; суммы в копейках, env overrides. |
| Provider status | `backend/billing.py` | `configured=true` только при наличии `TBANK_TERMINAL_KEY` и `TBANK_PASSWORD`. |
| Checkout | `backend/billing.py` | Без credentials пишет `billing_leads`; с credentials вызывает `Init`. |
| T-Банк token | `backend/billing.py` | SHA-256 по sorted scalar values + `Password`; `Token` исключается. |
| Notification | `backend/billing.py` | Принимает JSON/form, проверяет token, `TerminalKey`, `OrderId`, `PaymentId`, `Amount`. |
| Recurring charge | `backend/billing.py` | `/api/billing/tbank/charge-due` защищен `X-Kolibri-Billing-Token`; вызывает `Init` и `Charge`. |
| Tests | `backend/tests/test_billing.py` | Unit/contract tests без реальных API; после этой проверки добавлен отдельный safe signing test. |
| Frontend | `frontend/src/App.jsx`, `frontend/src/components/control/BillingPanel.jsx`, `frontend/src/plugins/controlPlugins.jsx` | Панель подписок получает планы, отправляет checkout и редиректит на `payment_url`. |
| API docs | `docs/API-RU.md`, `docs/api.md` | Публичный контракт billing endpoints описан. |

## 3. Сверка с официальным контрактом Т-Банк

Сверка выполнена по официальным страницам T-Банк Dev Portal:

- `https://developer.tbank.ru/eacq/api/init`
- `https://developer.tbank.ru/eacq/api/charge`
- `https://developer.tbank.ru/eacq/intro/developer/token`
- `https://developer.tbank.ru/eacq/intro/developer/notification`

Соответствия в коде:

| Контрактный пункт | В коде | Статус |
| --- | --- | --- |
| `Init` для платежной ссылки | `init_tbank_subscription()` вызывает `tbank_post("Init", payload)`. | Present |
| `TerminalKey`, `Amount`, `OrderId`, `Description` | Формируются в checkout payload. | Present |
| Recurrent initial payment | Checkout отправляет `Recurrent="Y"` и `CustomerKey`. | Present |
| `DATA.OperationInitiatorType` | Initial checkout отправляет `"1"`, recurring init отправляет `"R"`. | Present, sandbox verification required |
| `NotificationURL` для primary checkout | Формируется из `KOLIBRI_PUBLIC_URL`/request base. | Present |
| `SuccessURL`/`FailURL` | Есть, но не активируют подписку. | Present |
| `Charge` для recurring | `charge_subscription()` отправляет `PaymentId`, `RebillId`, `SendEmail`, `InfoEmail`. | Present |
| Token generation | Scalar fields + `Password`, sorted, SHA-256. | Present |
| Notification response | После успешной обработки возвращает plain text `OK`. | Present |

## 4. Реализованные safety guarantees

- Fallback без credentials не вызывает Т-Банк и не создает подписку.
- `SuccessURL` не считается подтверждением оплаты.
- Successful notification активирует подписку только при валидном token,
  известном `OrderId`, корректном `TerminalKey`, непустом `PaymentId` и
  совпадающей `Amount`.
- Duplicate successful notification по тому же `OrderId`/`PaymentId` не
  продлевает период второй раз.
- `charge-due` требует отдельный admin header и не работает без T-Банк
  credentials.
- Unit tests мокают provider calls и не выполняют реальные платежные операции.

## 5. Implementation gaps

| ID | Gap | Severity | Evidence | Нужно закрыть |
| --- | --- | --- | --- | --- |
| G1 | Нет real sandbox evidence | Blocker | Проверка нашла только mock/unit coverage; реальные `Init`, browser payment, notification и `Charge` не запускались. | Провести isolated sandbox run с тестовым terminal-ом, отдельной DB и публичным HTTPS callback. |
| G2 | Нет фискализации/чеков | Blocker | `Init` и `Charge` payload не содержат `Receipt`; отдельный кассовый путь не найден. | Принять кассовое решение: T-Касса receipt payload, внешний ОФД/касса или ручной non-prod запрет продаж. |
| G3 | `charge-due` без lock/idempotency | High | Endpoint выбирает due rows и сразу вызывает provider; нет lease/lock table, idempotency key или in-progress state. | Добавить transactional claim/lock до provider call или обеспечить единственный scheduler до релиза. |
| G4 | Recurring `Init` без `NotificationURL` | High | Initial checkout задает callback URL, recurring init нет. Если terminal-level notification не настроен, период не продлится после списания. | Проверить в sandbox; если callback не приходит, добавить `NotificationURL` в recurring init. |
| G5 | Raw provider payload хранится в DB | Medium | `insert_event()` сохраняет полный `payload_json`, включая provider `Token`, возможный `RebillId` и card/contact metadata. | Ограничить DB access, добавить sanitizer для внешних логов/экспортов, рассмотреть redaction before store. |
| G6 | Entitlement enforcement не подтвержден | Medium | В рамках этой области найдены billing status и UI, но не найден проверенный путь, где продуктовые лимиты читают `billing_subscriptions.status`. | Отдельно проверить/добавить enforcement лимитов по active subscription. |
| G7 | Нет customer self-service flows | Medium | Нет cancel, change-plan, retry payment, refund/reversal support endpoints. | До продаж зафиксировать manual support policy или добавить минимальные flows. |
| G8 | Public URL может быть построен из request headers | Medium | `public_base_url()` fallback использует `x-forwarded-*` или `request.base_url`; неверная proxy config даст плохой callback. | В sandbox/prod задавать явный `KOLIBRI_PUBLIC_URL` и проверять reachable HTTPS. |
| G9 | Суммы управляются env без acceptance guard | Low | `KOLIBRI_PLAN_*_KOPEKS` могут изменить цену на старте процесса. | Добавить release checklist со сверкой `/api/billing/plans` против коммерческой модели. |

## 6. Тестовое покрытие до и после этой проверки

Уже было покрыто:

- token generation по sorted flat values;
- token verification case-insensitive и tampering detection;
- fallback lead mode без provider call;
- recurrent checkout с `OperationInitiatorType="1"`;
- блокировка activation при amount mismatch;
- блокировка activation без `PaymentId`;
- duplicate successful notification idempotency;
- recurring init с `OperationInitiatorType="R"` и mapping recurring notification
  к подписке через audit event.

Добавлено в `backend/tests/test_billing.py`:

- `test_tbank_post_signs_payload_without_sending_password_or_calling_real_api`.

Этот тест подменяет `httpx.AsyncClient`, проверяет URL, timeout, наличие
`Token`, отсутствие `Password` в outgoing JSON и отсутствие мутации входного
payload. Тест использует dummy password `contract-password` и не может уйти в
реальный T-Банк API.

## 7. Рекомендуемый следующий контрактный тест

Без секретов и сети можно добавить отдельной задачей:

- contract test для `charge_due_subscriptions()` через fake due subscription и
  mocked `charge_subscription()`, чтобы доказать, что endpoint требует admin
  token и выбирает только `active` + `rebill_id` + `next_charge_at <= now`;
- contract test для `public_base_url()` с `KOLIBRI_PUBLIC_URL`, чтобы prod не
  полагался на proxy headers.

## 8. Sandbox acceptance checklist

- [ ] Sandbox secrets отделены от prod: `TBANK_TERMINAL_KEY`, `TBANK_PASSWORD`,
  `KOLIBRI_BILLING_ADMIN_TOKEN`.
- [ ] `KOLIBRI_DB_PATH` указывает на отдельную sandbox SQLite DB.
- [ ] `KOLIBRI_PUBLIC_URL` является публичным HTTPS URL, доступным Т-Банку.
- [ ] `GET /api/billing/plans` возвращает `provider=tbank` и `configured=true`.
- [ ] Checkout возвращает `mode=payment`, `payment_url`, `subscription_id`,
  `order_id`, `payment_id`.
- [ ] Первичный signed notification переводит подписку в `active`, сохраняет
  `RebillId`, выставляет период и `next_charge_at`.
- [ ] Negative notifications: invalid token, чужой `TerminalKey`, пустой
  `PaymentId`, неверная `Amount` не активируют подписку.
- [ ] `charge-due` с `limit=1` создает recurring `Init` и `Charge`.
- [ ] Notification после recurring charge продлевает период и обновляет
  `payment_id`.
- [ ] Логи и артефакты не содержат `TBANK_PASSWORD`, admin token или raw
  provider `Token`.

## 9. Final gate

Разрешен только local/mock и следующий sandbox-прогон. Production запуск
подписок и автосписаний остается запрещенным до закрытия G1-G4 минимум и до
отдельного go-live артефакта с результатами sandbox run, фискализацией,
мониторингом и ownership для `charge-due`.

## 10. Локальная проверка

Выполнено без секретов, без реальных платежей и без сетевых вызовов Т-Банка:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-tbank-agent-py312-venv/bin/python -m py_compile backend/billing.py
PYTHONDONTWRITEBYTECODE=1 /tmp/kolibri-tbank-agent-py312-venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/test_billing.py
```

Результат: `py_compile` прошел, `backend/tests/test_billing.py` - `9 passed in
0.83s`.

Примечание по runtime: системный Xcode `python3` в этой среде оказался Python
3.9 и не подходит для текущего FastAPI/Pydantic импорта с аннотациями
`str | None`; поэтому финальная проверка выполнена на Homebrew Python 3.12 в
одноразовом venv `/tmp/kolibri-tbank-agent-py312-venv`.
