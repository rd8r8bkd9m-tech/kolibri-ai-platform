# Visual Preview Live Report

Дата среза: 2026-06-29 07:49 MSK  
Агент: `Визуальный QA SPA/PWA`  
Область: текущая документация, package scripts, live frontend routes `/` и
`/app`. Код не редактировался.

## 1. Текущий live status

| Контур | URL / команда | Статус сейчас | Вывод для QA |
| --- | --- | --- | --- |
| Vite dev landing | `http://127.0.0.1:5173/` | `200 OK` | Открывать сейчас для visual pass лендинга. |
| Vite dev app | `http://127.0.0.1:5173/app` | `200 OK` | Открывать сейчас для chat-first SPA pass. |
| Manifest | `http://127.0.0.1:5173/manifest.webmanifest` | `200 OK` | PWA manifest доступен в dev preview. |
| Backend API | `http://127.0.0.1:8000/api/providers` | connection refused | Live API/chat/factory checks заблокированы до подъема backend. |
| Production-like preview | `http://127.0.0.1:4173/` | connection refused | Build/preview pass сейчас не открыт. |

Owner-facing URLs, которые должны быть открыты сейчас:

- Landing: `http://127.0.0.1:5173/`
- App: `http://127.0.0.1:5173/app`

Если владельцу нужен только визуальный smoke без живого backend, эти два URL
достаточны. В отчете обязательно пометить: `backend intentionally not running`
или `backend unavailable`, иначе console/network errors по `/api/*` и `/ws/chat`
будут выглядеть как незакрытый blocker.

## 2. Package scripts

`frontend/package.json` безопасно прочитан. Доступные scripts:

```json
{
  "dev": "vite",
  "build": "vite build",
  "lint": "eslint .",
  "preview": "vite preview",
  "test:mobile-layout": "node tests/mobile_layout_guard.mjs"
}
```

Команды для проверки:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173
```

Backend для live API/chat/factory status:

```bash
cd backend
KOLIBRI_DB_PATH=/tmp/kolibri-browser-preview.db python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## 3. Текущая карта frontend routes

В проекте нет отдельного `react-router` route table. Текущий route switch живет
в `frontend/src/App.jsx`:

- `routePath` инициализируется из `window.location.pathname`.
- `isLanding = routePath === "/" || routePath === ""`.
- `/` рендерит `LandingShell`.
- `/app` рендерит рабочий `AppHeader` + `ChatWorkspace`.
- Любой не-root path сейчас попадает в app shell, потому что условие отличает
  только `/` от остальных путей.
- CTA на лендинге вызывает `window.history.pushState({}, "", "/app")`, обновляет
  `routePath` и фокусирует composer.
- `popstate` обновляет `routePath`, поэтому browser back/forward должен
  переключать `/` и `/app` без перезагрузки.

Vite proxy настроен на backend:

- `/api` -> `http://localhost:8000`
- `/ws` -> `ws://localhost:8000`

Но `frontend/src/config.js` для local host обращается напрямую к
`http://127.0.0.1:8000` и `ws://127.0.0.1:8000`, поэтому при выключенном backend
ожидаем connection errors, а не proxy success.

## 4. Как проверить `/`

Открыть `http://127.0.0.1:5173/`.

Проверить визуально:

- `Kolibri AI` виден как главный first-viewport сигнал.
- Есть landing navigation, CTA `Открыть приложение` / `Начать в Kolibri`.
- Главный CTA переводит на `/app`, URL меняется без full reload, composer
  получает focus.
- Первый экран не является пустой заставкой: видны птица/product visual/chat
  preview и сигналы фабрики/PWA/Control.
- `Control` FAB доступен справа снизу и не перекрывает CTA.
- На 390 px и 360 px нет horizontal scroll, обрезанных русских строк и
  наложения nav/action buttons/product visual.
- Если backend не поднят, landing показывает degraded/offline status без белого
  экрана.

## 5. Как проверить `/app`

Открыть `http://127.0.0.1:5173/app`.

Проверить визуально:

- Видно именно рабочее chat-first приложение, без landing hero.
- Header показывает Kolibri, состояние подключения/фабрики, provider select и
  settings.
- Welcome/messages area читается на desktop и mobile.
- Composer закреплен снизу, placeholder и длинный русский ввод не ломают ширину.
- Send button не меняет размер между disabled/enabled/loading states.
- `Control` FAB не перекрывает composer/send button/safe area.
- Control Panel открывается и закрывается; tabs Billing, Documents, Search,
  Cluster, Settings переключаются без layout shift и обрезания.
