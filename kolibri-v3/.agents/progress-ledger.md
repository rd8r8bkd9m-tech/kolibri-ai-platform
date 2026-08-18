# Kolibri V3 — progress ledger

Состояния: `DISCOVERING | IMPLEMENTING | INTEGRATING | VERIFYING | BLOCKED | DONE`.
Правило: production-код раньше тестов; `DONE` — только по `definition-of-done`
(поведение через реальный entry point, контракты обновлены, без плейсхолдеров).

## Текущая задача

### MOBILE-017 — Новый мобильный клиент с нуля: первый сметный срез
- Состояние: INTEGRATING
- Acceptance: лэндинговая палитра в `constants/theme.ts`; mobile export
  `EstimateClient.export` для PDF/XLSX/DOCX/CSV; `EstimateEditor` widget
  рендерится в чате карточкой; `EstimatePositionSheet` больше не remount'ится
  по `mode`.
- Файлы: `constants/theme.ts`,
  `src/verticals/construction-estimates/{client,export}.ts`,
  `src/product-chat/estimate-widget.ts`,
  `components/assistant-ui/{message,estimate-widget-card}.tsx`,
  `src/components/overlays/PositionSheet.tsx`, `app/estimates.tsx`,
  `lib/mobile/{export-file,observability,offline-cache}.ts`,
  `src/product-chat/runtime-provider.tsx`,
  `components/design-system/{EmptyState,ErrorState}.tsx`,
  `components/shell/surface-boundary.tsx`, `src/data/menu.ts`,
  `src/components/overlays/Sidebar.tsx`, `package.json`.
- Проверка: `mobile:typecheck`, `lint`, `npm test` (207/207),
  `test:qa:mobile`, `export:web` — зелёные.
- Skills: kolibri-mobile-ui, kolibri-mobile-chat, primitives, dark-mode.
- Evidence: QA mobile OK; web export 9 routes.
- Device E2E: добавлен `.github/workflows/mobile-e2e.yml`; `export:ios` и
  `export:android` проходят локально; Maestro CLI в текущем окружении
  отсутствует, поэтому фактический прогон отложен до CI/устройства.

### MOBILE-016 — Единый мобильный UI-ритм по ChatGPT-эталону
- Состояние: DONE
- Acceptance: `constants/theme.ts` расширен единым `Spacing`, `FontSize`,
  `FontWeight`, `LineHeight`, `LetterSpacing`, `Glass`, `WebShadow` и
  недостающими радиусами; целевые экраны и примитивы
  (`index`, Sidebar, account, projects, library, remote, estimates,
  message/action-bar/branch-picker, composer, model-selector, thread,
  shell/settings/auth/overlays/ui) больше не содержат hardcoded
  colors/radii/padding/margin/gap/font-стилей вне токенов.
- Файлы: `constants/theme.ts`, `app/{_layout,index,account,projects,library,
  remote,estimates}.tsx`, `src/components/overlays/{Sidebar,ContextMenu,
  ProjectSheet,PositionSheet}.tsx`, `src/components/ui/*`,
  `components/assistant-ui/{message,message-action-bar,message-branch-picker,
  model-selector,thread}.tsx`, `components/assistant-ui/composer/*`,
  `components/shell/*`, `components/settings/*`,
  `components/auth/auth-screen.tsx`.
- Проверка: `npm run mobile:typecheck`, `npm --prefix apps/kolibri-mobile run
  lint`, `npm test` (207/207), `npm run test:qa:mobile` (chat OK + flow OK),
  `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm --prefix
  apps/kolibri-mobile run export:web` — зелёные.
- Skills: kolibri-mobile-ui, kolibri-mobile-chat, primitives, dark-mode.
- Evidence: `rg` по целевым файлам не находит hex/rgba вне theme/glass и
  прямых `fontSize|fontWeight|letterSpacing|lineHeight|borderRadius|padding|
  margin|gap` числовых литералов; QA mobile OK; export 9 routes.

### MOBILE-015 — Финальный hardcoded-colors pass (ChatGPT-эталон)
- Состояние: DONE
- Acceptance: composer controls/attachments/model-selector/thread/PositionSheet
  используют theme tokens вместо `#007AFF`, `#FFFFFF`, `#111111`,
  `#9A9AA0`; shadow token импортирован в thread/composer styles.
