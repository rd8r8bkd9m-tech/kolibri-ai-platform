# Регресс-ревью мобильной полировки Kolibri V3 — раунд 2 (субагент 04)

Дата: 2026-08-18. Режим: READ-ONLY (файлы репозитория не менялись, кроме данного отчёта).

---

## Часть A — судьба compact-шаблона

### Факты (проверено в коде)

1. **`data-workspace-mode="compact"` нигде не выставляется.** В вебе единственное
   значение — `data-workspace-mode="desktop"` (`components/kolibri-shell/desktop-workspace/desktop-workspace-layout.tsx:43`).
   Греп по `components/`, `app/`, `lib/` даёт только CSS-упоминания
   (`app/globals.css:229,260,592`) и `data-workspace-mode="desktop"`. Селектор
   `[data-workspace-mode="compact"]` в рантайме не срабатывает никогда.

2. **`compact`-проп Thread/ThreadComposer никогда не `true`.**
   `components/assistant-ui/thread.tsx:28,56` — `compact = false` по умолчанию;
   оба места вызова (`desktop-workspace-view.tsx:150,172`, `codex-main.tsx:36`)
   не передают `compact`. Следовательно `data-mobile-layout` в
   `thread/thread-shell.tsx:26` всегда `"false"`, и весь CSS
   `.aui-thread-root[data-mobile-layout="true"]` (globals.css ≈660–945) мёртв.

3. **`MobileWorkspaceHeader` не импортируется нигде**, кроме самого файла
   (`components/kolibri-shell/mobile-workspace-header.tsx`). Это полностью
   мёртвый компонент. Его CSS (`[data-slot="kolibri-mobile-header"]`,
   `[data-slot="mobile-hamburger-icon"]`, globals.css ≈283–297) тоже мёртв.

4. **Спецификация явно свернула на Expo.** `docs/design/desktop-mobile-redesign-spec.md`
   (§1, §3.2, §4) фиксирует: mobile = Expo Router + React Native
   (`apps/kolibri-mobile`), `@assistant-ui/react-native`, нативные safe areas,
   SF Symbols/Material Icons. Web-compact-шаблон в целевой архитектуре отсутствует.
   Реальные телефоны уходят в Expo через `mobile-environment.tsx` (`?client=mobile`),
   а узкое окно десктопа обслуживает `useAdaptiveWorkspaceLayout`
   (overlay-навигация / fullscreen-auxiliary) + `lib/responsive/workspace.ts`.

5. **НЕ всё внутри `@media (max-width: 959px)` (globals.css 225–947) мёртвое.**
   Блоки, которые живут без `data-workspace-mode="compact"` и привязаны к
   реально присутствующим `data-slot`/атрибутам, реально срабатывают на узком
   десктопе: `aside[data-overlay="true"] …` (overlay-навигация),
   `[data-slot="settings-*"]`, `[data-slot="estimate-editor"]`,
   `[data-slot="estimate-mobile-list"]` (переключаются классами
   `min-[960px]:hidden` / `hidden min-[960px]:block` в `estimate-editor.tsx`),
   `.aui-button-icon` (globals.css:1882). Их удалять нельзя.

6. **Тест завязан на мёртвые артефакты.** `tests/design-contract.test.mjs`
   читает `mobile-workspace-header.tsx` (строка 92) и ассертит наличие CSS
   (`--background:#000000`, `@media (max-width:959px)`, `data-mobile-layout={compact ?`
   и т.п.) в тесте «the compact shell matches the mobile chat contract».
   Ни один тест НЕ ассертит, что `data-workspace-mode="compact"` реально
   выставляется или что `compact` передаётся `true`.

### Рекомендация: **(б) оставить как есть (легаси) — основной вариант, НЕ включать и НЕ удалять массово сейчас**

Обоснование:

