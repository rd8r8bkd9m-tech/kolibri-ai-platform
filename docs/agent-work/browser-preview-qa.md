# Browser preview QA для Kolibri SPA/PWA

Дата: 2026-06-29  
Роль: `QA-ревизор browser preview`  
Назначение: дать владельцу и главным агентам короткий, повторяемый регламент,
как сразу смотреть frontend-изменения в браузере и фиксировать визуальные
доказательства без ожидания деплоя.

## 1. Цель проверки

Любое изменение лендинга, `/app`, PWA shell, Control FAB, Control Panel,
композера, живой птицы или мобильной раскладки должно быть видно владельцу в
браузере сразу после запуска локального dev server.

Browser preview не заменяет release QA из
`docs/agent-work/product-qa-pack.md`. Это быстрый owner-facing контур:

- открыть актуальный frontend без сборки и деплоя;
- проверить оба главных маршрута: `/` и `/app`;
- поймать console/runtime errors, overlap, horizontal overflow и mobile
  дефекты до передачи владельцу;
- приложить screenshots/video как visual evidence к отчёту агента.

## 2. Базовые URL

Dev server:

| Экран | URL | Что должен увидеть владелец |
| --- | --- | --- |
| Landing | `http://127.0.0.1:5173/` | Первый экран Kolibri AI, CTA в `/app`, продуктовый визуал, намёк на следующий блок. |
| App | `http://127.0.0.1:5173/app` | Chat-first рабочее приложение: header, messages/welcome state, composer, правый нижний `Control`. |

Production-like preview после `vite build`:

| Экран | URL | Когда использовать |
| --- | --- | --- |
| Landing | `http://127.0.0.1:4173/` | Проверка собранного bundle перед PR/release handoff. |
| App | `http://127.0.0.1:4173/app` | Проверка history fallback, assets, service worker/PWA поведения после сборки. |

Не использовать `file://frontend/index.html`: так ломаются Vite routing,
proxy, PWA и часть runtime-проверок.

## 3. Команды запуска

Из корня репозитория:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1 --port 5173
```

Если проверяется не только внешний вид, а live API/chat/factory status, в
отдельном терминале поднять backend:

```bash
cd backend
KOLIBRI_DB_PATH=/tmp/kolibri-browser-preview.db python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Vite уже проксирует `/api` и `/ws` на `localhost:8000`, поэтому frontend URL
остаётся `http://127.0.0.1:5173`.

Для проверки production-like сборки:

```bash
npm --prefix frontend run build
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173
```

Минимальный обязательный набор перед handoff:

```bash
npm --prefix frontend run lint --if-present
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout --if-present
```

## 4. Что смотреть на `/`

Landing должен отличаться от рабочего приложения и продавать доверие к
продукту. Проверить:

- `Kolibri AI` виден как главный first-viewport сигнал, не только в nav;
- главный CTA ведёт в `/app` и после клика фокус переходит к composer;
- есть вторичный CTA и видимый намёк на следующий блок ниже fold;
- продуктовый визуал/птица/интерфейс не выглядит как пустая абстрактная
  заставка;
- нет горизонтального overflow на 360-390 px;
- русские строки не обрезаются и не залезают на кнопки, nav, визуал или
  соседние блоки;
- `Control` остаётся доступен справа снизу и не перекрывает CTA.

## 5. Что смотреть на `/app`

`/app` остаётся рабочей chat-first поверхностью, без лендингового hero внутри.
Проверить:

- header показывает Kolibri, состояние подключения/фабрики, выбор модели и
  settings без визуального шума;
- welcome/messages зона читается на desktop и mobile;
- composer закреплён снизу, send button не меняет размер, placeholder и
  длинный русский ввод не ломают layout;
- `Control` находится справа снизу, учитывает safe-area и не перекрывает
  composer, send button, toast или home indicator;
- Control Panel открывается, закрывается, переключает Billing/Documents/Search/
  Cluster/Settings без layout shift и обрезанных tabs;
- offline/degraded backend state отображается как безопасное состояние, а не
  белый экран;
- focus states и keyboard navigation не теряются после открытия Control Panel.

## 6. Console и network checks

Открыть DevTools на `/` и `/app`, перезагрузить страницу с отключённым cache и
проверить Console/Network.

Блокеры:

- `Uncaught`, `TypeError`, `ReferenceError`, React runtime error или белый экран;
- failed chunk load, missing asset, broken `manifest.webmanifest`, missing icons
  192/512;
- mixed content, CORS error на ожидаемом live backend, service worker install
  loop;
