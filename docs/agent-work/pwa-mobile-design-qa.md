# PWA mobile дизайн-QA

Дата: 2026-06-29  
Роль: `PWA mobile дизайн-QA`  
Область: Android/iOS PWA acceptance, light/system theme, manifest/meta,
safe areas, no-overlap, standalone mode, install/offline evidence. Код
приложения не редактировался.

## 1. Сверенные источники

| Файл | Что сверено |
| --- | --- |
| `frontend/index.html` | Manifest, apple/mobile meta, viewport `viewport-fit=cover`, theme colors, non-local service worker gate. |
| `frontend/public/manifest.webmanifest` | `name`, `short_name`, `start_url`, `scope`, `display: standalone`, portrait, 192/512 maskable icons. |
| `frontend/public/pwa-register.js` | Регистрация `/service-worker.js` со scope `/` после load. |
| `frontend/public/service-worker.js` | App shell cache, navigation fallback на `/`, static asset caching, исключение `/api` и `/ws`. |
| `frontend/src/App.css` | `safe-area-inset-*`, `100svh/100dvh`, sticky composer, FAB/control offsets, mobile bottom sheet, theme variables. |
| `frontend/tests/mobile_layout_guard.mjs` | Контрактные CSS-инварианты для mobile layout. |
| `frontend/src/hooks/useThemeMode.js` | `system/light/dark`, сохранение в `localStorage`, class на `<html>`, dynamic `theme-color`. |
| `frontend/src/hooks/usePwaStatus.js` | Статус `display-mode: standalone` / `navigator.standalone` и наличие service worker API. |

Ключевые anchors: `frontend/index.html:6-16`, `frontend/index.html:35-42`,
`frontend/public/manifest.webmanifest:7-24`, `frontend/public/service-worker.js:1-18`,
`frontend/public/service-worker.js:36-74`, `frontend/src/App.css:50-52`,
`frontend/src/App.css:86-102`, `frontend/src/App.css:489-493`,
`frontend/src/App.css:569-574`, `frontend/src/App.css:608-650`,
`frontend/src/App.css:923-948`, `frontend/tests/mobile_layout_guard.mjs:6-10`.

## 2. Acceptance gates

### Android PWA

Статус `PASS` только если:

- Chrome на Android видит installability: manifest доступен, service worker
  зарегистрирован, иконки 192/512 загружены, scope покрывает `/` и `/app`;
- install prompt или browser UI `Install app` появляется без DevTools errors;
- после установки приложение открывается отдельным standalone окном без address
  bar, `display-mode: standalone` становится `true`;
- launcher icon не обрезан, splash/background соответствует `theme_color` /
  `background_color`;
- back button не ломает `/` -> `/app` и не закрывает приложение неожиданно из
  рабочего экрана;
- offline reload показывает app shell, а не белый экран.

### iOS PWA

Статус `PASS` только если:

- Safari `Add to Home Screen` показывает название `Фабрика Колибри` и
  `apple-touch-icon` 180x180;
- Home Screen запуск открывается fullscreen/standalone, `navigator.standalone`
  становится `true`;
- `viewport-fit=cover` и safe areas защищают composer, Control FAB, bottom
  sheet и status/home indicator зоны;
- status bar в light/system теме не конфликтует с цветом header;
- mobile keyboard не перекрывает composer так, чтобы нельзя было отправить
  сообщение или закрыть Control Panel;
- offline повторный запуск после первой online загрузки показывает shell.

### Theme: light/system

Статус `PASS` только если:

- default theme = `system`, системная light scheme даёт `.theme-light`, dark
  scheme даёт `.theme-dark`;
- переключатели `Системная`, `Светлая`, `Тёмная` не меняют layout и сохраняют
  выбор в `localStorage`;
- `<meta name="theme-color">` обновляется в runtime: light `#f0f4f8`, dark
  `#0a0a0f`;
- manifest/base meta остаются согласованы с light theme;
- текст, controls, disabled states и focus ring читаются на 390 px и 360 px.

### Manifest и meta

Статус `PASS` только если:

- `manifest.webmanifest` валиден JSON и отдаётся с `200`;
- `display` = `standalone`, `start_url` = `/`, `scope` = `/`,
  `orientation` = `portrait`;
- есть PNG icons `192x192` и `512x512` с `purpose: any maskable`;
- `index.html` содержит manifest link, apple touch icon, Android/iOS mobile web
  app meta, two theme-color meta for light/dark, `format-detection=no`;
- `/app` в production preview отдаёт SPA fallback `200`, а не `404`.

### Safe areas и no-overlap

Статус `PASS` только если на `390x844`, `360x740`, `430x932`, `1440x1000`:

- нет horizontal scroll у `html/body`;
- composer sticky снизу, имеет bottom padding `composer gap + safe bottom`;
- Control FAB расположен выше composer и не закрывает send button;
- Control Panel на mobile открывается как bottom sheet, помещается в `88dvh` и
  имеет bottom padding с `safe-area-inset-bottom`;
- header, model select, settings button, quick actions, long Russian text,
  code/pre блоки и billing form не налезают друг на друга;
- landing first viewport начинается с brand/nav/hero, а не с прокрученного
  середины страницы;
- при offline/degraded backend UI остаётся интерактивным.

