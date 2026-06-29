# Premium UI Standard для Kolibri SPA/PWA и лендинга

Дата: 2026-06-29  
Роль: `premium_ui_director`  
Область: лендинг `/`, рабочее приложение `/app`, PWA-оболочка, Control FAB и Control Panel.

## 1. Северная звезда

Kolibri должен ощущаться как дорогой, спокойный и точный AI-инструмент для
прикладной работы: сметы, коммерческие предложения, документы, поиск по базе,
оплата, статус фабрики и мобильный доступ. Основная рабочая поверхность всегда
chat-first: пользователь начинает с диалога, а вторичные операции открывает
через `Контрол`.

Премиум здесь не означает больше декора. Премиум означает:

- ясную иерархию;
- отсутствие визуального шума;
- уверенную типографику;
- предсказуемые состояния;
- быстрое ощущение отклика;
- отсутствие overlap на русских строках;
- аккуратную PWA-посадку на iOS/Android;
- брендового персонажа, который помогает понимать состояние системы.

## 2. Архитектура экранов

### `/` landing

Лендинг отделен от рабочего приложения. Он продает доверие, сценарии и продукт,
но не имитирует рабочий чат внутри декоративной обложки.

Первый viewport обязан показывать:

- имя продукта `Kolibri AI` как главный сигнал, не только в навигации;
- реальный продуктовый визуал: скрин/рендер интерфейса, живую птицу Kolibri или
  скомпонованный product shot, а не абстрактный градиент;
- один главный CTA: `Открыть приложение` или `Начать в Kolibri`;
- вторичный CTA: `Посмотреть возможности`, `Тарифы` или `Связаться`;
- намек на следующий блок ниже fold на desktop и mobile.

Структура лендинга:

1. Hero: продукт, ценность, CTA, доверительные микро-сигналы.
2. Workflow: чат -> документы/поиск/сметы -> Control -> результат.
3. Возможности: документы, поиск, биллинг, фабрика, PWA.
4. Применение: строительство, КП, сметы, база знаний, команда.
5. Mobile/PWA: установка на экран, offline shell, быстрый доступ.
6. Trust: прозрачные статусы, платежи, роли, безопасность без громких обещаний.
7. Финальный CTA.

### `/app` chat-first SPA

Рабочее приложение открывается сразу в usable-состоянии. Не должно быть
маркетингового экрана, hero-секции или лендингового вступления внутри `/app`.

Иерархия `/app`:

- Header: Kolibri, состояние подключения/фабрики, выбор модели, настройки.
- Messages: основной поток работы.
- Welcome state: короткая продуктовая подсказка и быстрые действия.
- Composer: главный рабочий контрол, закреплен внизу.
- Control FAB: вторичный вход в плагины.
- Control Panel: биллинг, документы, поиск, кластер, настройки.

Основное действие: отправить сообщение. Все остальное вторично и не должно
соревноваться с composer.

## 3. Visual Principles

### Характер

Kolibri визуально должен быть:

- спокойным, не игровым;
- технически точным, но не холодным;
- светлым по умолчанию;
- премиальным за счет воздуха, качества деталей и состояния компонентов;
- достаточно плотным для ежедневной работы.

### Палитра

Базовый подход: нейтральные поверхности + один главный акцент + ограниченные
семантические цвета.

Рекомендуемый контракт:

- фон: холодный светлый нейтрал, не чисто белый;
- поверхность: белая/почти белая с мягкой границей;
- текст primary: темный slate;
- text secondary/muted: два стабильных уровня;
- accent: cyan/sky для Kolibri и интерактивных элементов;
- secondary accent: violet только как тонкая поддержка бренда;
- success/warning/error: зеленый, янтарный, красный только по смыслу.

Запрещено:

- доминирующая одноцветная синяя/фиолетовая заливка всего интерфейса;
- декоративные blobs/orbs/bokeh как основа премиум-ощущения;
- тяжелые темные градиенты на лендинге, если продукт нельзя рассмотреть;
- новые one-off hex-цвета вне CSS tokens без причины.

### Поверхности

Glass можно использовать только как функциональный слой: header, composer,
FAB, легкие панели. Glass не должен ухудшать читаемость и не должен превращать
весь интерфейс в туманный фон.

Карточки допустимы для повторяемых сущностей: тарифы, документы, ноды,
результаты поиска. Не вкладывать карточку в карточку. Секции страницы должны
быть full-width bands или обычные constrained layouts, а не набор плавающих
декоративных плиток.

