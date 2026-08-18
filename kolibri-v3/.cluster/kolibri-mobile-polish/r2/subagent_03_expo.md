# Аудит Expo-клиента Kolibri V3 (mobile)

READ-ONLY код-аудит. Файлы НЕ редактировались — правки делает не этот агент.
Область: `apps/kolibri-mobile` (React Native / Expo, handoff `?client=mobile`).
Прочитаны: `app/_layout.tsx`, `app/index.tsx`, `app/app.tsx`, `app/account.tsx`, `app/estimates.tsx`,
`app/estimate/[projectId].tsx`, `app/projects.tsx`, `app/library.tsx`, `app/remote.tsx`,
`app/auth/magic-link.tsx`, `components/shell/*`, `components/auth/auth-screen.tsx`,
`components/assistant-ui/*` (+ `composer/*`), `constants/theme.ts`, `hooks/theme-provider.tsx`,
`hooks/use-theme.ts`, `hooks/use-design-tokens.ts`, `lib/dialogs.tsx`, `src/components/{ui,icons,overlays}/*`,
`src/data/*`, `components/settings/*`, `components/pet/pet-mini-assistant.tsx`.

Метод: полный перебор импортов (скрипт резолвит каждый `@/…` и относительный путь к файлу) +
точечная сверка именованных экспортов. Проверка на «красные» тач-цели — по `StyleSheet`-константам
(ниже 44×44 без `hitSlop`).

---

## 1. Сломанные импорты / ссылки после удаления файлов

**Вывод: битых импортов НЕТ.** Рефакторинг полностью перевёл ссылки на новые модули.

| Удалённый файл | Что было | Что теперь | Статус |
|---|---|---|---|
| `components/assistant-ui/composer.tsx` | монолитный композер | `components/assistant-ui/composer/index.tsx` (экспортирует `Composer`) | ✅ `thread.tsx:22` `import { Composer } from "@/components/assistant-ui/composer"` резолвится в `composer/index.tsx` |
| `components/ui/icon.tsx`, `components/ui/icon.ios.tsx` | старый Icon | `src/components/icons/Icon.tsx` + `components/ui/icon-mappings.ts` (back-compat alias `IconName`) | ✅ ни одного оставшегося `@/components/ui/icon` / `icon.ios` импорта; все `IconName`-потребители (`settings-row`, `surface-boundary`, `EmptyState`, `Chip`, `ListItem`, `PillButton`, `Icon`, `src/data/*`) импортируют `icon-mappings` |
| `components/thread-list/drawer-content.tsx`, `components/thread-list/thread-list-item.tsx` | старый drawer | `src/components/overlays/Sidebar.tsx` + `DrawerContentAdapter.tsx` + `src/data/*` | ✅ единственная ссылка на drawer — `_layout.tsx:85` `drawerContent={(props) => <DrawerContentAdapter {...props} />}`, адаптер живёт в `src/components/overlays/DrawerContentAdapter.tsx` |

Дополнительно сверены именованные экспорты: `Composer` (`composer/index.tsx:24`),
`DrawerContentAdapter`, `Icon`, `MessageBubble`, `parseEstimateEditorWidget`,
`parseEstimateGenerationActivity`, `DATA_PART_NAMES` — все на месте. Скрипт-резолвер вернул
`Total missing: 0`.

⚠️ Примечание (не баг, но хрупко): путь `@/components/assistant-ui/composer` теперь работает
только благодаря резолву директории → `index.tsx` (Metro). Если в `composer/` позже появится
файл `composer.tsx`-аналог рядом с index, приоритет может измениться.

---

## 2. Тач-цели < 44px

Красная линия 44×44 по Apple HIG / Material. Считаю «красным» только то, у чего нет `hitSlop`,
компенсирующего размер.

| # | file:line | элемент | фактический размер | sev |
|---|---|---|---|---|
| T1 | `components/shell/mobile-header.tsx:227-232` | `capsuleButton` («Переименовать», «Ещё действия» в шапке чата) | `height:34, width:34`, без hitSlop | **med** |
| T2 | `components/assistant-ui/thread.tsx:276-283` | `scrollToBottom` (плавающая «вниз») | `height:32, width:32`, без hitSlop | **med** |
| T3 | `components/assistant-ui/message-action-bar.tsx:48` | `button` (Copy / Reload под ответом) | `padding:8` + иконка 17 ⇒ ≈33×33 | **med** |
| T4 | `components/assistant-ui/message.tsx:365-371` | `suggestion` (чипы «Варианты продолжения») | `paddingVertical:8` + текст 13 ⇒ ≈33 | **med** |
| T5 | `src/components/ui/ChipsRow.tsx:59` | `chip` (выбор раздела/ед.изм. в смете) | `minHeight:40` | **med** |
| T6 | `components/assistant-ui/composer/styles.ts:36-40` | `attachmentRemove` (крестик удаления вложения) | `height:22, width:22` | **med** |
| T7 | `components/settings/native-billing-settings.tsx:536` | `payButton` («Оплатить») | `height:42` | **low** |
| T8 | `components/settings/native-billing-settings.tsx:475` | `retry` | `minHeight:40` | **low** |
| T9 | `components/assistant-ui/model-selector.tsx:375` | `retry` в модалке моделей | `minHeight:38` | **low** |
| T10 | `components/assistant-ui/model-selector.tsx:331` | `label`-вариант селектора модели | `minHeight:30` + `hitSlop:6` ⇒ ≈42 | **low** |
| T11 | `lib/dialogs.tsx:416` | `promptButton` («Сохранить»/«Отмена» промпта) | `minHeight:40` | **low** |
| T12 | `components/assistant-ui/composer/attachments.tsx:21-23` | `plusStyles.button` («вложение») | `32×32` + `hitSlop:6` ⇒ ≈44 (на грани) | **low** |
| T13 | `components/pet/pet-mini-assistant.tsx:462,492` | `petChoice` / `send` питомца | `40×40` | **low** — компонент сейчас НЕ смонтирован (см. §6) |