- Файлы: `components/assistant-ui/composer/{index,styles,controls,attachments}.tsx`,
  `components/assistant-ui/model-selector.tsx`,
  `components/assistant-ui/thread.tsx`,
  `src/components/overlays/PositionSheet.tsx`.
- Проверка: `npm run mobile:typecheck`, `npm run lint` (0 errors), `npm test`
  (29/29), `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm run export:web`,
  `npm run test:qa:mobile` — зелёные.
- Skills: design-system, kolibri-mobile-ui, premium-mobile-ui.
- Evidence: `rg` hardcoded hex/rgba в composer/model-selector/thread/overlays
  сведён к glass-материалу и shadow-эффектам; QA mobile OK; export 9 routes.

### MOBILE-014 — Типографический и отступный unification pass
- Состояние: DONE
- Acceptance: `constants/theme.ts` содержит единые typography-токены для
  settings, projects, identity, suggestion; settings-group/row,
  identity-summary, projects и empty-chat используют эти токены вместо
  локальных fontSize/fontWeight.
- Файлы: `constants/theme.ts`, `components/settings/settings-group.tsx`,
  `components/settings/settings-row.tsx`,
  `components/settings/identity-summary.tsx`, `app/projects.tsx`,
  `components/assistant-ui/thread.tsx`.
- Проверка: `npm run mobile:typecheck`, `npm run lint` (0 errors), `npm test`
  (29/29), `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm run export:web`,
  `npm run test:qa:mobile` — зелёные.
- Skills: design-system, kolibri-mobile-ui, premium-mobile-ui.
- Evidence: QA mobile OK; web export 9 routes.

### MOBILE-013 — Visual unification pass: один примитив/Icon/shell
- Состояние: DONE
- Acceptance: один `CircleButton` (`src/components/ui`), один `Icon`
  (`src/components/icons`), header и shell используют его; `estimates`
  переведён на `NativeScreenShell`; пустой чат больше не использует
  hardcoded `#52525B`.
- Файлы: `src/components/ui/CircleButton.tsx`,
  `components/shell/circle-button.tsx`, `components/ui/icon.tsx` (удалён),
  `components/shell/native-screen-header.tsx`,
  `components/shell/native-screen-shell.tsx`, `app/estimates.tsx`,
  `app/account.tsx`, `components/assistant-ui/thread.tsx`,
  `components/pet/pet-mini-assistant.tsx`,
  `components/settings/native-billing-settings.tsx`.
- Проверка: `npm run mobile:typecheck`, `npm run lint` (0 errors), `npm test`
  (29/29), `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm run export:web`,
  `npm run test:qa:mobile` — зелёные.
- Skills: design-system, kolibri-mobile-ui, premium-mobile-ui, react-native-components,
  kolibri-mobile-navigation.
- Evidence: QA mobile OK; web export 9 routes; `rg 'from "@/components/ui/icon"'`
  пусто.

### MOBILE-012 — Финальная чистка и сверка
- Состояние: DONE
- Acceptance: preview-контур `/chatgpt` и `src/App.tsx`, `src/screens`,
  `src/theme/tokens.ts` удалены; `src/data/copy.ts` читает токены из
  `constants/theme.ts`. Реальный `/app` не зависит от preview-контура.
- Файлы: удалены `app/chatgpt.tsx`, `src/App.tsx`,
  `src/screens/HomeScreen.tsx`, `src/theme/tokens.ts`; изменены
  `app/_layout.tsx`, `src/data/copy.ts`, `components/assistant-ui/thread.tsx`,
  `scripts/qa-mobile-flow.mjs`.
- Проверка: `npm run verify` — structure/architecture/backend/typecheck/test/
  cargo gates passed; `npm run test:qa:mobile` — chat OK + flow OK;
  `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm run export:web` — 9 routes.
- Skills: kolibri-v3-development, update, integration-testing, design-to-code,
  kolibri-mobile-qa.
- Evidence: quick verify `All quick verification gates passed`; web export 9
  static routes; QA mobile OK.

