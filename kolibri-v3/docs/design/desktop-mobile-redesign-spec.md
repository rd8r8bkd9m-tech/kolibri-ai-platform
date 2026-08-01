# Kolibri V3 — desktop canvas и mobile account

Статус: обязательная спецификация реализации.
Дата аудита: 2026-08-01.
Область: desktop web/PWA и native/Expo mobile. Backend-контракты не меняются.

## 1. Основание и продуктовая модель

Kolibri — серверное агентное приложение. Интерфейс отображает серверное
состояние, а не кодирует набор конкретных агентов, моделей, проектов или
прав. Основной сценарий — диалог с агентом, из которого создаются и
редактируются артефакты. Навигация и инструменты должны помогать сценарию, а
не конкурировать с ним за экран.

Референс desktop — переданный скриншот Codex
`codex-clipboard-bf290520-6a16-4438-951d-65ecd4a77c9e.png`:

- слева постоянная спокойная навигация и история;
- в центре один первичный canvas с чатом;
- справа только короткий launcher контекстных инструментов;
- composer визуально является главным рабочим действием;
- панели разделены одним тонким divider, без карточек в карточках.

Mobile должен использовать ту же информационную модель, но иметь отдельную
нативную композицию: Expo Router + React Native, системные safe areas,
SF Symbols/Material Icons через единый `Icon`, haptics и жесты. Примитивы
`@assistant-ui/react-native` обязательны для thread/composer/tool-stream, но
не должны имитироваться в обычных формах профиля.

## 2. Evidence-аудит текущего состояния

### Desktop, 1280×720, `/app?client=desktop`

Проверено в живом приложении с реальной owner-сессией.

1. Закрытый auxiliary canvas выглядит относительно спокойно, но header
   смешивает заголовок диалога, поиск, проект и context toggle в одной узкой
   строке без ясной иерархии.
2. Левый sidebar имеет фактическую ширину 389 px при минимуме 300 px. На
   1280 px он занимает 30% экрана — заметно больше доли референса.
3. После открытия правого canvas одновременно видны панели 389 + ~420 px.
   Центральный чат сжимается примерно до 470 px; composer и длинные ответы
   становятся тесными. Это нарушает правило «chat remains primary».
4. Auxiliary canvas открывается вкладкой «Инструменты», затем повторяет
   список «Проверка / Расчёты / Браузер / Файлы / Дополнительная задача».
   Получаются лишний chrome, лишний уровень выбора и статичная стартовая
   страница вместо полезного контекста.
5. В правом canvas одновременно присутствуют tab label, fullscreen,
   minimize, close и отдельный список инструментов. Контролы корректны по
   смыслу, но визуально превышают необходимую плотность.
6. Центральный canvas остаётся смонтированным — это правильно и должно быть
   сохранено. Resize/fullscreen/minimize/session tabs — полезная техническая
   основа, которую следует упростить, а не дублировать.

### Mobile account, 390×844, `/account`

Проверено в реальном Expo/RN Web клиенте через gateway 3103.

1. Header и возврат работают, bearer-backed профиль загружается — сохранить.
2. Страница выглядит как техническая admin-форма: крупный hero, затем рамка
   формы внутри секции, затем ещё одна рамка для read-only настроек.
3. Вертикальный ритм слабый: avatar/имя/почта/badge занимают почти 200 px,
   после чего пользователь только начинает редактирование.
4. Цвет `border: #b6b6b6` слишком контрастный для grouped settings; рамки
   формы и input конкурируют с контентом.
5. Disabled «Сохранить» показан как большая серая полоса даже когда изменений
   нет. Это создаёт ложное главное действие.
6. Server capability IDs и entitlement IDs выведены сырыми chips. Это
   техническая информация, не пользовательские настройки. Owner-only детали
   должны жить в раскрываемом блоке «Доступ и роль».
7. Нет пользовательских строк «Оформление», «Агент и модель», «Устройства и
   сессии»; текущие значения показаны как статичный debug dump.
8. Скрытый drawer остаётся в accessibility tree вместе с account route —
   скринридер получает дублированную навигацию. Закрытый drawer должен быть
   `inert`/accessibility-hidden средствами навигатора.
9. Хорошая основа уже есть: `SafeAreaView`, `KeyboardAvoidingView`,
   `ScrollView`, real session update/logout, light/dark palette, SF Symbols.

## 3. Целевая информационная архитектура

### 3.1 Desktop

