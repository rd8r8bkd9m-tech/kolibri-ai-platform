# Kolibri V3 → V5 (React) Полный рефакторинг

## Важная оговорка
«React v5» не существует как версия. Корректно: React 19 + Next.js 16.2 (у вас уже стоит).

## Цель (V5)
Сделать модульную, масштабируемую React-архитектуру без изменения доменной логики:
- predictible data flow,
- разрез по слоям: app → shell/feature → ui → primitives,
- единые токены классов и shared wrappers,
- строгая зависимость: `lib/ui` и `components/ui` не зависят от `components/assistant-ui`/`kolibri-shell`.

## Базовая структура (целевая)
- `components/ui/*` — атомарные primitives (Button, Input, Dialog, Dropdown, wrappers)
- `components/shared/*` — cross-surface composition primitives (`PageShell`, `SectionCard`, `List`, `EmptyState`, `StatePill`)
- `components/assistant-ui/*` — продуктовые assistant-модули
- `components/kolibri-shell/*` — shell + навигация + layout
- `components/kolibri-workspace/*` — workspace/domain view
- `lib/*` — бизнес-контракты и clients
- `app/*` — рендеринг маршрутов

## Этапы миграции V5
1. Архитектурная разметка и архитектурные границы
   - Добавить ADR: почему Next.js + React 19.
   - Добавить `component-contracts.md` с правилами импортов.
2. Token + shared wrappers
   - Единственный файл токенов классов (`components/ui/class-names.ts`) + экспорт
   - Базовые wrappers: `PanelContainer`, `ActionIconButton`, `ListItemRow`.
3. Полная декомпозиция монолитов
   - `assistant-ui/thread.tsx` → `thread-state`, `thread-shell`, `thread-list`, `thread-empty`, `thread-item`, `thread-actions`
   - `assistant-ui/product-widgets.tsx` → `widgets/shell`, `widgets/weather`, `widgets/estimate`, `widgets/file`, `widgets/project`
   - `kolibri-shell/workspace-shell.tsx` → `shell/layout`, `shell/topbar`, `shell/sidebar`, `shell/content-router`, `shell/state`.
4. Устранение дублирования
   - Один класс для кнопок/контейнеров в токенах,
   - замена inline-классов через `cn(uiClassTokens.*)`.
5. Жесткий boundary-check
   - Ввести скрипты проверки (`check-architecture-boundaries`) в CI.

## План выполнения (конкретно сейчас)
- Шаг 0: фиксация API-соглашений и визуальных контрактов (чтобы поведение не менялось).
- Шаг 1: чистка компонента `thread` как эталон.
- Шаг 2: перенос shared wrappers и token-first рефактор ко всем sidebar/thread/group-элементам.
- Шаг 3: аналогично `product-widgets`.
- Шаг 4: вынос layout-компонентов shell-а.
- Шаг 5: финальный архитектурный аудит и CI-гейт.

## Критерий готовности V5
- нет `className` клонов более 2 мест для одного и того же паттерна,
- модульные файлы >300 строк уменьшаются,
- `yarn test`/`npm run verify` проходят,
- структура `docs/PROJECT_MAP.md` и ADR отражают текущую архитектуру.
