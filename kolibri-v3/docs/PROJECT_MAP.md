# Карта проекта Kolibri V3

Это нормативная карта активного продукта. Она отвечает на вопрос «куда
помещать изменение» до написания кода. Runtime-ограничения задаёт
[`AGENTS.md`](../AGENTS.md), владельцев данных и контрактов —
[`SOURCE_OF_TRUTH.md`](SOURCE_OF_TRUTH.md).

## Контуры

| Путь | Ответственность | Не должен содержать |
| --- | --- | --- |
| `app/` | Next.js composition, страницы и тонкие BFF route handlers | доменные правила, прямой SQL |
| `components/ui/` | бездоменные UI-примитивы | API-клиенты, product state, импорты product surfaces |
| `components/assistant-ui/` | чат и отображение tool/runtime событий | backend-правила |
| `components/kolibri-shell/` | оболочка, навигация, admin surfaces | универсальные UI-примитивы |
| `components/kolibri-workspace/` | рабочая область и артефакты | transport/auth authority |
| `lib/<domain>/` | browser-контракты, state, клиенты и адаптеры домена | Next route handlers |
| `lib/server/` | server-only доступ Next к V3 backend | React-компоненты |
| `backend/app/` | FastAPI composition и серверные домены | migrations, тестовые фикстуры |
| `backend/app/chat/` | изолированный chat application layer | UI и Next.js contracts |
| `backend/migrations/` | последовательная эволюция схемы | runtime feature logic |
| `backend/tests/` | backend unit/contract/integration tests | production modules |
| `packages/` | Rust-ядра с собственной границей FFI/CLI | web UI |
| `apps/kolibri-mobile/` | нативный Expo-клиент | копии backend-логики |
| `deploy/portable/` | единственный production release lane | dev-runtime |
| `deploy/workers/` | шаблоны и launcher фоновых workers | второй release lane |
| `scripts/` | воспроизводимые dev/verify операции | бизнес-правила |
| `server/` | генерация и проверка общих контрактов | HTTP product backend |
| `generated/` | только сгенерированные артефакты | вручную поддерживаемый код |
| `tests/` | web/architecture contract tests | backend unit tests |
| `docs/` | нормативная документация и ADR | секреты и runtime state |
| `release/` | release evidence | исходный код продукта |

## Направление зависимостей

```text
app (composition/routes)
  ├─> components (product presentation)
  │     ├─> components/ui (generic presentation)
  │     └─> lib/<domain> (contracts/state/clients)
  └─> lib/server (server-only backend access)

backend/app/main (composition)
  └─> backend/app/<domain> (application/domain behavior)
          └─> database/provider adapters

web/mobile/backend
  └─> declared contracts or generated artifacts
          └─> Rust kernels where deterministic computation is required
```

Зависимость идёт к более стабильному слою. Generic UI не знает о workspace,
admin или chat. Доменные правила не размещаются в route handler ради удобства.
Мобильный и web-клиенты могут иметь разное представление, но не разные
серверные правила.

## Как размещать новую возможность

1. Назвать домен и определить владельца данных по
   [`SOURCE_OF_TRUTH.md`](SOURCE_OF_TRUTH.md).
2. Добавить серверное поведение в существующий доменный модуль. Новый пакет
   создавать только когда у него есть отдельный публичный контракт.
3. Разместить browser contract/client в `lib/<domain>/`.
4. Собрать UI в подходящей product surface; выносить в `components/ui/` только
   действительно бездоменный примитив.
5. Оставить `app/` и HTTP routers слоем композиции и преобразования транспорта.
6. Добавить ближайший тест и выполнить `npm run verify`.

## Когда нужен ADR

ADR обязателен при новом top-level контуре, новой базе/очереди, переносе
владения данными, новом межпроцессном протоколе, обращении направления
зависимостей или изменении production lane. Шаблон находится в
[`docs/adr/README.md`](adr/README.md).
