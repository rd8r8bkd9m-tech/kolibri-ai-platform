# ADR 0003: Authority-first estimate catalog and privacy-gated market aggregates

- Status: proposed
- Date: 2026-08-02
- Owners: V3 backend estimates, pricing and product surfaces

## Context

Короткий brief должен разворачиваться в редактируемую предварительную смету,
но AI-строки и цены нельзя считать утверждёнными справочными или рыночными
данными. Существующая смета уже владеет версиями и экспортом, а
`price_observations` — личной историей цен. Нужны reviewable кандидаты,
версионируемые technology cards и отдельная read model агрегатов, не
пересекающая tenant boundary и не раскрывающая исходные документы.

## Decision

Владелец канонических данных остаётся за V3 backend:

- `EstimateVersion` хранит snapshot строки, ссылки на `CatalogEntry`/версию
  карты и качество строки; UI и AI не создают canonical version напрямую.
- `CatalogCandidate` — единственная первая остановка для AI/user/import.
  Только явный owner review создаёт approved tenant/project entry; system
  curated seed не пополняется автоматически.
- `technology_card_definitions` и `technology_card_versions` хранят
  applicability, inputs, lines, resources, assumptions и exceptions. Старая
  версия сметы сохраняет ссылку на использованную версию и не меняется при
  обновлении карты.
- `price_observations` расширяется append-only миграцией. AI preliminary и
  user edit не aggregate-eligible; подтверждаемый источник требует evidence
  hash, действующего срока и отдельного consent.
- `market_price_aggregates` — privacy-gated read model. По умолчанию минимум
  пять независимых contributor pseudonyms, дедупликация по tenant/document/row,
  один contributor учитывается один раз, выбросы обрабатываются Tukey IQR
  1.5, наружу выдаются только P25/median/P75, cohort и policy version.
- Отзыв consent не удаляет историю, но исключает observation из будущего
  пересчёта. Нормативные и юридические решения не считаются одобренными этим
  ADR.

Роутеры остаются тонкими: SQL и правила находятся в
`backend/app/estimate_catalog.py`, BFF только ограничивает параметры и
проксирует запрос к V3 backend. UI использует существующий `EstimateEditor` и
создаёт candidate через idempotent mutation.

## Consequences

Положительные последствия: происхождение каждой строки и цены видно, старые
документы воспроизводимы, межтенантные утечки и самозагрязнение AI блокируются,
а небольшой cohort не превращается в публичный «индекс». Цена — это диапазон
для выбора пользователя, а не обязательная или единая ставка.

Цена решения: миграция перестраивает legacy observation table с сохранением
строк, а владельцу нужно вручную review-ить кандидатов. Для production
агрегации потребуются подтверждённые legal/retention правила и операционный
контроль источников.

## Verification

- migration 049 поднимается с чистой БД и проходит `foreign_key_check`;
- backend tests покрывают alias/unit search, candidate lifecycle, tenant
  isolation, consent, AI exclusion, cohort minimum, deduplication, outlier и
  revoke;
- BFF не содержит SQL и ограничивает project/id/query parameters;
- aggregate response не содержит supplier/document/evidence fields;
- `npm run typecheck` и backend targeted pytest проходят.

## Rollback

Не удалять миграцию и не откатывать реальные observations физически. Для
отката feature flag/маршрут можно закрыть чтение новых endpoints, оставив
`EstimateVersion` и append-only audit доступными. Пересчёт агрегатов можно
остановить, а уже опубликованные read-model rows пометить `published = 0`
отдельной контролируемой операцией.