### MOBILE-011 — Расширенный real-browser mobile QA flow
- Состояние: DONE
- Acceptance: `test:qa:mobile:flow` проверяет регистрацию → чат →
  перезагрузку/историю → drawer/пользователя → переход в Проекты →
  Library/Remote shell → новую задачу → account → logout/login. `test:qa:mobile`
  проходит chat + flow. Селекторы детерминированы по aria-label, без
  координатных кликов.
- Файлы: `scripts/qa-mobile-flow.mjs`, `scripts/qa-mobile-chat.mjs`.
- Проверка: `npm run test:qa:mobile` — chat OK + flow OK.
- Skills: kolibri-mobile-qa, visual-e2e, development-smoke-check, mobile-e2e.
- Evidence: `[qa-mobile-chat] OK`, `[qa-mobile-flow] OK`.

### MOBILE-010 — Унификация shell и вторичных экранов
- Состояние: DONE
- Acceptance: `account`, `projects`, `library`, `remote` используют общий
  `NativeScreenShell` (SafeAreaView + NativeScreenHeader + тема) вместо
  повторяющихся локальных обёрток. Один back/shared header, единый фон и
  safe-area обработка. Защищённые billing/vertical слои не изменены.
- Файлы: `components/shell/native-screen-shell.tsx`,
  `app/{account,projects,library,remote}.tsx`,
  `tests/mobile-account.test.mjs`, `scripts/qa-mobile-chat.mjs`.
- Проверка: `npm run mobile:typecheck`, `npm run lint` (0 errors), `npm test`
  (29/29), `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm run export:web`,
  `npm run test:qa:mobile:chat` — зелёные.
- Skills: kolibri-mobile-navigation, kolibri-mobile-ui, premium-mobile-ui,
  expo-native-ui, visual-e2e.
- Evidence: web export 10 routes; QA chat OK; тест account обновлён под shell.

### MOBILE-009 — Canonical assistant-ui message/action-bar/branch layer
- Состояние: DONE
- Acceptance: `message.tsx` больше не использует deprecated
  `MessagePrimitive.If`; условное появление action bar/suggestions
  реализовано через `AuiIf`. `MessagePrimitive.Parts`,
  `ActionBarPrimitive.Copy/Reload` и `BranchPickerPrimitive.Previous/Next`
  остаются canonical primitives. Fallback и data-cards продолжают работать
  без крашей.
- Файлы: `components/assistant-ui/message.tsx`,
  `components/assistant-ui/message-action-bar.tsx`,
  `components/assistant-ui/message-branch-picker.tsx`,
  `scripts/qa-mobile-chat.mjs`.
- Проверка: `npm run mobile:typecheck`, `npm run lint` (0 errors), `npm test`
  (29/29), `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm run export:web`,
  `npm run test:qa:mobile:chat` — зелёные.
- Skills: primitives, code-refactoring, react-native-components,
  kolibri-mobile-chat.
- Evidence: `rg 'MessagePrimitive\\.If|ThreadPrimitive\\.If|ComposerPrimitive\\.If'
  components/assistant-ui src/components` — пусто; QA chat OK.

### MOBILE-008 — Единая дизайн-система: миграция sidebar/overlays/ui на useTheme
- Состояние: DONE
- Acceptance: сайдбар, контекстное меню, project/position sheet и все
  `src/components/ui/*` читают цвета/радиусы/типографику из
  `constants/theme.ts` через `useDesignTokens()`, а не статические
  `src/theme/tokens.ts`. Светлая/тёмная тема работают через `useTheme()`.
- Файлы: `constants/theme.ts`, `hooks/use-design-tokens.ts`,
  `src/components/ui/*`, `src/components/overlays/{Sidebar,ContextMenu,
  ProjectSheet,PositionSheet}.tsx`.
- Проверка: `npm run mobile:typecheck`, `npm run lint` (0 errors), `npm test`
  (29/29), `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm run export:web`,
  `npm run test:qa:mobile:chat` — зелёные.
- Skills: design-system, dark-mode, primitives, kolibri-mobile-ui,
  kolibri-mobile-chat.