- `Esc` закрывает Control Panel.
- При выключенном backend отправка сообщения должна дать понятную ошибку
  подключения, а не белый экран или зависший infinite loading.

## 6. Screenshots, которые нужны

Хранить как task artifact или во временной папке, не коммитить без отдельного
запроса.

Минимальный набор:

- `/` desktop `1440 x 1000`.
- `/app` desktop `1440 x 1000`.
- `/app` desktop `1440 x 1000` с открытым Control Panel.
- `/` mobile `390 x 844`.
- `/app` mobile `390 x 844`.
- `/app` mobile `390 x 844` с открытым Control Panel.
- DevTools Console на `/`.
- DevTools Console на `/app`.

Дополнительные viewport для overlap pass:

- `1024 x 768`
- `360 x 740`

Playwright helper, если нужен быстрый static capture:

```bash
mkdir -p /tmp/kolibri-browser-preview-qa/$(date +%Y%m%d-%H%M)
QA_DIR=$(ls -td /tmp/kolibri-browser-preview-qa/* | head -1)
npx -y playwright@latest screenshot --viewport-size=1440,1000 http://127.0.0.1:5173/ "$QA_DIR/landing-desktop-1440.png"
npx -y playwright@latest screenshot --viewport-size=1440,1000 http://127.0.0.1:5173/app "$QA_DIR/app-desktop-1440.png"
npx -y playwright@latest screenshot --viewport-size=390,844 http://127.0.0.1:5173/ "$QA_DIR/landing-mobile-390.png"
npx -y playwright@latest screenshot --viewport-size=390,844 http://127.0.0.1:5173/app "$QA_DIR/app-mobile-390.png"
```

Для Control Panel лучше сделать интерактивный browser pass, потому что нужно
сначала открыть FAB и переключить tabs.

## 7. Console и network checks

На `/` и `/app` открыть DevTools, включить `Disable cache`, перезагрузить.

Blocker console errors:

- `Uncaught`, `TypeError`, `ReferenceError`, React runtime error.
- Белый экран или ErrorBoundary вместо приложения.
- Failed chunk load.
- Missing `manifest.webmanifest`, `/kolibri.svg`, `/icons/icon-192.png`,
  `/icons/icon-512.png`, `/icons/apple-touch-icon.png`.
- 404 для `/app` в dev или production-like preview.
- Service worker install/update loop в non-local preview.
- Mixed content или CORS на ожидаемом live backend.
- Бесконечный поток одинаковых WebSocket/fetch errors без понятного degraded UI.

Допустимые errors только при visual-only pass без backend:

- `GET http://127.0.0.1:8000/api/providers` failed.
- `GET http://127.0.0.1:8000/api/factory/status` failed.
- `GET http://127.0.0.1:8000/api/billing/plans` failed.
- `WebSocket ws://127.0.0.1:8000/ws/chat` failed.

Даже при допустимых backend-offline errors SPA должна оставаться интерактивной.

## 8. Blockers

Текущие blockers:

- Backend `127.0.0.1:8000` не поднят: нельзя подтвердить live providers,
  billing plans, factory status, knowledge documents/search и `/ws/chat`.
- Production-like preview `127.0.0.1:4173` не поднят: нельзя подтвердить
  `vite build` artifacts, history fallback `/app`, service worker/PWA поведение
  после сборки.

Если dev server `5173` не поднят, blockers становятся жесткими:

- владелец не может открыть `/` и `/app`;
- нельзя сделать browser screenshots;
- нельзя проверить console/runtime errors;
- нельзя подтвердить route switch CTA `/` -> `/app`;
- нельзя проверить mobile overlap, Control FAB/Panel и sticky composer;
- отчет должен быть `NO-GO: frontend dev server unavailable`.

Минимальное снятие blocker по dev server:

```bash
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
curl -I --max-time 2 http://127.0.0.1:5173/
curl -I --max-time 2 http://127.0.0.1:5173/app
```

## 9. Рекомендуемый live verdict format

```text
Visual preview: GO / GO WITH EXCEPTION / NO-GO

URLs:
- /: http://127.0.0.1:5173/
- /app: http://127.0.0.1:5173/app

Server state:
- frontend dev 5173: pass/fail
- backend 8000: pass/fail/not required
- preview 4173: pass/fail/not run

Browser checks:
- landing visual: pass/fail
- app visual: pass/fail
- console: pass/fail, allowed backend-offline noise
- network: pass/fail
- mobile overlap: pass/fail
- Control FAB/Panel: pass/fail
- evidence: /tmp/... or artifact reference

Blockers:
- ...

Next action:
- ...
```