```text
WorkspaceShell
├── NavigationRail (докированная или overlay)
│   ├── BrandActions
│   ├── PrimaryDestinations
│   ├── ThreadHistory
│   └── AccountTrigger
├── PrimaryCanvas
│   ├── CompactHeader
│   └── ChatThread (постоянно смонтирован)
│       └── Composer
└── AuxiliaryCanvas (по требованию, 0..N session tabs)
    ├── CanvasToolbar
    └── ActiveSurface
        ├── Files
        ├── Browser
        ├── Review
        ├── Terminal
        ├── DocumentEditor
        └── SecondaryChat (последующая фаза)
```

Правила:

- «Рабочий стол», «Инструменты» и отдельная launcher-страница удаляются.
- Toggle открывает последнюю полезную surface; если истории нет — Files.
- Files/Browser/Review/Terminal являются server/capability-driven entries.
  Отсутствующая capability скрывает entry, а не показывает неработающую
  кнопку.
- Клик по артефакту из чата открывает именно DocumentEditor с этим artifact
  ID. Артефакт остаётся в сообщении и появляется в Files; копий данных нет.
- Клик по Projects/Documents/References слева меняет primary destination, но
  не уничтожает thread runtime. Возврат в Chat мгновенный, draft сохранён.
- Auxiliary tabs независимы по UI-state, но содержат project/thread scope из
  server context. Никаких singleton-заглушек с общей выбранной сущностью.

### 3.2 Mobile shell

```text
MobileRoot
├── DrawerNavigator
│   ├── ChatScreen
│   ├── EstimatesScreen
│   └── AccountScreen
├── Thread primitives (@assistant-ui/react-native)
└── System surfaces (share, voice, file picker)

AccountScreen
├── NativeScreenHeader
├── ScrollView
│   ├── IdentitySummary
│   ├── SettingsGroup «Профиль»
│   ├── SettingsGroup «Персонализация»
│   ├── SettingsGroup «Приложение»
│   ├── SettingsGroup «Доступ и роль» (collapsed)
│   └── DestructiveAction «Выйти»
└── InlineSaveBar (только при dirty state)
```

Mobile account — пользовательская настройка продукта, не admin dashboard.
Raw claim IDs не показываются по умолчанию. Owner-переход в расширенную
админку — отдельная строка, только если server capability это разрешает.

## 4. Компонентная декомпозиция

### Desktop, существующие файлы

- Сохранить `WorkspaceSidebar`, `Thread`, `CanvasFrame`, canvas session state,
  resizable primitive и lazy surface loading.
- `WorkspaceHeader` сократить до semantic shell: title/context, Search,
  ProjectPicker, AuxiliaryCanvasToggle.
- `CanvasFrame` оставить единственным chrome для всех right surfaces.
- `CanvasWorkspace` разделить на registry resolver и surface components; он
  не должен рисовать launcher-карточку.
- `ContextPanel` должен стать registry/command source, а не второй страницей.
- Любой surface регистрируется описателем
  `{id,title,icon,requiredCapability,render}`. Frontend не содержит список
  конкретных моделей/агентов.

### Mobile, новые/переиспользуемые primitives

- `components/shell/native-screen-header.tsx` — back/menu, centered title,
  optional trailing action; 48 px tap targets.
- `components/settings/settings-group.tsx` — единый grouped container.
- `components/settings/settings-row.tsx` — icon, title, value, chevron/switch,
  press/focus/disabled states.
- `components/settings/profile-name-editor.tsx` — label + native input;
  dirty/validation/save state.
- `components/settings/identity-summary.tsx` — avatar 64, name, email, role.
- `components/settings/disclosure-section.tsx` — collapsed technical details.
- Использовать существующие `CircleButton`, `Icon`, `useTheme`, `haptics`,
  `useMobileSession`; не копировать session/API logic.

## 5. Размеры, typography и tokens

### Shared principles

- Grid: 4 px; рабочие интервалы 8/12/16/20/24/32.
- Иконки: desktop 16 px, stroke 1.9; mobile 20–22 px regular, 24–27 px для
  navigation; tap target не меньше 44×44, целевой 48×48.
- Один divider `hairline` между крупными областями. Карточки не вкладываются.
- Radius: control 10–12, grouped surface 16, composer 20/27, circle 999.
- Focus: 3 px ring desktop; mobile/web keyboard focus 2–3 px. Pressed mobile
  opacity 0.62–0.72 + light haptic на selection.

### Desktop