- Evidence: `rg 'from "@/src/theme/tokens"' src/components` остались только
  иконки-артефакты (не UI-примитивы); web export 10 routes; QA chat OK.

### MOBILE-007 — Возврат реального чата на `/app` и canonical assistant-ui scroll
- Состояние: DONE
- Acceptance: `/app?client=mobile` снова использует боевой `MobileSessionProvider +
  MobileHeader + Thread + Composer`, а не preview `ChatGptSpecApp`; чат
  регистрирует нового пользователя, отправляет сообщения из композера и
  корректно скроллит длинный тред на react-native-web.
- Файлы: `apps/kolibri-mobile/app/index.tsx`,
  `components/assistant-ui/thread.tsx`,
  `components/assistant-ui/composer/index.tsx`,
  `src/components/overlays/{Sidebar,DrawerContentAdapter,PositionSheet}.tsx`,
  `app/estimates.tsx`, тесты `mobile-{account,chatgpt-plan,navigation-focus}.test.mjs`.
- Проверка: `npm run mobile:typecheck`, `npm run lint` (0 errors), `npm test`
  (29/29), `EXPO_PUBLIC_API_BASE_URL=https://127.0.0.1:8002 npm run export:web`,
  `npm run test:qa:mobile:chat` — зелёные.
- Skills: assistant-ui, primitives, thread-list, chat-interface,
  kolibri-mobile-chat, kolibri-mobile-ui.
- Evidence: QA `test:qa:mobile:chat` OK; web export 10 static routes.

### MOBILE-005 — ChatGPT-parity mobile UI: новый чат, сайдбар и theme-aware dialogs
- Состояние: DONE
- Acceptance: нейтральная ChatGPT-палитра (blue send `#3982f7`/`#2f7fff`),
  стартеры пустого чата выровнены с desktop `MOBILE_STARTERS`
  (`Создать изображение`, `Напиши или отредактируй`, `Искать в интернете`),
  сайдбар с заголовком «КолИ», секциями «Закреплено»/«Недавнее» и footer
  «Чат» + настройки; системные диалоги theme-aware; лейбл модели не течёт
  сырым `platform:/user:` id.
- Файлы: `apps/kolibri-mobile/constants/theme.ts`,
  `components/assistant-ui/{thread.tsx,message.tsx,composer/controls.tsx,
  model-selector.tsx,cards/weather-card.tsx}`,
  `components/{thread-list/drawer-content.tsx,auth/auth-screen.tsx,
  settings/{settings-row.tsx,identity-summary.tsx,profile-name-editor.tsx}}`,
  `components/ui/icon-mappings.ts`, `app/account.tsx`, `lib/dialogs.tsx`,
  `src/models/client.ts`.
- Проверка: `npm run mobile:typecheck`, `npm run lint`, `npm test`,
  `npm run export:web` — зелёные; 29/29 тестов.
- Skills: accessibility, animation-motion, dark-mode, design-system,
  design-to-code, kolibri-mobile-ui, kolibri-mobile-chat,
  frontend-app-builder, frontend-testing-debugging.
- Evidence: typecheck/lint OK; 29 тестов pass; web export 9 static routes.

