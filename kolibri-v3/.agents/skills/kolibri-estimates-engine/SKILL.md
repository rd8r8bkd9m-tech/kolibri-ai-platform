---
name: kolibri-estimates-engine
description: "Kolibri construction-estimates engine: deterministic calculation in backend/app/estimate_engine.py, durable generation orchestration (estimate_generation.py), intake normalization, catalog and market aggregates, arithmetic reconciliation, document packs and PDF/XLSX/DOCX/CSV/ZIP exports, and the mobile construction-estimates vertical. Use when generating, validating, pricing, reconciling, exporting, or fixing estimates, or when changing the mobile estimates surface."
license: MIT
---

# Kolibri Сметный движок

Работаем внутри `kolibri-v3/`. Сначала прочитать `kolibri-v3/AGENTS.md` и
`docs/SOURCE_OF_TRUTH.md` (строки про оценки/сметы, каталог и документы).

## Когда использовать

- Генерация, валидация, ценообразование или экспорт смет.
- Фикс расчётной логики, версий правил или реконсиляции AI-кандидатов.
- Изменение мобильной поверхности смет (construction-estimates vertical).

## Rules

1. **LLM никогда не считает деньги.** Все суммы, объёмы и проценты считает
   детерминированный движок `backend/app/estimate_engine.py` (Decimal,
   ROUND_HALF_UP; деньги — 2 знака, количества — 6 знаков после запятой).
   Правки арифметики — только там, не в промптах и не в UI.
2. **Один вход → один канонический JSON.** `canonical_json()` +
   `content_hash()` (sha256) — контракт идемпотентности. Одинаковые входы и
   версия правил всегда дают одинаковый хеш. Версии правил фиксированы
   константами: `ENGINE_VERSION = "kolibri-estimate-engine/1.0.0"`,
   `PLASTER_RULES_VERSION = "plastering/1.0.0"`, policy-версии в
   `estimate_intake.py` / `estimate_catalog.py` / `estimate_reconciliation.py`.
3. **История и evidence — append-only на backend.** Run journal, ProjectCase,
   technology-ревизии, source evidence, row lineage живут в SQLite через
   `estimate_generation.py`; существующая миграция не переписывается.
4. **Каталог ≠ исполнение.** Запись в каталоге или AI-кандидат не является
   ценой; источник цены — только approved evidence
   (`EVIDENCE_SOURCE_TYPES`: user_input, approved_catalog, official_reference,
   supplier_offer, market_aggregate, ai_candidate) с `LINE_CONFIDENCE`
   (missing/preliminary/source_backed/verified).
5. **Документы — из опубликованного снапшота.** Официальные КП/договор/акт/
   счёт рендерятся из immutable `estimate_document_issues.snapshot_json`
   (`estimate_document_pack.py`), а не из живого состояния UI.

## Контур модулей

| Модуль | Роль |
|---|---|
| `estimate_engine.py` | Детерминированный расчёт: `Quantity`/`Formula`, единицы и размерности, plastering-карта технологий, `calculate_plastering_estimate`, canonical JSON + хеш. Никакого HTTP/LLM/персистенции. |
| `estimate_intake.py` | Нормализация ввода пользователя (`normalize_plastering_intake`, `parse_plastering_intake`) — из текста в структурированный scope. |
| `estimate_attachment_context.py` | Парсинг вложений как входного контекста сметы (`PARSER_VERSION = "estimate-attachment-context/1.0.0"`). |
| `estimate_generation.py` | Durable-оркестрация: `create_generation_run`, `plan_generation_sections`, `claim/complete/fail_generation_task`, `register_generation_evidence`, `save/publish_technology_card_revision`, `persist_expanded_lines`, `transition_generation_run`. Стадии `RUN_STAGES`, роли `SECTION_ROLES`, статусы `RUN_STATUSES` (`queued→running→…→ready/failed/cancelled`). |
| `estimate_generation_router.py` | AG-UI прогресс durable-генерации: `AG_UI_PROTOCOL_VERSION="0.0.57"`, поток `GET /{project_id}/estimate/generation/{run_id}/events` (Last-Event-ID) — тонкий транспорт. |
| `estimate_catalog.py` | Каталог: `search_catalog`, `create/review_catalog_candidate`, `record_catalog_price_observation`, `refresh_market_price_aggregate`, consent на агрегаты. |
| `estimate_reconciliation.py` | Починка арифметики AI-кандидатов (`reconcile_ai_candidate_estimates`, `REPAIR_POLICY_VERSION`) — детерминированные исправления с аудитом. Тот же модуль — CLI-entrypoint (`main()`) для пакетной реконсиляции. |
| `estimate_document_pack.py` | Снапшот документов, `issue_document_pack`, `money_words` (сумма прописью), версия рендера `official_ru_v1`. |
| `estimate_exports.py` | `render_estimate_pdf` / `render_estimate_xlsx` / `render_estimate_docx` / `render_estimate_csv` / `render_estimate_zip` (шрифт `KolibriUnicode`), `build_or_load_estimate_export`. |
| `estimate_*_router.py` | Тонкие FastAPI-роутеры — только транспорт, без бизнес-правил. |
| Мобильная вертикаль `apps/kolibri-mobile/src/verticals/construction-estimates/` | `contracts.ts` (строгие парсеры), `client.ts` (`GET /v1/documents`, `GET /v1/projects/{id}/estimate`, `PATCH .../estimate/rows`), `registration.ts` + `access.ts` (тройной гейт capability/entitlement/rendererKey). |

## Workflow

1. Прочитать scope: тип работ, зоны, объёмы, единицы, регион/валюта, ограничения клиента.
2. Если данных мало — честный статус `needs_input` / `preliminary`, не выдумывать расценки.
3. Нормализовать вход через `estimate_intake`; построить ProjectCase и technology-карту.
4. Получить цены через `estimate_catalog` (approved/evidence) или явный evidence от поставщика с источником и датой. Не брать цену «из головы» и не из сниппета поиска.
5. Развернуть смету (`expand_technology_card`) → реконсиляция (`reconcile_expanded_estimate` / `reconcile_ai_candidate_estimates`) → `persist_expanded_lines`.
6. Опубликовать technology-ревизию (`publish_technology_card_revision`), затем при необходимости снапшот документов и экспорт.
7. Прогнать тесты движка и live-QA (см. Verification).

## Verification

- Юнит/контракт-тесты движка: `backend/tests/test_estimate_*.py`
  (`PYTHONPATH=backend backend/venv/bin/python -m pytest backend/tests/test_estimate_engine.py -q` — точный файл смотреть в `backend/tests/`).
- Live-QA смет: `npm run test:qa:estimate:live`.
- Мобильные контракты вертикали: `apps/kolibri-mobile/tests/native-vertical-contracts.test.mjs` (`node --test` из `apps/kolibri-mobile`).
- После изменения расчётной логики — обязательно новая миграция (append-only) или bump версии правил + тест на хеш; прогон `npm run verify` (backend gates).

## Related skills

- `kolibri-backend` — структура backend, миграции, pytest-конвенции
- `kolibri-vertical-registry` — как подключается мобильная вертикаль
- `estimate-generation` (legacy) — устаревший скилл, только для чтения
- `kolibri-billing` — entitlement-гейты вертикалей