- **Включение (а) противоречит спеку и несёт десктоп-риски.** Модель продукта
  переведена на Expo; web-compact — это две несвязанные половинки
  (`data-workspace-mode="compact"` токен-ресет и `data-mobile-layout` через
  `compact`-проп), между которыми нет связующей логики. Чтобы получить
  согласованный компактный UI, надо синхронно переключить и shell-атрибут, и
  `compact`-проп Thread, и заголовок (`MobileWorkspaceHeader`), иначе
  получится «половина» стиля (мобильный composer при десктопном заголовке или
  белый/чёрный рескин без мобильного composer).
- **Hydration mismatch.** Наивное `compact={window.innerWidth < 960}` в рендере
  даст рассинхрон сервера/клиента. Безопасный путь — только после
  «mounted»-состояния (как уже сделано в `useAdaptiveWorkspaceLayout`, где
  `viewportWidth === null` до клиента), т.е. потребуется дополнительная
  прокинуть ширину в Thread/ThreadComposer и в `data-workspace-mode` shell'а.
- **Недоделанность CSS.** Токен-ресет `[data-workspace-mode="compact"]`
  (globals.css 225–260) переопределяет `--brand` на `#0e7a6b`, `--background`
  на `#fff/#000` и т.д. — это старая палитра, конфликтующая с текущей
  mint/oklch-системой; включение мгновенно перекрасит всё узкое окно в старый
  бренд и гарантированно вызовет визуальную регрессию.
- **Трудозатраты на (а) неоправданны:** это фактически поддержка второго
  мобильного UI параллельно с Expo — дублирование, от которого продукт уже ушёл.
- **Удаление (в) сейчас рискованно и неточно по границам:** мёртвые и живые
  правила переплетены в одном `@media (max-width: 959px)` блоке (см. факт 5),
  а `tests/design-contract.test.mjs` читает удаляемый компонент — при удалении
  тест упадёт. В условиях, когда `git status` показывает десятки незакоммиченных
  правок по `apps/kolibri-mobile` и `app/globals.css`, массовая чистка добавит
  шум и риск случайной потери живых правил.

**Итог по A:** оставить легаси без изменений (вариант б). Чистку (в) отложить
до стабилизации ветки и делать точечно (см. «минимальный безопасный объём» ниже),
а не «снести 225–947».

### Если всё же решат удалять мёртвый код — точный минимальный объём (вариант в, факультативно)

Удалять только то, что гарантированно мёртво, и **не трогать** живые
`@media (max-width: 959px)`-правила:

- `app/globals.css`:
  - блок `[data-workspace-mode="compact"] { … }` (светлый) — строки ≈225–258;
  - `.dark [data-workspace-mode="compact"] { … }` — строки ≈260–283;
  - `[data-slot="kolibri-mobile-header"] …` + `[data-slot="mobile-hamburger-icon"]`
    (≈283–297) — только если удаляем компонент (см. ниже);
  - `[data-workspace-mode="compact"]:has([data-slot="estimate-editor"]) …`
    (≈592–596);
  - блок `.aui-thread-root[data-mobile-layout="true"] …` целиком (≈655–945),
    включая `.aui-mobile-starter-action` и вложенный `@media (max-width: 340px)`.
  - ⚠️ НЕ удалять: `aside[data-overlay="true"] …`, `[data-slot="settings-*"]`,
    `[data-slot="estimate-editor"]`, `[data-slot="estimate-mobile-list"]`,
    `.aui-button-icon` (1882) — они живые.
- `components/kolibri-shell/mobile-workspace-header.tsx` — удалить файл целиком
  (никем не импортируется).
- `components/assistant-ui/thread.tsx` — убрать `compact` из пропсов
  `Thread`/`ThreadComposer` (и из `ThreadCompactContext`-провайдеров); затем
  `thread/thread-context.tsx` (`ThreadCompactContext`), `thread/layouts/thread-screen.tsx`,
  `thread/parts/thread-layout.tsx`, `thread/thread-shell.tsx`
  (`data-mobile-layout`) — каскадная чистка. Это средний объём; делать отдельным PR.