- Navigation: default 320 px; min 280; max 360. Исторические 389/440 удалить.
- Header: 48 px; horizontal padding 12; icon button 28; gap 4.
- Primary chat: hard minimum 640 px when auxiliary is docked.
- Auxiliary: default 400; min 320; max 640.
- Docked 3-pane разрешён, только если `viewport >= nav + 640 + aux` (минимум
  1240 при nav 280 и aux 320). При меньшей доступной ширине:
  1) сначала nav переходит в overlay; 2) если всё ещё тесно — auxiliary в
  overlay/fullscreen. Нельзя ужимать chat ниже 640.
- Thread text max 46rem, message body 15–16/1.55, metadata 12/1.3.

### Mobile

- Screen width contract: 320–599; QA baseline 390×844.
- Header 64 logical px + safe-area; content inset 16.
- Title: 17 px/22, weight 600 iOS / 700 Android, letter spacing -0.2.
- Hero: avatar 64, name 20/24, email 14/20; total content height <= 132.
- Section label: 13/18, weight 600, muted; left inset 4.
- Settings row: min-height 54; horizontal padding 14; title 16/21; value
  14/19 muted; icon container 28.
- Input: min-height 48, font 16 (Safari zoom prevention), radius 12.
- Bottom padding: `max(24, safe-area-bottom + 16)`.
- Palette uses `Colors`; adjust light `border` to a subtle neutral
  (`#d9d9dc`) and use it only for group boundaries. Dark group `#1c1c1e`,
  divider rgba white 12%.

## 6. State transitions

### Auxiliary canvas

```text
closed
  --open(last|Files)--> docked
docked
  --select surface/artifact--> docked(active)
  --maximize--> fullscreen
  --minimize--> shelf
  --close--> closed (session retained)
fullscreen --restore--> docked
shelf --restore--> docked
```

- `Escape`: fullscreen → docked → closed; focus возвращается launcher.
- При открытии artifact из chat активируется существующая вкладка по artifact
  ID либо создаётся новая. Повторный клик не создаёт дубль.
- Loading surface показывает skeleton внутри canvas, а не заменяет shell.
- Error surface содержит message, retry и diagnostics ID; chat продолжает
  работать.
- Empty Files: «Документов пока нет» + действие «Создать в чате».

### Mobile account

```text
restoring -> account skeleton | signed-out auth
account clean --edit name--> dirty + inline save
dirty --save--> saving -> success(clean) | error(dirty)
clean --open row--> route/sheet
clean --expand access--> disclosure open
logout --confirm/destructive action--> logging-out -> auth
```

- Не показывать disabled save постоянно; save bar существует только в dirty
  state. Ошибка остаётся рядом с editor и объявляется live region.
- Back при dirty state: нативный confirm sheet «Сохранить изменения?».
- Theme row показывает «Системная / Светлая / Тёмная»; выбор должен быть
  связан с существующим theme authority.
- Agent/model values приходят из server catalog; UI не перечисляет Mimocode,
  Codex или конкретную модель в коде.

## 7. Loading, empty, error, focus и accessibility

- Account restoring: header + identity/settings skeletons; не пустой spinner.
- Auth error: human message, retry, сохранённый email; пароль не логируется.
- Profile save: row/input остаются видимыми, save action busy, повторный tap
  заблокирован.
- Canvas loading/empty/error не изменяют размеры layout.
- Все icon-only controls имеют локализованный accessibility label.
- Закрытые drawer/canvas/account overlay исключены из focus/accessibility tree
  (`inert`/`aria-hidden` web, navigation detach/freeze native).
- Порядок focus desktop: sidebar → header → thread → composer → auxiliary.
- Touch targets >=44; long press thread item открывает context menu и даёт
  medium haptic; swipe drawer не конфликтует с horizontal artifact controls.
- `prefers-reduced-motion`/Reduce Motion отключает decorative motion, но не
  убирает progress/status.

## 8. Что удалить и что сохранить

Удалить:

- статичную страницу «Рабочая область/Инструменты»;
- повторные headers/title rows внутри surface;
- постоянную серую кнопку save в clean account;
- raw capability/entitlement chips из основного account flow;
- hardcoded agent/model/feature entries;
- nested bordered cards и дублирующие mobile web/native shells.

Сохранить:

- левую desktop навигацию и history;
- постоянный центральный assistant-ui thread runtime;
- canvas session/resizable/fullscreen/minimize mechanics;
- real bearer mobile session, profile PATCH и logout;
- `@assistant-ui/react-native` для chat primitives;
- `Icon` abstraction, safe areas, theme, haptics;
- server-driven projects/files/capabilities/agents/models.

## 9. Screenshot-based acceptance checklist

### Desktop reference comparison

- [ ] При закрытом auxiliary screenshot читается как три зоны референса:
      nav / primary chat / свободный contextual edge, без «Рабочего стола».