Погранично-нормально (не считаю багом): `CircleButton` `size:40 + hitSlop:4` ⇒ ≈48;
`model-selector` `pill minHeight:34 + hitSlop:6` ⇒ ≈46; `MicButton` `40 + hitSlop:6` ⇒ ≈52.

**Предложение фикса (общее):** для T1–T6 поднять до `minHeight/minWidth:44` (или `hitSlop`
до суммарных 44); для `attachmentRemove` — `hitSlop` минимум 11 по каждой оси либо увеличить
визуально до 32 и добавить hitSlop.

---

## 3. Safe-area (вырез/чёлка, home indicator)

Положительное (зафиксировано, чтобы не чинить): `app/index.tsx:29-33`, `native-screen-shell.tsx:19-22`,
`auth-screen.tsx:120-122` используют `SafeAreaView edges={["top","bottom"]}`; `Sidebar.tsx:259-260,281-282`
сам добавляет `paddingTop: insets.top`, `paddingBottom: max(insets.bottom, md)`. `SafeAreaProvider`
есть — его ставит `expo-router` (`ExpoRoot.js` оборачивает корень в `SafeAreaProvider`), так что
`useSafeAreaInsets()` в Sidebar/TotalBar валиден.

| # | file:line | проблема | sev |
|---|---|---|---|
| S1 | `src/components/ui/TotalBar.tsx:26` | `marginBottom: Math.max(insets.bottom, Spacing.md)` **дублирует** нижний inset: `TotalBar` рендерится внутри `NativeScreenShell` (уже `SafeAreaView edges bottom`), который уже прибавил `paddingBottom = insets.bottom`. Итог — панель «Итого / Добавить позицию» в редакторе сметы всплывает на ~2×inset выше home indicator. | **med** |
| S2 | `app/auth/magic-link.tsx` (весь экран) | нет `SafeAreaView` и нет кнопки «назад»: при невалидной ссылке (`missing`/`error`) пользователь на дед-энде без навигации (см. D3). | **low** |
| S3 | `components/pet/pet-mini-assistant.tsx:345-347,361-364` | жёсткие `bottom:70` / `bottom:68` без `insets.bottom` — на устройствах с большим home indicator перекроет композер. Компонент сейчас не смонтирован (§6), фикс актуален при его возврате. | **low** |

---

## 4. Контраст / видимость

| # | file:line | проблема | sev |
|---|---|---|---|
| C1 | `src/components/ui/PillButton.tsx:71,77,124-126` | **Невидимая подпись в disabled-состоянии.** Текст (`color: disabled ? colors.disabled : …`, стр. 77) и иконка (стр. 71) получают `colors.disabled`, а фон кнопки — тот же `backgroundColor: colors.disabled` (стр. 124). `disabled` = `#b0ada7` (light) / `#5f5e5a` (dark) — текст и фон совпадают ⇒ кнопка выглядит пустой серой пилюлей. Затрагивает главный CTA «Сохранить» и «Поделиться» в редакторе сметы (`app/estimates.tsx:626,632`), когда они неактивны. | **high** |
| C2 | `constants/theme.ts:60` | `placeholder: "#8a8780"` на фоне `#fafaf7` ≈ 3.2:1 — ниже AA 4.5:1 для плейсхолдеров инпутов (`Field`, `Composer`, поиск в проектах). Плейсхолдеры формально exempt, но 3.2:1 на мелком тексте читается тяжело. | **low** |

---

## 5. Overflow / геометрия

| # | file:line | проблема | sev |
|---|---|---|---|
| O1 | `app/_layout.tsx:95` vs `src/components/overlays/Sidebar.tsx:103` | Рассогласование ширины drawer. Drawer: `width: Math.min(width * Layout.drawerFraction, 340)` (кап 340). Sidebar: `width = Dimensions.get("window").width * Layout.drawerFraction` (без капа, `drawerFraction:0.74`). При ширине окна > ~459px (iPad portrait, телефон в landscape, web < 959px) Sidebar рендерится шире drawer (например 568 vs 340), а `drawerStyle` имеет `overflow:"hidden"` (стр. 94) ⇒ правый край меню обрезается. | **med** |
| O2 | `components/settings/settings-row.tsx` (стиль `title: flexShrink: 0`) | Заголовок строки не сжимается; при длинном `title` + `value` + chevron возможен выезд за экран (нет `maxWidth`/ellipsis-ограничения у самого title). Сейчас замаскировано короткими лейблами. | **low** |