- **Обязательно обновить** `tests/design-contract.test.mjs`: убрать
  `readSource(".../mobile-workspace-header.tsx")` и ассерты
  `data-mobile-layout={compact ?`, `--background:#000000`,
  `data-slot="mobile-hamburger-icon"` и т.п. — иначе тест упадёт на
  `ENOENT`/`assert.match`.

### Если бы включали (а) — чего это стоит (для полноты; НЕ рекомендуется)

Минимальная безопасная цепочка выглядела бы так (не реализовано):

1. `lib/responsive/workspace.ts` — ввести компактный флаг с гистерезисом
   (по образцу `DESKTOP_ENTER/EXIT_WIDTH`), например `COMPACT_ENTER=960`.
2. `desktop-workspace.tsx` / `desktop-workspace-view.tsx` — прокинуть
   `viewportWidth` из `useAdaptiveWorkspaceLayout` и, только после первого
   клиентского замера (`viewportWidth !== null`), выставлять
   `data-workspace-mode="compact"` на shell и `compact={true}` в
   `<Thread>`/`<ThreadComposer>` — синхронно, иначе половинчатый стиль.
3. `desktop-workspace-layout.tsx` — принимать `workspaceMode` проп вместо
   жёсткого `data-workspace-mode="desktop"`.
4. Подключить `MobileWorkspaceHeader` вместо/поверх `WorkspaceHeader` на узком
   окне (сейчас он не подключён).
5. Переписать токен-ресет 225–260 под текущую mint/oklch-систему (сейчас он
   перекрашивает в устаревший `#0e7a6b`).
6. Добавить hydration-безопасные тесты + скриншот-прогон 390×844 и 1280×720.

Вывод: стоимость (а) ≈ стоимость поддержки второго мобильного UI; риск
десктоп-регрессии и hydration-mismatch высокий; продуктовая ценность нулевая,
потому что мобильный сценарий уже закрыт Expo.

---

## Часть B — проверка десктоп-регрессий раунда 1 (viewport ≥960px)

Все правки ниже — CSS-брейкпоинты, JS не влияет на ≥960px. Hydration-риска нет,
кроме одного места, где `matchMedia` вызывается только в обработчике клика
(см. п.6).

| Правка | Где (file:line) | Риск на десктопе ≥960px | Вердикт |
| --- | --- | --- | --- |
| `items-start … sm:items-center` у auth | `components/kolibri-shell/auth-panel.tsx` `DesktopAuthScreen` (контейнер `flex h-dvh items-start … sm:items-center sm:pt-0`) | Нет. `sm:` = 640px; при ≥960px активен `sm:items-center` + `sm:pt-0/sm:pb-0` — форма по-прежнему вертикально центрирована. `items-start` действует только <640px (браузер, не Expo-клиент). Чистый CSS, hydration-риска нет. | ✅ OK |
| `text-base min-[960px]:text-sm` у селектов | `estimate-editor.tsx:626` (offerKind), `:673` (vatStatus) | Нет. При ≥960px `min-[960px]:text-sm` (14px) перекрывает `text-base` (16px) — десктоп без изменений. | ✅ OK |
| (незакрытый хвост той же правки) селекты без `min-[960px]:text-sm` | `estimate-document-common.tsx:324` (entityType), `:553` (clientType); `catalog-autocomplete.tsx:155` (тип новой позиции) | **Низкий, не ломающий.** Эти `<select>` оставлены с голым `text-base` — на десктопе рендерятся 16px вместо 14px у соседних `Input` (`md:text-sm`). Визуальная несогласованность (высота строки/базлайн в форме), функционально не ломает. | ⚠️ Флаг: довести паттерн до конца (добавить `min-[960px]:text-sm`) |
| `bottom-full … min-[960px]:top-full` у дропдауна | `catalog-autocomplete.tsx` панель результатов (`absolute inset-x-0 bottom-full top-auto … min-[960px]:top-full min-[960px]:bottom-auto min-[960px]:mt-1`) | Нет. При ≥960px активен `top-full/bottom-auto/mt-1` — дропдаун раскрывается вниз, как было на десктопе. `bottom-full` (вверх) — только <960px. | ✅ OK |
| `size-11 md:size-9` | `components/ui/class-names.ts` → `threadScrollToBottom` (`… self-center size-11 md:size-9 rounded-full …`) | Нет. `md:` = 768px; при ≥960px `md:size-9` (36px) — десктопный размер scroll-to-bottom без изменений. `size-11` (44px) только <768px. | ✅ OK |
| `@media (max-width: 959px) .aui-button-icon { w/h 2.75rem }` | `app/globals.css:1882` | Нет. При ≥960px правило не применяется, остаётся `size-6 p-1` (24px) из `tooltip-icon-button.tsx:32`. 44px-touch-target только <960px. | ✅ OK |
| (смежная, для справки) `matchMedia("(max-width: 959px)")` в карточке сметы | `estimate-document-card.tsx:104` (`openEditor`) | Нет. `matchMedia` вызывается **только в обработчике клика**, а не в рендере — hydration-риска нет. На ≥960px ветка `matches===false` → `toggleExpanded()` (inline-раскрытие), как раньше. | ✅ OK |