- [ ] Открытие Files показывает Files сразу, без промежуточной страницы
      «Инструменты».
- [ ] На 1280×720 chat остаётся >=640 px: nav автоматически overlay/collapsed
      либо auxiliary overlay; composer не ломается и не перекрывается.
- [ ] На >=1600 px nav + chat + docked auxiliary разделены двумя hairline,
      без карточек-контейнеров вокруг колонок.
- [ ] Canvas header содержит одну вкладку/название и максимум три действия;
      toolbar surfaces не повторяет header.
- [ ] Artifact card из chat открывает тот же документ справа, без дубля и без
      сброса scroll/draft chat.
- [ ] Resize, fullscreen, minimize, restore, close и Escape проверены.
- [ ] Light/dark screenshots не содержат контрастных случайных рамок.
- [ ] Console: 0 React/runtime errors и 0 invalid DOM prop warnings.

### Mobile account, 390×844

- [ ] В первом viewport видны header, compact identity, полностью группа
      «Профиль» и начало «Персонализация»; нет огромной disabled save полосы.
- [ ] Account визуально совпадает с chat shell: одинаковые 48 px header
      controls, 16 px insets, одна icon family, одинаковый light/dark canvas.
- [ ] Grouped rows не выглядят как desktop form cards; нет card-in-card.
- [ ] Изменение имени показывает inline save, успешный PATCH обновляет avatar
      и drawer; error остаётся редактируемым.
- [ ] Сырые claim IDs скрыты; owner видит лаконичную строку «Администрирование»
      и раскрываемый «Доступ и роль».
- [ ] Back, keyboard avoidance, vertical scroll, focus-visible, safe-area и
      bottom inset проверены в Safari/RN Web.
- [ ] Drawer закрыт и отсутствует в accessibility tree account screen.
- [ ] Voice/file/thread gestures не регрессировали.
- [ ] Mobile unit/contract tests, lint, TypeScript и browser console зелёные.

## 10. Каноническая evidence-матрица mobile

Все файлы `docs/design-evidence/mobile-chatgpt` и
`docs/design-evidence/mobile-comparison` просмотрены. Геометрия ниже
масштабируется из сохранённого capture 318×701 в логический viewport, но
отношения, ритм и иерархия обязательны. Kolibri меняет только названия и
доступные server-driven функции.