### MOBILE-006 — Pixel-perfect ChatGPT-спека (экраны A–D) как preview-route
- Состояние: DONE
- Acceptance: спецификация из `pasted-text.txt` реализована как
  самодостаточный preview `/chatgpt?client=mobile`: токены, data/*, ui-
  примитивы, Sidebar, ContextMenu, ProjectSheet, HomeScreen, App; строки
  не захардкожены, тап-таргеты ≥44pt, custom drawer/sheet/context-menu на
  reanimated, хаптика medium на long-press/открытие меню.
- Файлы: `apps/kolibri-mobile/src/{theme/tokens.ts,data/*,
  components/ui/*,components/overlays/*,components/icons/MenuIcon.tsx,
  screens/HomeScreen.tsx,App.tsx}`, `app/chatgpt.tsx`, `app/_layout.tsx`,
  `components/ui/icon-mappings.ts`.
- Проверка: `npm run typecheck`, `npm run lint`, `npm test`,
  `npm run export:web` — зелёные; SSR `/chatgpt` содержит все лейблы спеки.
- Skills: frontend-app-builder, frontend-testing-debugging, design-to-code,
  kolibri-mobile-ui, kolibri-mobile-navigation.
- Evidence: typecheck/lint OK; 29 тестов pass; web export 10 routes; curl
  `/chatgpt?client=mobile` → ChatGPT/Обновить/Изображения/Библиотека/
  Проекты/Удаленно/Больше/Закреплено/Фабрика Колибри/Недавнее/
  Спросить Chat/Создать изображение/Напиши или отредактируй/Искать в
  интернете.

### SKILLS-001 — Настройка системы `.agents/skills` (эта задача)
- Состояние: DONE
- Acceptance: `AGENTS.md` требует skill routing; роутер выбирает скиллы по
  задаче; контроллер цикла описан; леджер ведётся; profiles/index/валидаторы
  согласованы и работают на реальных запросах.
- Файлы: `kolibri-v3/AGENTS.md`, `.agents/scripts/skill-router.mjs`,
  `.agents/skills/{skill-router,development-controller}/SKILL.md`,
  `.agents/progress-ledger.md`, `.agents/agent-profiles.json`,
  `.agents/skills-index.json`, `.agents/scripts/validate-skills.sh`,
  `.agents/scripts/validate_skills.py`.
- Проверка: `node .agents/scripts/skill-router.mjs` на 3 задачах;
  `bash .agents/scripts/validate-skills.sh`; quick_validate новых скиллов.
- Evidence: роутер на «почини композер…» → kolibri-mobile-chat/model-selector/
  chat-interface; «смета…экспорт xlsx» → estimate-*/kolibri-estimates-engine;
  «сайдбар и back» → thread-list/kolibri-mobile-navigation. Валидация:
  `package=250 flat=55 total=305 OK`; quick_validate новых скиллов — valid.

## Next (следующая production-задача)

### MOBILE-003 — Модель из label открывается bottom-sheet (убрать поповер)
- Состояние: DONE
- Принятое поведение: нажатие на метку модели в композере открывает нижний
  шит (`Modal slide`), как у pill-варианта; всплывающий dropdown и `labelWrap`
  удаляются; дублирование body шита устранено.
- Файлы: `apps/kolibri-mobile/components/assistant-ui/model-selector.tsx`
- Проверка: `npm run typecheck`, `npm run lint`, `npm test`; бандл через шлюз.
- Skills: `kolibri-mobile-chat`, `kolibri-mobile-ui`, `code-refactoring`,
  `ui-regression-review`
- Evidence: typecheck/lint/28 тестов зелёные; бандл: `optionsScroll`=0
  (поповер удалён), `sheetBackdrop` присутствует; label-триггер ведёт в общий
  `Modal slide` (единый `setOpen(true)`).

### MOBILE-004 — Композер «в один этаж» по референсу (после визуальной сверки)
- Состояние: DONE
- Принятое поведение: однорядная капсула — `+ → input(flex) → модель → mic →
  send/stop/voice`; input растёт до 4 строк вверх, контролы на месте; высота
  ~48 (контролы 30 + padding 9+9), radius 27, inset 18.
- Файлы: `apps/kolibri-mobile/components/assistant-ui/composer/{styles.ts,
  index.tsx}`, `tests/mobile-chatgpt-plan.test.mjs`, скиллы kolibri-mobile-
  {ui,chat,qa}, `docs/MOBILE_CHATGPT_DEVELOPMENT_PLAN.md`
- Проверка: typecheck/lint/28 тестов; бандл через шлюз (`actionsRow`=0).
- Skills: `chat-interface`, `kolibri-mobile-chat`, `primitives`,
  `kolibri-mobile-ui`, `kolibri-mobile-qa`
- Evidence: см. выше; сверка геометрии по OCR-скрипту — после ручной
  проверки в PWA (референс 02 двухуровневый, продуктовое решение — один ряд).

## История

_2026-08-13 — леджер создан вместе с системой skill routing (SKILLS-001);
закрыта первая production-задача по циклу контроллера (MOBILE-003);
завершена MOBILE-005 — полный UI/UX redesign мобильного клиента на бренд
Kolibri._