### Standalone mode

Статус `PASS` только если:

- Android installed app: `matchMedia("(display-mode: standalone)").matches`
  возвращает `true`;
- iOS Home Screen app: `navigator.standalone === true`;
- PWA status в Settings показывает `установлено`;
- route `/app` открывается напрямую в standalone и после reload остаётся в app
  shell;
- screenshots приложены из установленного режима, не только из browser tab.

### Install/offline evidence

Минимальный evidence-набор для release:

- Android: screenshot install prompt, screenshot launcher icon, screenshot
  standalone `/app`, screenshot offline reload;
- iOS: screenshot Add to Home Screen, screenshot Home Screen icon, screenshot
  standalone `/app`, screenshot safe-area/composer with keyboard;
- DevTools/Application evidence: service worker activated, cache
  `kolibri-ai-pwa-v1`, cached `/`, manifest, icons;
- network offline evidence: reload `/app` without network returns shell, `/api`
  and `/ws` are not cached as fake-success responses;
- short note with device/browser versions and exact URL.

Важно: локальный `http://localhost` / `http://127.0.0.1` preview не является
достаточным install/offline evidence для этого проекта, потому что
`frontend/index.html` намеренно не подключает `pwa-register.js` на этих host.
Нужен HTTPS/non-local preview или реальное устройство.

## 3. Текущий QA-срез

Вердикт текущего документального pass: `GO WITH EXCEPTIONS`.

Что подтверждено:

- `npm run test:mobile-layout` прошёл: `mobile layout guard passed`;
- manifest JSON guard прошёл: обязательные поля и 192/512 maskable icons есть;
- icons присутствуют: `apple-touch-icon.png` 180x180, `icon-192.png` 192x192,
  `icon-512.png` 512x512;
- `npm run build` прошёл, production bundle собран;
- production preview `127.0.0.1:4173` отдаёт `200` для `/`, `/app`,
  `/manifest.webmanifest`, `/service-worker.js`;
- static service worker guard прошёл: app shell cache, navigation fallback,
  `/api`/`/ws` skip и local SW disable найдены;
- Playwright CLI screenshots сохранены в
  `/tmp/kolibri-pwa-mobile-design-qa-20260629/`.

Ограничения и риски:

- реальная Android/iOS установка не проверялась в этом pass;
- offline activation не проверена в браузере, потому что local preview
  отключает service worker registration;
- Playwright screenshots `/` на desktop и mobile показывают страницу уже ниже
  hero/nav. Это design-QA риск для landing first viewport: нужно проверить и,
  если воспроизводится вручную, исправить авто-scroll к chat/workbench;
- Control Panel визуально не снималась в открытом состоянии, acceptance требует
  отдельного интерактивного mobile pass.

## 4. Повторяемые проверки

Из корня репозитория:

```bash
npm --prefix frontend run test:mobile-layout
npm --prefix frontend run build
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173
curl -I --max-time 5 http://127.0.0.1:4173/
curl -I --max-time 5 http://127.0.0.1:4173/app
curl -I --max-time 5 http://127.0.0.1:4173/manifest.webmanifest
curl -I --max-time 5 http://127.0.0.1:4173/service-worker.js
```

Manifest/icon guard:

```bash
node -e "const fs=require('fs'); const m=JSON.parse(fs.readFileSync('frontend/public/manifest.webmanifest','utf8')); if (m.display !== 'standalone') throw new Error('display'); if (!m.icons.some(i => i.sizes === '192x192' && i.purpose.includes('maskable'))) throw new Error('192'); if (!m.icons.some(i => i.sizes === '512x512' && i.purpose.includes('maskable'))) throw new Error('512'); console.log('manifest guard passed')"
file frontend/public/icons/apple-touch-icon.png frontend/public/icons/icon-192.png frontend/public/icons/icon-512.png
```

Screenshot smoke:

```bash
mkdir -p /tmp/kolibri-pwa-mobile-design-qa-20260629
npx --yes playwright@latest screenshot --viewport-size=390,844 http://127.0.0.1:4173/ /tmp/kolibri-pwa-mobile-design-qa-20260629/landing-mobile-390.png
npx --yes playwright@latest screenshot --viewport-size=390,844 http://127.0.0.1:4173/app /tmp/kolibri-pwa-mobile-design-qa-20260629/app-mobile-390.png
npx --yes playwright@latest screenshot --viewport-size=1440,1000 http://127.0.0.1:4173/ /tmp/kolibri-pwa-mobile-design-qa-20260629/landing-desktop-1440.png
npx --yes playwright@latest screenshot --viewport-size=1440,1000 http://127.0.0.1:4173/app /tmp/kolibri-pwa-mobile-design-qa-20260629/app-desktop-1440.png
```

## 5. Release sign-off rule

Release sign-off по PWA/mobile можно ставить только после:

- текущие static guards и `test:mobile-layout` зелёные;
- нет воспроизводимого landing auto-scroll на first viewport;
- Android install/standalone/offline evidence приложен;
- iOS Home Screen/standalone/safe-area/offline evidence приложен;
- mobile Control Panel проверена открытой на 390 px и 360 px;
- все screenshots и device notes лежат в task artifacts или `/tmp`, но не
  коммитятся без отдельного запроса.
