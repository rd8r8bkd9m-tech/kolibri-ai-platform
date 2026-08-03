# Справочник смет и рыночные наблюдения V3

## Граница данных

Backend владеет `CatalogEntry`, `CatalogCandidate`, technology cards,
`price_observations`, consent grants и `market_price_aggregates`. Web/mobile
клиенты получают только scoped API; browser не может выставить `verified` или
`aggregate_eligible` самостоятельно. Системные записи помечены
`system_curated`, tenant/project записи не видны другой области видимости.

AI-строка проходит путь:

```text
brief → preliminary EstimateVersion → CatalogCandidate → owner review
     → approved CatalogEntry → повторное использование
```

AI цена остаётся `preliminary` и никогда не становится рыночным наблюдением
без внешнего evidence. Детерминированный backend сохраняет и считает
количества/суммы; UI показывает диапазон как ориентир и не перезаписывает
введённую цену молча.

Универсальная генерация не пишет AI-строки прямо в готовую смету. Durable run,
project technology-card revision, research evidence и построчная lineage
определены в
[`ESTIMATE_GENERATION_ORCHESTRATION.md`](ESTIMATE_GENERATION_ORCHESTRATION.md)
и [ADR 0005](adr/0005-durable-universal-estimate-orchestration.md).

## Справочник и технологические карты

Официальный комплект документов выпускается только из точной версии EstimateVersion:
backend сначала фиксирует `EstimateDocumentSnapshot` с условиями и границами
расчёта, source hash, сторонами и источниками цен, затем renderer `official_ru_v1`
создаёт PDF/DOCX/XLSX/ZIP. Выпуск хранится в migration 050 и не меняется при
последующем редактировании проекта. Предварительные цены остаются видимыми как
`AI PRELIM.` и блокируют официальный выпуск до подтверждения.

Migration 049 создаёт небольшой проверяемый system-curated seed: подготовка
площадки, фундамент, арматура, стены, кровля, электрика, сантехника и явная
механизированная штукатурка. Seed описывает применимость и необходимые
уточнения, но не утверждает выдуманные нормативные коэффициенты. Каждая
EstimateVersion сохраняет `catalogEntryVersion` и `technologyCardVersion` в
snapshot строки.

`technology_card_definitions` / `technology_card_versions` — переиспользуемые
reviewed шаблоны. Они могут быть входом для run, но не заменяют project
`technology_cards`: последняя хранит точную сгенерированную карту объекта и
hash, с которыми связаны `operationId` строк опубликованной EstimateVersion.

`EstimateEditor` ищет по canonical/short name и aliases, нормализует `ё/е`,
`м²/m2`, `м³/m3`, поддерживает клавиатурную навигацию и добавляет approved
entry одним действием. Если совпадения нет, пользователь может оставить
строку локальной сметы или отправить `CatalogCandidate` на review.

## Источники цен

`price_observations` расширяет существующую таблицу без второй параллельной
истории. В observation фиксируются item key/catalog entry, specification,
единица, объёмной band, страна/регион/муниципалитет/timezone, VAT/delivery,
source type, evidence hash, valid-until, confidence, consent и contributor
pseudonym. Иерархия источников:

1. `completed_work` / `paid_invoice`;
2. `contract_price`;
3. `supplier_offer` с проверяемым evidence;
4. `customer_approved` и официальный reference с ограничениями;
5. `user_edit` и `ai_preliminary` — private/non-market.

Без evidence, действующего срока или согласия observation не участвует в
market aggregate. Тестовые строки получают `test_data = 1` и не агрегируются.

## Aggregate policy

Policy `market-aggregate/1.0.0` использует minimum cohort 5, свежесть 180
дней, дедупликацию повторных строк и contributor pseudonym, затем Tukey IQR
1.5. При недостаточном cohort API возвращает `published=false`; при успехе
возвращаются P25/median/P75, свежесть, confidence, состав источников,
количество observations/contributors и версию метода. Supplier name,
исходный документ, email и evidence hash в aggregate response отсутствуют.

## Согласие и открытые вопросы юристу

Consent хранит scope, policy version, granted/revoked timestamps, source и
append-only events. Отзыв исключает будущие пересчёты, не разрушая audit trail.
До production-публикации market statistics требуется отдельное заключение по
следующим вопросам:

- какие поля загрузок и счетов являются персональными данными и каков lawful
  basis/notice для их обработки;
- могут ли цены, условия поставки, договоры и evidence составлять
  коммерческую тайну клиента или поставщика;
- какие права и лицензии нужны на загружаемые документы и выдержки из них;
- не создаёт ли агрегирование цен антимонопольные риски или недопустимый
  coordination signal;
- достаточны ли cohort threshold, pseudonymization и suppression для
  допустимой рыночной статистики;
- сроки хранения, архивирования и уничтожения observation/evidence;
- последствия отзыва consent для уже рассчитанных aggregates и экспортов;
- требуется ли отдельное согласие/договор для cross-tenant statistics и
  supplier imports.

Документ не является юридическим заключением и не объявляет политику
production-approved.

## QA tenant и архив

Тестовые кандидаты/сметы/observations должны создаваться только в отдельном
QA tenant с `test_data = 1`. Архивирование должно быть tenant-scoped,
сначала dry-run, затем отдельная auditable archive операция; физическое
удаление пользовательской или production истории этим контуром не выполняется.