### Иконки и визуальные маркеры

Для инструментов использовать знакомые иконки. Текст на кнопке добавлять там,
где команда должна быть явной: `Контрол`, `Отправить`, `Оплатить`, `Загрузить`.
Незнакомые иконки требуют `title`/tooltip и доступного имени.

Птица Kolibri - продуктовый персонаж и state indicator, не украшение. Ее
состояния должны отражать приложение: idle, listening, thinking, working,
success, warning, error, offline.

## 4. Layout Standard

### Общая сетка

Desktop:

- основной content max-width лендинга: 1120-1200px;
- рабочий чат: сообщения до 720-768px, composer до 768px;
- header высотой около 56px;
- минимальные поля страницы: 24px, на широких экранах 32-48px.

Tablet:

- content max-width: 720-880px;
- Control Panel может оставаться floating panel, если есть место;
- landing hero перестраивается в один поток без split-card ощущения.

Mobile:

- минимальная ширина QA: 360px;
- поля: 16px;
- controls touch target не меньше 44px;
- `100dvh`/`100svh` + safe areas обязательны;
- composer не перекрывается клавиатурой и Control FAB;
- Control Panel становится bottom sheet.

### `/app` layout

Header:

- слева Kolibri + статус;
- справа выбор модели и settings;
- не добавлять туда большие CTA, промо или навигационный шум.

Messages:

- пользовательские сообщения справа, assistant слева;
- длинные русские строки переносятся без горизонтального overflow;
- code/pre имеют горизонтальный scroll внутри bubble;
- loading/streaming не меняют ширину layout;
- empty state содержит только 3-4 быстрых действия.

Composer:

- закреплен визуально внизу рабочей зоны;
- высота textarea растет ограниченно;
- send button стабилен по размеру;
- focus state заметен, но не кричит;
- mobile font-size не меньше 16px, чтобы iOS не зумил input.

Control FAB:

- fixed справа снизу, выше composer;
- desktop: 48px height, label `Контрол`, icon слева;
- mobile: 44px height, compact padding;
- учитывает `env(safe-area-inset-right)` и `env(safe-area-inset-bottom)`;
- не перекрывает composer, send button, toast или системную home indicator area;
- open state меняет акцент и сохраняет читаемость.

Control Panel:

- desktop: floating panel справа снизу, width около 430px;
- mobile: bottom sheet, max-height до 88dvh;
- scrim затемняет, но не делает фон полностью черным;
- tabs горизонтально скроллятся без обрезания текста;
- close доступен мышью, touch, Escape;
- фокус не теряется внутри панели;
- плагины имеют одинаковые состояния: loading, empty, error, success.

## 5. Typography

Базовые шрифты:

- UI: Inter или системный sans fallback;
- code/data: JetBrains Mono или системный monospace.

Принципы:

- без отрицательного letter-spacing;
- русские строки тестировать на переносы;
- hero-scale type только на лендинге и welcome state;
- компактные панели используют компактные заголовки, не hero-шрифты;
- uppercase использовать редко: labels, badges, metadata.

Рекомендуемая шкала:

| Роль | Desktop | Mobile | Weight | Line-height |
| --- | ---: | ---: | ---: | ---: |
| Landing H1 | 56-72 | 36-44 | 750-800 | 1.0-1.08 |
| Landing H2 | 32-44 | 26-32 | 700-750 | 1.12 |
| App welcome H1 | 28-32 | 22-26 | 750-800 | 1.12 |
| Panel H3 | 16-18 | 16 | 700-750 | 1.2 |
| Body | 15-16 | 15-16 | 400-500 | 1.55-1.7 |
| Metadata | 11-13 | 11-13 | 500-700 | 1.25-1.4 |
| Code | 13-14 | 12-13 | 400-500 | 1.5 |

## 6. Motion Standard

Motion должен помогать понять состояние, а не развлекать сам по себе.

Базовые правила:

- использовать Framer Motion для входов/выходов и микро-интеракций;
- hover/tap scale для кнопок: 0.96-1.04;
- panel open/close: 160-220ms;
- subtle fade/translate: 120-240ms;
- spring допустим для птицы и welcome, но без bounce-эффекта в рабочих панелях;
- shimmer/skeleton только во время загрузки;
- статусные pulse/spinner должны быть тихими.

Обязательно:

- поддерживать `prefers-reduced-motion`;
- reduced motion убирает декоративное движение, но оставляет мгновенную смену
  состояний;
