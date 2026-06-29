# Бриф дизайн-директора продукта для PR #46

Дата: 2026-06-29
Роль фабрики: `Дизайн-директор продукта`
Область: premium SPA/PWA, живая птица Kolibri, light/system theme, Control FAB/Panel, mobile PWA.
PR: [#46 `[codex] Factory autonomy, PWA billing, remote FormulaLM`](https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform/pull/46)
Ветка: `codex/factory-autonomy-pwa-billing`, база: `main`, статус на момент брифа: draft, `mergeStateStatus=UNSTABLE`.

## 1. Дизайн-позиция

PR #46 уже переводит продукт из монолитной SPA в компонентный chat-first React/Vite интерфейс с PWA-оболочкой, Control FAB, Control Panel, биллингом и темами. Дизайн должен подключаться не как отдельная "картинка сверху", а как контракт компонентов, состояний и QA-гейтов.

Основной принцип: `chat composer` остается главным рабочим действием, `Control` является вторичным слоем для подписок, документов, поиска, сети и настроек, а птица Kolibri показывает состояние продукта без перекрытия рабочих элементов.

Не вводить новую UI-библиотеку или параллельную дизайн-систему. Работать через текущие React-компоненты, CSS custom properties в `frontend/src/App.css`, Framer Motion и существующий plugin pattern в `frontend/src/plugins/controlPlugins.jsx`.

## 2. Какие дизайнерские роли нужны прямо сейчас

| Роль | Зачем нужна сейчас | Участие в PR #46 |
| --- | --- | --- |
| Product Design Director | Держит целостность premium SPA/PWA и принимает merge-ready состояние. | Ведет этот чеклист, классифицирует visual blockers P0/P1/P2, дает финальный design sign-off перед merge. |
| Design Systems / UI Designer | Приводит компоненты к единому visual contract: токены, spacing, radius, states, типографика. | Проверяет `App.css`, `AppHeader`, `ChatWorkspace`, `ControlPanel`, все Control plugin panels; запрещает one-off цвета/карточки/нестабильные размеры. |
| UX / Interaction Designer | Проверяет chat-first сценарий, composer, quick actions, Control flows и billing flow. | Проходит `/`, `/app`, отправку сообщения, открытие Control tabs, checkout fallback, empty/loading/error/success states. |
| Character Motion Designer | Отвечает за живую птицу как state indicator, а не декор. | Проверяет текущий SVG fallback (`KolibriBird`, `LivingKolibri`) и готовит Rive-state contract без блокировки текущего UI. |
| Mobile PWA Designer | Защищает mobile safe areas, keyboard, standalone mode и installability. | Проверяет 360/390/768 viewports, iOS/Android PWA, FAB/composer/bottom sheet overlap, offline shell. |
| Accessibility + Visual QA | Фиксирует evidence pack перед merge. | Делает screenshots, console checks, focus/keyboard/reduced-motion проверки и прикладывает результат в PR #46. |
| Product Copy / Russian UI Editor | Убирает длинные или рекламные строки, которые ломают русский UI. | Проверяет CTA, tabs, badges, billing copy, error copy и состояния сети/оплаты. |

Не нужны прямо сейчас: большой brand refresh, новая компонентная библиотека, отдельный dashboard-router, PixiJS/Rive runtime как обязательный dependency. Rive можно проектировать, но текущий merge не должен зависеть от canvas runtime.

## 3. Как роли участвуют в PR #46

1. Product Design Director открывает PR #46 как дизайн-review scope и заводит один общий comment thread с текущим статусом: `Design QA: pending / blocked / approved`.
2. Design Systems/UI Designer проверяет, что новые визуальные решения выражены через `--bg-*`, `--text-*`, `--accent`, `--radius-*`, `--shadow-*`, `--safe-bottom`, а не через случайные локальные стили.
3. UX Designer проходит основной happy path: landing -> app -> prompt -> thinking/response -> Control -> Billing/Settings -> обратно в chat.
4. Character Motion Designer валидирует state map птицы: `offline`, `thinking`, `listening`, `success`, `error`; расширенные состояния идут в backlog/Rive contract.
5. Mobile PWA Designer делает mobile evidence pack и отдельно подтверждает, что `Control FAB`, composer и bottom sheet не конфликтуют с safe area и keyboard.
6. Visual QA фиксирует блокеры в терминах `P0/P1/P2` и не дает design approval, пока P0/P1 без exception остаются открытыми.
7. Финальный design sign-off в PR #46 возможен только после зеленого frontend build/lint/mobile guard и приложенных screenshots.

## 4. UI-файлы, которые уже менялись

### В committed diff PR #46

PWA shell/assets:

- `frontend/index.html`
- `frontend/package-lock.json`
- `frontend/public/kolibri.svg`
- `frontend/public/manifest.webmanifest`
- `frontend/public/pwa-register.js`
- `frontend/public/service-worker.js`
- `frontend/public/icons/apple-touch-icon.png`
- `frontend/public/icons/icon-192.png`
- `frontend/public/icons/icon-512.png`

SPA architecture and tokens:

- `frontend/src/App.jsx`
- `frontend/src/App.css`
- `frontend/src/config.js`
- `frontend/src/hooks/usePwaStatus.js`
- `frontend/src/hooks/useThemeMode.js`
- `frontend/src/plugins/controlPlugins.jsx`

Shared/components:

- `frontend/src/components/AppHeader.jsx`
- `frontend/src/components/ErrorBoundary.jsx`
- `frontend/src/components/ui/Skeleton.jsx`

Chat:

- `frontend/src/components/chat/ChatWorkspace.jsx`
- `frontend/src/components/chat/ChatComposer.jsx`
- `frontend/src/components/chat/MessageList.jsx`
- `frontend/src/components/chat/QuickActions.jsx`
- `frontend/src/components/chat/ThinkingBlock.jsx`
- `frontend/src/components/chat/WelcomeState.jsx`

Control:

- `frontend/src/components/control/ControlFab.jsx`
- `frontend/src/components/control/ControlPanel.jsx`
- `frontend/src/components/control/BillingPanel.jsx`
- `frontend/src/components/control/ClusterPanel.jsx`
- `frontend/src/components/control/DocumentsPanel.jsx`
- `frontend/src/components/control/SearchPanel.jsx`
- `frontend/src/components/control/SettingsPanel.jsx`

### Локально поверх PR-ветки замечены дополнительные UI-правки

Эти файлы видны в рабочем дереве, но не все они обязательно уже входят в remote PR diff:

- изменены: `frontend/index.html`, `frontend/public/manifest.webmanifest`, `frontend/src/App.css`, `frontend/src/App.jsx`, `frontend/src/components/AppHeader.jsx`, `frontend/src/components/KolibriBird.jsx`, `frontend/src/components/chat/ChatComposer.jsx`, `frontend/src/components/chat/ChatWorkspace.jsx`, `frontend/src/components/control/ControlFab.jsx`, `frontend/src/components/control/ControlPanel.jsx`
- добавлены локально: `frontend/src/components/LandingShell.jsx`, `frontend/src/components/LivingKolibri.jsx`, `frontend/src/assets/landing-hero.png`

Дизайн-review должен явно отличать "уже в PR" от "локально подготовлено к следующему push", чтобы не принять непроверенный UI как merged state.

## 5. Acceptance criteria: premium SPA/PWA

- `/` и `/app` имеют разные роли: landing продает доверие и сценарии, `/app` сразу работает как chat-first продукт.
- Первый viewport landing показывает `Kolibri AI`, продуктовый интерфейс или живую птицу и CTA в `/app`; hero не является абстрактным градиентом без продукта.
- `/app` держит иерархию: header -> messages/welcome -> composer -> Control FAB -> Control Panel.
- Composer остается главным действием; FAB, header и welcome actions не конкурируют с отправкой сообщения.
- Empty, loading, streaming, error и success states есть у chat, billing, documents/search/cluster и settings.
- Русские строки не дают horizontal overflow; длинные названия документов, тарифов, моделей и статусов имеют wrap или ellipsis.
- Компоненты используют текущие CSS tokens и существующие React props; новые цвета сначала добавляются как токены.
- Нет nested cards ради декора; карточки используются только для повторяемых сущностей или framed tools.
- `prefers-reduced-motion` уважает пользователя; декоративные анимации не мешают чтению.
- Console без runtime errors, missing assets, failed chunk load, service worker loop и CORS noise на happy path.

## 6. Acceptance criteria: живая птица

- Текущий merge path обязан работать на SVG fallback: `KolibriBird` и `LivingKolibri` не требуют Rive/canvas для загрузки приложения.
- Птица отражает минимум состояния `idle`, `listening`, `thinking`, `success`, `error`, `offline`.
- `LivingKolibri` может слушать app events (`chat:focus`, `chat:send`, `network:offline`, `network:online`, future factory/billing events), но не должен становиться глобальным источником layout shift.
- В header размер птицы остается компактным; на landing она может быть выразительнее, но не перекрывает продуктовый visual.
- `aria-label`/`role="img"` есть в meaningful usage; декоративные будущие варианты должны быть `aria-hidden`.
- Reduced motion отключает бесконечные loops или резко снижает амплитуду.
- Offline/error states не используют агрессивную или тревожную анимацию.
- Будущий Rive runtime должен быть lazy-loaded и иметь SVG fallback при load error, low-power mobile, reduced motion и маленьких аватарах.

## 7. Acceptance criteria: light/system theme

- Светлая тема является premium default: нейтральные поверхности, читаемый slate text, ограниченный cyan/sky accent.
- `system` уважает `prefers-color-scheme` и сохраняет выбор пользователя через `localStorage` ключ `kolibri-theme`.
- Root class переключается между `theme-light` и `theme-dark`; новые компоненты не должны зависеть от прямых hard-coded светлых цветов.
- `meta[name="theme-color"]` синхронизируется с resolved theme.
- Settings panel показывает segmented control `Системная / Светлая / Тёмная` и понятный текущий resolved state.
- Контраст body text, badges, buttons и tabs проходит WCAG AA в светлой теме; dark theme не должен ломаться как побочный эффект.
- PWA `theme_color`/`background_color` совпадают с premium shell и не дают резкого flash на standalone launch.

## 8. Acceptance criteria: Control FAB и Control Panel

- `Control FAB` фиксирован справа снизу, учитывает `env(safe-area-inset-right)` и `env(safe-area-inset-bottom)`.
- На desktop FAB высотой около 48px, с иконкой и label `Контрол`; на mobile не ниже 44px touch target.
- FAB не перекрывает composer, send button, toast/error и системную home indicator area.
- Open state визуально отличается, но сохраняет читаемость и доступное имя.
- `ControlPanel` на desktop открывается как floating panel справа снизу; на mobile становится bottom sheet с `max-height <= 88dvh`.
- Tabs горизонтально скроллятся без обрезания текста.
- Закрытие работает через close button, scrim click/tap и Escape.
- Panel role/aria остаются dialog-friendly; focus path предсказуемый: header -> chat -> composer -> FAB -> panel -> close/tabs.
- Новые Control sections подключаются через `controlPlugins`, а не через разрозненный conditional UI в `App.jsx`.

## 9. Acceptance criteria: mobile PWA

- Минимальные viewport для acceptance: `360x740`, `390x844`, `768x1024`, `1024x768`, `1440x900`.
- Используются `100svh`/`100dvh`, `--safe-bottom`, sticky composer и stable bottom gaps.
- Mobile keyboard не перекрывает критически composer; textarea имеет `font-size >= 16px`.
- Control bottom sheet не выходит за viewport и не перекрывает composer в closed state.
- Manifest валиден: `lang=ru`, `display=standalone`, `scope=/`, icons `192/512` с `any maskable`.
- Service worker открывает offline shell без белого экрана и не кеширует `/api`/`/ws` как static.
- Android Chrome installability и iOS Home Screen standalone проверены скриншотами.
- Back/scroll behavior на mobile не создает page-level horizontal scroll.

## 10. Visual QA gates перед merge

Merge PR #46 нельзя считать готовым по дизайну без evidence pack.

Обязательные команды:

```bash
git status --short
git diff --check
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout
gh pr checks 46 --watch=false
```

Обязательные screenshots:

- `/` landing: desktop `1440x900`, mobile `390x844`.
- `/app` empty/welcome state: desktop `1440x900`, mobile `390x844`.
- `/app` после отправки сообщения: visible thinking/assistant state, no layout shift.
- Control Panel: Billing, Documents, Search, Cluster, Settings tabs.
- Theme: light, system-resolved-light, system-resolved-dark или dark fallback.
- Mobile PWA: `360x740`, `390x844`, `768x1024`; отдельно Control bottom sheet.
- Living bird: `idle`, `listening`, `thinking`, `success`, `error/offline`; reduced motion enabled.
- PWA/offline: standalone shell или browser offline shell, no white screen.

Blocker policy:

- P0: white screen, broken chat/composer, broken build, inaccessible Control, PWA stale/blank shell, secret in diff/log/screenshot, billing UI that can imply active subscription without confirmation.
- P1: mobile overlap between FAB/composer/panel, unreadable Russian text, missing accessible names on icon buttons, theme contrast failure, bird causing layout shift or covering work controls.
- P2: minor spacing/typography polish without overlap, non-critical hover polish, incomplete expressive bird state when SVG fallback remains clear.

Design sign-off format for PR #46:

```text
Design QA: APPROVED / BLOCKED / APPROVED WITH EXCEPTION
Commit:
Screenshots:
Commands:
P0:
P1:
P2:
Exceptions:
Owner:
```

## 11. Component compatibility rules

- Keep React/Vite implementation simple: functional components, hooks, props, CSS classes and existing Framer Motion usage.
- New design work should extend `AppHeader`, `ChatWorkspace`, `ChatComposer`, `ControlFab`, `ControlPanel`, plugin panels and `LivingKolibri`, not duplicate them.
- New Control capability must be a `controlPlugins` entry with a panel component and predictable context object.
- Do not move product state into presentational components except local UI state such as open/hover/transient animation.
- Do not introduce global DOM event contracts except where already used for bird/app status; future event contracts should be named and documented.
- Reserve stable dimensions for fixed-format controls: FAB, header buttons, composer send button, bird sizes, tabs, cards and bottom sheet.
- Every visual change must be testable by screenshot at desktop and mobile sizes before merge.

## 12. Current design decision

Design can participate in PR #46 immediately, but approval should remain blocked until:

- current failing PR checks are understood or green;
- frontend lint/build/mobile layout guard pass on the merge candidate;
- visual evidence pack is attached;
- local UI additions such as `LandingShell.jsx` and `LivingKolibri.jsx` are either pushed into PR #46 and reviewed, or explicitly excluded from the merge decision.