---

## 6. Мёртвые / нерабочие кнопки

| # | file:line | проблема | sev |
|---|---|---|---|
| D1 | `src/components/overlays/Sidebar.tsx:161-167` | Кнопка «Поиск» в шапке drawer не имеет `onPress` — `<CircleButton accessibilityLabel={COPY.searchLabel} size={48} variant="muted">` без обработчика. Тап ничего не делает (визуально полноценная кнопка с иконкой лупы). | **med** |
| D2 | `app/estimate/[projectId].tsx:46` и `:69` | `onBack={() => undefined}` — кнопка «назад» в состояниях «нет доступа» и «загрузка/ошибка» мёртвая. | **high** |
| D3 | `app/estimate/[projectId].tsx` (весь flow закрытия) | Дед-энд: после открытия сметы рендерится `EstimateEditor`; его `onClose` делает `setEstimate(null)` ⇒ экран возвращается в ветку загрузки, но `useEffect(open)` не перезапускается (`open` стабилен), спиннер крутится вечно, а `onBack` в этой ветке = `undefined` (D2). Пользователь заперт на экране сметы (из Library/диплинка). | **high** |
| D4 | `components/pet/pet-mini-assistant.tsx:177` | `PetMiniAssistant` определён, но нигде не импортируется/не монтируется (`grep` по проекту даёт только строку экспорта). Либо «забыли подключить» после рефакторинга, либо мёртвый код — уточнить у владельца; при возврате в разметку активируются T13 и S3. | **low** |

---

## 7. Итоговый severity-ранжированный список

**high**
1. `app/estimate/[projectId].tsx:46,69` — мёртвый `onBack={() => undefined}` + дед-энд: закрытие редактора → вечный спиннер без навигации (D2, D3).
2. `src/components/ui/PillButton.tsx:71,77,124` — невидимая подпись disabled-кнопки (текст == фон), ломает CTA «Сохранить»/«Поделиться» (C1).

**med**
3. `components/shell/mobile-header.tsx:227-232` — кнопки шапки 34×34 (T1).
4. `components/assistant-ui/thread.tsx:276-283` — «вниз» 32×32 (T2).
5. `components/assistant-ui/message-action-bar.tsx:48` — Copy/Reload ≈33px (T3).
6. `components/assistant-ui/message.tsx:365-371` — suggestion-чипы ≈33px (T4).
7. `src/components/ui/ChipsRow.tsx:59` — чипы раздела/ед.изм. 40px (T5).
8. `components/assistant-ui/composer/styles.ts:36-40` — крестик вложения 22×22 (T6).
9. `src/components/overlays/Sidebar.tsx:161-167` — мёртвая кнопка «Поиск» (D1).
10. `app/_layout.tsx:95` + `Sidebar.tsx:103` — рассогласование ширины drawer, обрезка на планшетах/landscape (O1).
11. `src/components/ui/TotalBar.tsx:26` — двойной bottom inset (S1).

**low**
12. `components/settings/native-billing-settings.tsx:536` — payButton 42px (T7).
13. `components/settings/native-billing-settings.tsx:475` — retry 40px (T8).
14. `components/assistant-ui/model-selector.tsx:375` — retry 38px (T9).
15. `components/assistant-ui/model-selector.tsx:331` — label ≈42px (T10).
16. `lib/dialogs.tsx:416` — promptButton 40px (T11).
17. `components/assistant-ui/composer/attachments.tsx:21-23` — вложение 32×32 на грани (T12).
18. `app/auth/magic-link.tsx` — нет safe-area и нет «назад» при ошибке (S2, D3-смежно).
19. `constants/theme.ts:60` — placeholder 3.2:1 (C2).
20. `components/settings/settings-row.tsx` — `title: flexShrink:0`, риск overflow (O2).
21. `components/pet/pet-mini-assistant.tsx:177` — несмонтированный компонент (D4) + его 40×40 (T13) и `bottom:70` без inset (S3).

---

### Рекомендуемый порядок правок (минимальный diff)
1. D2/D3 — дать `estimate/[projectId].tsx` рабочий `onBack` (`router.replace("/estimates?client=mobile")` или `canGoBack()`) и перезапуск `open`/`onClose`-обработку, не уводящую в вечный спиннер.
2. C1 — в `PillButton` disabled-текст сделать `colors.mutedForeground` (или отдельный токен), не совпадающий с фоном.
3. T1–T6 + S1 + O1 + D1 — точечные `hitSlop`/размеры, убрать двойной inset в `TotalBar`, выровнять ширину Sidebar с drawer, повесить `onPress` (или убрать) кнопке поиска.