- не анимировать layout так, чтобы composer или FAB прыгали;
- не запускать бесконечные анимации возле текста, который пользователь читает.

Живая птица:

- idle: редкие микродвижения;
- listening: мягкое внимание к composer;
- thinking/working: заметное, но спокойное ожидание;
- success: короткая положительная реакция;
- error/offline: понятное состояние без драматизации.

## 7. Responsive и Safe Area

Минимальные контрольные viewport:

- 360x740 mobile;
- 390x844 iPhone;
- 768x1024 tablet;
- 1024x768 compact desktop/tablet landscape;
- 1440x900 desktop;
- 1920x1080 wide desktop.

Проверять:

- нет горизонтального scroll у страницы;
- нет overlap между FAB, composer, bottom sheet и системными safe areas;
- header не сжимает model select до нечитаемости;
- длинные названия документов/моделей/тарифов получают ellipsis или wrap;
- tab row в Control скроллится;
- landing hero оставляет намек на следующий блок;
- клавиатура на mobile не ломает composer;
- `100svh`/`100dvh` используются для устойчивой высоты.

## 8. PWA Standard

Kolibri должен быть installable SPA/PWA на Android и iOS Home Screen.

Manifest:

- `name`: Kolibri AI;
- `short_name`: Kolibri;
- `lang`: `ru`;
- `display`: `standalone`;
- `scope`: `/`;
- `start_url`: для production должен вести в ожидаемую точку входа; если
  landing остается на `/`, CTA ведет в `/app`;
- `theme_color` и `background_color` совпадают с премиальной оболочкой;
- icons 192/512 maskable проверены на Android launcher и iOS icon crop.

Service worker:

- offline shell открывается без сети;
- static assets кешируются без ломания обновлений;
- network/API failures показывают понятное состояние, не белый экран;
- новая версия приложения не должна зависать на старом stale UI без сигнала.

iOS/Android:

- safe area bottom/right/left учтены;
- standalone mode не прячет критичные controls;
- install-поток не должен быть единственным способом использовать продукт;
- PWA status можно показывать в Control -> Settings.

## 9. Landing `/` Detailed Spec

Hero:

- H1: `Kolibri AI` или буквальное продуктовое обещание рядом с брендом;
- subtitle: конкретно про сметы, КП, документы и чат;
- primary CTA ведет в `/app`;
- visual: продуктовый screenshot, bird/product composition или реальный
  интерфейс в устройстве;
- фон не должен скрывать продуктовый visual;
- hero не занимает 100% высоты намертво: следующий блок должен быть виден.

Navigation:

- 4-5 пунктов максимум;
- sticky допустим, но без тяжелой тени;
- CTA справа на desktop, в меню/нижней зоне на mobile.

Sections:

- каждая секция отвечает на один вопрос;
- карточки только для повторяемых возможностей/кейсов;
- не использовать крупные декоративные SVG, если можно показать продукт;
- trust-блоки должны быть конкретными: PWA, Control, документы, платежи,
  фабрика, статус.

Copy tone:

- уверенный русский язык;
- меньше "революционный", больше "быстро собрать КП", "найти документ",
  "видеть статус";
- никаких длинных объяснений внутри UI-контролов.

## 10. `/app` Detailed Spec

Welcome state:

- показывает Kolibri, короткую строку ценности и 3-4 действия;
- quick actions не должны превращаться в dashboard;
- действие `Подписка` открывает Control -> Billing, а не уводит из чата.

Chat:

- streaming assistant bubble появляется сразу;
- ошибка соединения оформляется как message state;
- provider badge вторичен и не спорит с текстом;
- thinking block раскрывается по желанию, по умолчанию не захламляет ответ.

Documents/Search/Billing/Cluster:

- живут в Control Panel;
- не открывают отдельные full-screen маршруты без причины;
- имеют compact layout;
- статусы видны словами и цветом;
- кнопки действий используют один стиль primary/secondary.

Settings:

- тема: system/light/dark;
- PWA status;
- будущие настройки не должны вытеснять основные plugin tabs.

## 11. Accessibility

Обязательный минимум:

- contrast body text не ниже WCAG AA;
- focus visible на всех интерактивных элементах;
- keyboard path: header -> chat -> composer -> FAB -> panel -> close;
- Escape закрывает Control Panel;
- touch targets 44px на mobile;
- `aria-label` для icon-only кнопок;
- `title` не заменяет полноценное accessible name, если кнопка без текста;
- reduced motion;
- ошибки не только цветом, но и текстом.

