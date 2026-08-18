---
name: kolibri-billing
description: "Kolibri billing: backend billing service, renewals, T-Bank protocol, entitlements, and the mobile billing client. Use when billing state is wrong, subscriptions or renewals misbehave, or entitlement gates surface access incorrectly."
license: MIT
---

# Kolibri Billing

Работаем внутри `kolibri-v3/`. Сначала прочитать `kolibri-v3/AGENTS.md` и
`docs/SOURCE_OF_TRUTH.md` (строка про тарифы/payment intents/T-Банк).

## Когда использовать

- Состояние биллинга неправильное: подписка/продление/платёж не сходятся.
- Entitlement-гейты не открывают/открывают поверхности ошибочно.
- Меняется серверная логика тарифов, T-Банк-протокола или клиентский биллинг.

## Владельцы данных

- Сервер владеет планами, payment intents, подписками и проверенными T-Банк
  событиями — `backend/app/billing/` + append-only миграции.
- Клиент хранит только безопасный статус и intent; никаких карточных данных и
  production-секретов в клиенте.
- Владелец строки в SOURCE_OF_TRUTH меняется только через ADR.

## Контур

| Слой | Файлы |
|---|---|
| Backend | `backend/app/billing/` (service, renewals, tbank, admin_settings), миграции `059_tbank_recurring.sql`, `062/063/064_tbank_*` |
| Мобильный клиент | `apps/kolibri-mobile/src/billing/client.ts` (`GET /v1/billing/plans`, `/subscriptions`, payment-intents, auto-renew) |
| Мобильный UI | `components/settings/native-billing-settings.tsx` (native) и `web-billing-settings.web.tsx` (web, `web-billing-settings.tsx` — no-op) — два параллельных рендера, логика polling платежа дублируется |
| Entitlements | Серверные entitlement-флаги гейтят вертикали (`kolibri-vertical-registry`) |

## Правила

- Карточные данные и статусы — только server-owned; клиент — redacted read-модель.
- Повторяющиеся платежи и проверенные события T-Банк — только через billing-домен, не в UI.
- Известный долг: дублирование `readError`/`formatMoney`/статусных меток между
  native/web-поверхностями и `client.ts` — при правке синхронизировать все копии
  или выносить общий код, но не создавать второй источник истины.

## Workflow

1. Определить, где баг: клиентский рендер/статус или серверная транзакция.
2. Сервер: проверить billing-домен и миграции (append-only), T-Банк webhook-валидацию.
3. Клиент: сверить `client.ts` и UI-поверхность; статусы платёжного терминала — константы рядом с UI.
4. Entitlement: если поверхность не открывается — проверить серверные entitlement-флаги в сессии, не «лечить» на клиенте.

## Verification

- Backend: `backend/tests/test_billing*.py` (`PYTHONPATH=backend backend/venv/bin/python -m pytest ...`).
- Клиент: `apps/kolibri-mobile/tests/` (контрактные), `npm run mobile:typecheck`.
- Live: оплата/подписка на живом стеке (QA-биллинг, не прод).

## Related skills

- `kolibri-backend` — структура backend и миграции
- `kolibri-vertical-registry` — entitlement-гейты вертикалей
- `kolibri-estimates-engine` — сметные документы (смежные серверные домены)