### Вывод по части B

Прошлые правки раунда 1 **не ломают десктоп ≥960px**: все различия
закодированы CSS-брейкпоинтами (`sm:`/`md:`/`min-[960px]:`/`@media 959px`),
которые на десктопе возвращают прежнее поведение. Единственное замечание —
**неполное применение** паттерна `text-base` к трём селектам
(`estimate-document-common.tsx:324,553`, `catalog-autocomplete.tsx:155`), из-за
чего на десктопе они остаются 16px; это косметическая несогласованность, не
регрессия.

### Тесты, покрывающие эти поверхности

- `tests/design-contract.test.mjs`:
  - тест «the estimate editor uses mobile cards without changing desktop table behavior»
    ассертит `data-slot="estimate-mobile-list"`, `matchMedia("(max-width: 959px)")`,
    `min-[960px]:hidden` и `hidden overflow-x-auto min-[960px]:block` — т.е.
    держит контракт «мобильные карточки ↔ десктопная таблица». При включении
    compact или удалении CSS он напрямую не упадёт, но защищает именно ту
    границу 960px, что и правки раунда 1.
  - тест «small browser zoom changes do not flip the workspace into modal mode»
    ассертит `data-workspace-mode="desktop"` и `minSize={640}` — **сломается,
    если включить compact** (shell начнёт менять `data-workspace-mode` на
    `"compact"` в узком окне; ассерт завязан на литерал `"desktop"`).
  - тест «the compact shell matches the mobile chat contract» читает
    `mobile-workspace-header.tsx` и ассертит мёртвый CSS — **сломается при
    удалении** (вариант в), но не при включении.
- `tests/mobile-thread-navigation.test.mjs` — чистая логика long-press
  (`lib/mobile-thread-navigation.ts`), не завязана на CSS/compact; при включении
  compact не пострадает (это отдельный gesture-контракт thread-list, который
  работает через `compactThreadMenu` + `useSyncExternalStore` и жив уже сейчас).
- `tests/workspace-*.test.mjs` (`workspace-canvas-state`, `workspace-document-catalog`,
  `workspace-real-data-boundary`) — состояние canvas/каталога/данных, CSS и
  компакт не затрагивают; при включении compact **не пострадают**, при удалении
  мёртвого CSS — тоже (они не читают globals.css).

**Ключевой риск при включении compact:** `design-contract.test.mjs`
(«small browser zoom…») начнёт падать, поскольку ассертит жёсткий литерал
`data-workspace-mode="desktop"` в shell. Любая попытка (а) обязана одновременно
обновить этот тест и добавить новые hydration-safe тесты на переход
desktop↔compact.