## 12. Performance

Цели:

- initial app shell ощущается мгновенным;
- landing visual оптимизирован, не блокирует CTA;
- анимации держат 60fps на обычном mobile;
- SVG/персонаж не раздувает bundle без пользы;
- изображения: responsive sizes, lazy load ниже fold;
- no layout shift у hero, composer, Control Panel.

## 13. Implementation Contract

При будущих правках:

- не вводить новую визуальную систему параллельно текущим CSS tokens;
- использовать существующие переменные `--bg-*`, `--text-*`, `--accent`,
  `--radius-*`, `--shadow-*`;
- новые цвета сначала добавлять как токены;
- поддерживать light/system/dark;
- любые новые панели Control оформлять через общий plugin pattern;
- избегать одноразовой верстки;
- тестировать длинные русские строки;
- не менять GoMesh/Control Plane поведение ради визуального эффекта.

## 14. QA Checklist

### Visual QA

- [ ] `/` и `/app` визуально различаются: landing продает, app работает.
- [ ] Первый viewport лендинга показывает `Kolibri AI` и продуктовый visual.
- [ ] Hero не является абстрактным градиентом без продукта.
- [ ] В `/app` главным элементом остается chat composer.
- [ ] Control FAB находится справа снизу и не перекрывает composer.
- [ ] Control Panel выглядит как вторичный рабочий слой.
- [ ] Нет nested cards и декоративного шума.
- [ ] Палитра не стала one-note blue/purple.
- [ ] Тексты на русском не вылезают из кнопок, карточек, badges и tabs.

### Responsive QA

- [ ] 360x740: нет horizontal scroll.
- [ ] 390x844: composer, FAB и iOS safe area не конфликтуют.
- [ ] 768x1024: Control Panel usable, tabs читаются.
- [ ] 1024x768: header и model select не ломаются.
- [ ] 1440x900: чат не растянут на всю ширину.
- [ ] 1920x1080: landing сохраняет премиальную плотность, не пустеет.
- [ ] Mobile keyboard не перекрывает composer критично.
- [ ] Bottom sheet Control не выходит за 88dvh.

### Interaction QA

- [ ] Send disabled при пустом input.
- [ ] Loading/streaming видны без layout shift.
- [ ] Ошибка сети показывается внутри понятного состояния.
- [ ] Quick actions запускают prompt или открывают нужный Control tab.
- [ ] FAB hover/tap/open states различимы.
- [ ] Scrim закрывает panel кликом/tap.
- [ ] Escape закрывает Control Panel.
- [ ] Focus order предсказуемый.

### PWA QA

- [ ] Manifest валиден.
- [ ] Icons 192/512 загружаются и выглядят корректно maskable.
- [ ] Android Chrome предлагает установку или проходит Lighthouse installable.
- [ ] iOS Safari Home Screen открывает standalone shell.
- [ ] Offline shell не показывает белый экран.
- [ ] Service worker не ломает обновление новой версии.
- [ ] Theme/background color совпадают с UI.
- [ ] PWA status отображается в Control -> Settings.

### Accessibility QA

- [ ] Контраст body text, buttons, badges проходит WCAG AA.
- [ ] Все icon-only buttons имеют accessible name.
- [ ] Focus visible не обрезается border-radius/overflow.
- [ ] Reduced motion отключает декоративные движения.
- [ ] Status/error states имеют текст, не только цвет.
- [ ] Touch targets на mobile не меньше 44px.

### Performance QA

- [ ] Нет заметного CLS у hero, composer, messages и Control Panel.
- [ ] Анимации не просаживают FPS на mobile.
- [ ] Landing images имеют размеры/aspect-ratio.
- [ ] Ниже fold изображения lazy-loaded.
- [ ] Console без ошибок missing assets.
- [ ] Bundle не растет из-за одноразовых декоративных библиотек.

## 15. Definition of Done

Дизайн считается готовым к приемке, когда:

- `/` дает премиальное первое впечатление и ведет в `/app`;
- `/app` остается chat-first и usable без обучения;
- Control FAB и Control Panel работают как единый вторичный слой;
- PWA устанавливается и открывает стабильный shell;
- desktop/tablet/mobile проверены скриншотами;
- нет overlap, горизонтального overflow и нечитаемых русских строк;
- empty/loading/error/success states оформлены для всех критичных потоков.