| Evidence | Состояние | Компонент Kolibri | Проверяемое соответствие |
| --- | --- | --- | --- |
| `01-empty-chat-light.jpg` | Пустой чат | `MobileHeader`, `Thread.Empty`, `Composer` | 48 px круглые header targets; подчёркнутый центр; starter rows у нижнего края; composer inset 16–18, высота около 78, две строки действий. |
| `02-composer-focused-light.jpg` | Composer focus | `Composer` | Caret и focus без сдвига нижнего action row; input 16 px; фиксированы plus/model/mic/voice. |
| `03-weather-question-composed.jpg` | Однострочный prompt | `Composer` | Текст остаётся в верхней строке capsule; send — 30 px accent circle; нижние controls не прыгают. |
| `04-weather-streaming-stop.jpg` | Первый streaming frame | `Thread`, `Composer` | User bubble справа; send превращается в stop без relayout; empty title заменён active-chat actions. |
| `05-weather-result-light.jpg` | Weather result | `MessageBubble`, generative weather surface | Content inset 20; компактная structured card + prose; floating scroll-to-bottom над composer; никакого horizontal overflow. |
| `06-image-question-composed.jpg` | Multiline composer | `Composer` | Capsule растёт вверх до ~139 scaled px; bottom controls остаются на одной оси. |
| `07-image-streaming-stop.jpg` | Image request streaming | `Thread`, `Composer` | Правый user bubble с max width; stop остаётся доступен; свободный canvas не заполняется chrome. |
| `08-image-generation-skeleton.jpg` | Initial generative UI | generated-image tool surface | Muted activity label; rounded skeleton ~230×307 reference ratio; composer pinned. |
| `09-image-generation-preview-strip.jpg` | Preview generation | generated-image tool surface | Full content width preview, top-right preview pill, 4-slot thumbnail strip, стабильная высота. |
| `10-image-result-light.jpg` | Generated result | generated-image result | Square rounded image; in-card Edit pill + share circle; secondary compact actions below. |
| `11-sidebar-open-light.jpg` | Drawer open | `DrawerContent` | Width ~74% viewport, previous screen strip visible; no heavy scrim; 43 px row rhythm; primary destinations then pinned/recent; bottom account/settings reachable. |
| `12-projects-light.jpg` | Projects | mobile projects surface | 3-part header; horizontal filter pills; flat list with quiet icon tiles/timestamps; bottom search pinned. |
| `13-library-light.jpg` | Library | mobile library surface | 2-column mixed grid, 12 px gutter, consistent cell radius, category tabs and bottom search. |
| `14-remote-light.jpg` | Connection/project/chat list | agent/runtime source surface | Horizontal connection chips; flat sectioned lists; row progress/action states; bottom search + primary action. |
| `15-remote-sort-menu-light.jpg` | Floating menu | shared action menu | Trailing rounded menu ~60% width; grouped actions + one divider; checkmark current selection; icon/label baseline consistent. |
| `16-remote-settings-connections-light.jpg` | Settings sheet | `AccountScreen`, `SettingsGroup`, `SettingsRow` | Grouped-system language: neutral grouped background, white/dark raised groups, no outlined debug cards, 54–56 px rows, centered title and clear close/back. |
| `18-active-chat-back-light.jpg` | Tool-stream activity | assistant-ui tool/reasoning presentation | Compact chronological tool rows with muted completed/running states; no giant expanded tool cards; composer remains visible. |
| `19-back-transition-intermediate-light.jpg` | Directional transition | Expo Router/Drawer navigation | Incoming list and outgoing screen preserve spatial direction; no white flash; state remains mounted through transition. |
| `20-chat-list-light.jpg` | Chat list | `DrawerContent` / thread-list surface | Flat title+preview rows, selected segmented tab, independently scrollable list, bottom action remains reachable. |
| `empty-chat-dark-reference-vs-baseline.jpg` | Dark empty comparison | theme tokens + header/thread/composer | Reference geometry wins: larger starter labels/spacing, 48 px outlined header controls, wider/taller composer, true black canvas. |
| `empty-chat-dark-header-focus.jpg` | Dark header comparison | `MobileHeader`, `CircleButton` | Equal left/right targets, exact centered underlined title, thin neutral outlines, consistent glyph scale. |
| `empty-chat-dark-composer-focus.jpg` | Dark composer comparison | `Composer`, starter actions | Reference-sized labels/icons and 78 px composer; accent reserved for live/stop/send; no compressed baseline variant. |
| `thread-long-press-menu-390x844.png` | Conversation long press | `ThreadListItem` controlled menu | 250 ms pressed state; menu at 650 ms; drawer remains; Pin/Archive/Delete; short tap navigates; 22 px move cancels; mouse does not long-press. |
| `interaction-notes.md` | Measured geometry/limitations | all mobile shell components | Use documented centers, insets, composer/starter/result sizes; do not invent unobserved animation timings. |
| `state-matrix.md` | Coverage authority | QA suite | Confirm every captured endpoint; explicitly mark keyboard/model/tools states needing later evidence rather than fabricating them. |
| `long-press-acceptance.md` | Gesture contract | thread list tests | Preserve verified timing, cancellation and synthetic-click suppression behavior. |

Файл `17` отсутствует в сохранённом evidence; это не разрешает подменять его
придуманным состоянием. Account/settings визуальный язык берётся из `16`, а
данные — только из реальной bearer-сессии Kolibri.

### Implementation cut после evidence-review

Пересобираются:

- `app/account.tsx`: старая hero + nested form/debug cards удаляется;
- `components/thread-list/drawer-content.tsx`: иерархия и accessibility
  приводятся к `11`/`20`, без «Рабочего стола»;
- `components/shell/mobile-header.tsx`: геометрия сверяется с `01` и dark
  comparison;
- `components/assistant-ui/composer.tsx`: состояния `01`–`07` и dark
  comparison;
- settings primitives создаются один раз и переиспользуются.

Сохраняются без подмены:

- реальный `MobileSessionProvider`, bearer refresh/PATCH/logout;
- assistant-ui thread/runtime adapter;
- исправленный scroll/pointer-events контракт;
- verified long-press behavior;
- pet integration points (сама pet-подсистема принадлежит отдельному owner).

## 11. Порядок реализации

1. Mobile: вынести settings primitives, пересобрать account, сохранить real
   session contract, добавить состояния и тесты.
2. Mobile: визуальный QA 390×844 light/dark, keyboard/scroll/accessibility.
3. Desktop: удалить launcher surface и сделать direct surface registry.
4. Desktop: ввести hard minimum primary canvas и адаптивное dock/overlay
   поведение.
5. Desktop: пройти screenshot/state checklist и regression tests.
