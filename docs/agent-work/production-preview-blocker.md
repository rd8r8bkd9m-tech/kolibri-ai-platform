# Production Preview Blocker

Дата среза: 2026-06-29 07:53 MSK  
Агент: `Ревизор production preview`  
Область: локальный production-like preview SPA на `127.0.0.1:4173`,
локальный backend на `127.0.0.1:8000`, отличие от Vite dev server
`127.0.0.1:5173`. Код приложения не менялся.

## 1. Текущий статус

| Контур | Проверка | Статус сейчас | Вывод |
| --- | --- | --- | --- |
| Production-like preview | `lsof -nP -iTCP:4173 -sTCP:LISTEN` | нет listener | `npm run build` и наличие `frontend/dist` сами не поднимают HTTP server. |
| Production-like preview | `curl -fsS http://127.0.0.1:4173/` | connection refused | Собранный bundle сейчас не открыт для browser/e2e проверки через `4173`. |
| Backend API | `lsof -nP -iTCP:8000 -sTCP:LISTEN` | нет listener | `uvicorn` сейчас не запущен. |
| Backend API | `curl -fsS http://127.0.0.1:8000/api/health` | connection refused | Live API, chat, billing, factory status и WebSocket сейчас не проверяются. |
| Vite dev server | `lsof -nP -iTCP:5173 -sTCP:LISTEN` | listener есть | Это dev-контур, не production preview. |
| Vite dev server | `curl -I http://127.0.0.1:5173/` и `/app` | `200 OK` | Можно смотреть dev UI, но этим нельзя закрыть blocker по `4173`. |

`frontend/dist` присутствует, включая `index.html`, assets, manifest,
service worker и icons. Это подтверждает наличие build artifacts, но не
подтверждает, что они обслуживаются как production-like preview.

## 2. Почему 4173 и 8000 сейчас не подняты

`127.0.0.1:4173` не поднят, потому что `frontend/package.json` разделяет
сборку и serving:

```json
"build": "vite build",
"preview": "vite preview"
```

`npm --prefix frontend run build` создает `frontend/dist`, но не запускает
`vite preview`. Для `4173` нужен отдельный foreground-процесс preview server.
Живой `5173` означает только, что где-то запущен `vite` dev server.

`127.0.0.1:8000` не поднят, потому что backend является отдельным FastAPI /
Uvicorn процессом из `backend/main.py`. Frontend build, Vite dev server и
Vite preview не стартуют backend автоматически.

Дополнительный backend-нюанс: `backend/main.py` сейчас создает core SQLite DB
по `/opt/kolibri-ai/data/kolibri.db`. Если `/opt/kolibri-ai/data` не
подготовлен для текущего пользователя, запуск backend может упасть до начала
прослушивания `8000`. Переменная `KOLIBRI_DB_PATH` используется billing-модулем,
но не заменяет этот core path в `main.py`.

## 3. Безопасный подъем после build

Перед запуском не убивать процессы вслепую. Сначала проверить занятость портов:

```bash
lsof -nP -iTCP:4173 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Если порт занят чужим процессом, остановить только осознанно выбранный процесс
или выбрать другой порт для временной диагностики. Для закрытия именно этого
blocker целевые порты должны быть `4173` и `8000`.

Собрать frontend:

```bash
npm --prefix frontend run build
```

Подготовить backend data dir, если локальная машина еще не имеет
`/opt/kolibri-ai/data`:

```bash
sudo install -d -o "$(id -un)" -g "$(id -gn)" /opt/kolibri-ai/data
```

В отдельном терминале поднять backend только на loopback:

```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

В отдельном терминале поднять production-like frontend preview строго на
`4173`:

```bash
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173 --strictPort
```

`--strictPort` нужен, чтобы Vite не переехал молча на другой порт. Preview на
другом порту полезен для диагностики, но не закрывает acceptance по
`127.0.0.1:4173`.

## 4. Evidence для закрытия blocker

Минимальные terminal evidence:

```bash
npm --prefix frontend run build
lsof -nP -iTCP:4173 -sTCP:LISTEN
lsof -nP -iTCP:8000 -sTCP:LISTEN
curl -I --max-time 2 http://127.0.0.1:4173/
curl -I --max-time 2 http://127.0.0.1:4173/app
curl -I --max-time 2 http://127.0.0.1:4173/manifest.webmanifest
curl -fsS --max-time 5 http://127.0.0.1:8000/api/health
curl -fsS --max-time 5 http://127.0.0.1:8000/api/providers
```

Для product QA добавить backend endpoints по цели проверки:

```bash
curl -fsS --max-time 5 http://127.0.0.1:8000/api/billing/plans
curl -fsS --max-time 5 http://127.0.0.1:8000/api/factory/status
```

`/api/factory/status` может вернуть degraded/503, если Control Plane
недоступен. Это отдельный factory/runtime blocker; он не должен маскировать
факт, что сам backend listener на `8000` поднят или не поднят.

Минимальные browser evidence:

- screenshot `http://127.0.0.1:4173/` desktop `1440 x 1000`;
- screenshot `http://127.0.0.1:4173/app` desktop `1440 x 1000`;
- screenshot `http://127.0.0.1:4173/app` с открытым Control Panel;
- screenshot `/` и `/app` mobile `390 x 844`;
- DevTools Console на `/` и `/app` без `Uncaught`, React runtime error,
  failed chunk load и белого экрана;
- Network evidence, что API calls идут к `127.0.0.1:8000`, а не к dev proxy
  `5173`.

Evidence хранить как task artifact или во временной папке, например:

```text
/tmp/kolibri-production-preview-qa/<YYYYMMDD-HHMM>/
  landing-desktop-1440.png
  app-desktop-1440.png
  app-control-desktop-1440.png
  landing-mobile-390.png
  app-mobile-390.png
  console-landing.png
  console-app.png
  terminal-evidence.txt
```

## 5. Что нельзя путать с dev server 5173

`127.0.0.1:5173` закрывает только dev preview. Он не доказывает, что:

- `npm run build` прошел;
- `frontend/dist` корректно обслуживается;
- `/app` работает через production-like history fallback;
- manifest, icons, service worker и built assets доступны из собранного
  bundle;
- нет production-only runtime/chunk/cache проблем;
- backend на `8000` реально жив для собранного приложения.

Dev server `5173` использует Vite dev pipeline, HMR, dev overlay и dev server
поведение. В `frontend/vite.config.js` dev server проксирует `/api` и `/ws` на
`localhost:8000`, но production-like bundle на `4173` должен проверяться как
собранное приложение, которое для local host обращается к
`http://127.0.0.1:8000` и `ws://127.0.0.1:8000`.

Формулировка `5173 отвечает 200 OK` допустима только как evidence для
dev-визуального smoke. Для production preview verdict она должна звучать как:
`dev server live; production preview 4173 still blocked`, пока `4173` не
отвечает сам.

## 6. Verdict на момент среза

Production preview: `NO-GO`.

Blockers:

- `127.0.0.1:4173` не слушает, `curl` получает connection refused;
- `127.0.0.1:8000` не слушает, `curl /api/health` получает connection refused;
- живой `127.0.0.1:5173` не заменяет `4173` и не закрывает production-like
  preview acceptance.

Next action: после fresh `npm --prefix frontend run build` поднять backend на
`8000`, поднять Vite preview на `4173 --strictPort`, затем приложить terminal и
browser evidence из раздела 4.