- бесконечный поток одинаковых ошибок WebSocket/fetch без понятного degraded UI;
- 404 для `/app` в preview/build режиме.

Допустимо только в visual-only проверке без backend:

- сетевые ошибки `/api/*` или `/ws/chat`, если в отчёте явно написано
  `backend intentionally not running`;
- при этом UI всё равно не должен падать или зависать в бесконечном loading.

## 7. Overlap и mobile checks

Проверять минимум эти viewport:

| Viewport | Назначение |
| --- | --- |
| `1440 x 1000` | Desktop owner preview, landing + app + Control Panel. |
| `1024 x 768` | Tablet/узкий desktop, panel не должна съедать chat. |
| `390 x 844` | iPhone-like mobile, основной mobile smoke. |
| `360 x 740` | Минимальная ширина, переносы русских строк и safe-area. |

На каждом viewport проверить:

- нет horizontal scroll у `body`;
- нет наложения текста на кнопки, bird/product visual, composer, FAB, panel;
- sticky composer не скачет при появлении thinking/error state;
- mobile Control Panel выглядит как bottom sheet и помещается по высоте;
- tabs/quick actions скроллятся внутри своего контейнера, а не расширяют
  страницу;
- длинный prompt, длинное сообщение assistant и code/pre блоки не ломают ширину;
- при имитации mobile keyboard composer остаётся доступен.

Командный guard:

```bash
npm --prefix frontend run test:mobile-layout --if-present
```

Если guard прошёл, всё равно сделать ручной browser pass: этот тест ловит
контрактные CSS-инварианты, но не заменяет визуальную проверку overlap.

## 8. Visual evidence

Evidence хранить как task artifact или `/tmp`-папку и ссылаться на неё в
отчёте. Не коммитить screenshots в репозиторий без отдельного требования.

Рекомендуемая структура:

```text
/tmp/kolibri-browser-preview-qa/<YYYYMMDD-HHMM>/
  landing-desktop-1440.png
  app-desktop-1440.png
  app-control-desktop-1440.png
  landing-mobile-390.png
  app-mobile-390.png
  app-control-mobile-390.png
  console-landing.png
  console-app.png
  notes.md
```

Минимальный evidence-набор для handoff:

- screenshot `/` desktop;
- screenshot `/app` desktop;
- screenshot `/app` с открытым Control Panel;
- screenshot `/` mobile 390 px;
- screenshot `/app` mobile 390 px;
- screenshot DevTools Console без красных runtime ошибок или текстовое
  перечисление допустимых backend-offline ошибок;
- вывод команд `lint`, `build`, `test:mobile-layout`.

Если доступен Playwright CLI, можно снять статичные screenshots:

```bash
mkdir -p /tmp/kolibri-browser-preview-qa/$(date +%Y%m%d-%H%M)
QA_DIR=$(ls -td /tmp/kolibri-browser-preview-qa/* | head -1)
npx -y playwright@latest screenshot --viewport-size=1440,1000 http://127.0.0.1:5173/ "$QA_DIR/landing-desktop-1440.png"
npx -y playwright@latest screenshot --viewport-size=1440,1000 http://127.0.0.1:5173/app "$QA_DIR/app-desktop-1440.png"
npx -y playwright@latest screenshot --viewport-size=390,844 http://127.0.0.1:5173/ "$QA_DIR/landing-mobile-390.png"
npx -y playwright@latest screenshot --viewport-size=390,844 http://127.0.0.1:5173/app "$QA_DIR/app-mobile-390.png"
```

Для интерактивных состояний лучше использовать Codex Browser/in-app browser или
обычный браузер: открыть Control Panel, раскрыть нужную вкладку, проверить
console и сделать screenshot уже после взаимодействия.

## 9. Формат отчёта агента

Финальный отчёт browser preview агента должен быть коротким и проверяемым:

```text
Browser preview: GO / NO-GO / GO WITH EXCEPTION

URLs:
- /: http://127.0.0.1:5173/
- /app: http://127.0.0.1:5173/app

Commands:
- npm --prefix frontend run lint --if-present: pass/fail
- npm --prefix frontend run build: pass/fail
- npm --prefix frontend run test:mobile-layout --if-present: pass/fail

Browser checks:
- console: pass/fail, notes
- overlap desktop: pass/fail, notes
- overlap mobile: pass/fail, notes
- Control FAB/Panel: pass/fail, notes
- visual evidence: /tmp/... или artifact reference

Blockers:
- ...

Next action:
- ...
```

Не писать `готово`, если владелец не может открыть оба URL и увидеть свежие
изменения без дополнительных догадок.
