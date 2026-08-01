# ADR 0002: T-Банк billing authority в V3 backend

- Status: accepted
- Date: 2026-08-01
- Owners: Kolibri V3 backend

## Context

V3 уже хранит tenant policy и deny-by-default product entitlement, но до этого
решения не имел канонической сущности заказа, платежа или периода доступа.
Клиентский return URL и статус в интерфейсе не могут быть финансовой authority.
Повторные и приходящие не по порядку банковские уведомления также нельзя
напрямую проецировать в доступ к продукту.

## Decision

Создать server-owned billing domain под `backend/app/billing/` и append-only
SQLite migration. Generic entitlement catalog отделяет plan→entitlement mapping
от текущего construction vertical: `construction.estimates.use` — approved
catalog row, но не schema CHECK. Intent фиксирует immutable snapshot тарифа,
tenant/user, integer minor amount, environment terminal, idempotency key и
уникальный `OrderId`. Карточные данные собирает только hosted form Т-Банка.

Единственный переход, активирующий фиксированный период и entitlement, — проверенное
уведомление `CONFIRMED`. Проверка подписи, binding и state transition выполняется
в одной backend границе; финансовые callback replay и out-of-order события
идемпотентны. Production и инициирование возвратов остаются отдельными
операторскими gates.

T‑Касса в MVP используется только для web/PWA/direct B2B как one-time
`PayType=O` с ручным продлением. `Recurrent`, `CustomerKey` и `RebillId` не
используются. Native iOS/Android digital SaaS потребует отдельных проверенных
StoreKit/Google Play adapters, которые в phase 2 проецируют события в общую
provider-neutral entitlement authority. Клиент не выдает доступ сам себе.
Immutable `return_surface` входит в idempotency hash и выбирает только один из
заданных внутренних landing paths; ни callback, ни request host не формируют
произвольный redirect.

## Consequences

Web/PWA получают T‑Касса BFF contract и не содержат платежной authority;
native клиенты остаются provider-neutral до StoreKit/Google Play phase 2.
Platform owner имеет redacted read model. Для реального запуска необходимо
отдельно утвердить terminal, кассу/54-ФЗ, публичную оферту/условия/возврат и
каталог тарифов; миграция не подставляет фиктивную цену. Неоднозначный `Init`
timeout требует reconciliation, а не автоматического сетевого retry.

## Verification

- миграция проверяет strict constraints, immutable scope и version fences;
- официальный `Init` token vector проверяется без сети;
- mock integration доказывает tenant/user binding, CSRF, idempotency, hosted
  URL, подпись webhook, replay/out-of-order, expiration и refund projection;
- Expo Web export доказывает PWA surface, а platform-specific native stub не
  экспортирует T‑Кассу в iOS/Android account;
- `npm run verify` включает backend и structure checks.

## Rollback

Отключить `KOLIBRI_V3_TBANK_ENABLED`, убрать billing router из composition и не
создавать новые intents. Миграцию 046 не переписывать и финансовую историю не
удалять. Существующие entitlement grants сохраняют server-owned state; их
изменение выполняется отдельной проверенной операторской процедурой.
