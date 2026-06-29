# QA-пакет релиза Kolibri AI Platform

Дата: 2026-06-29  
Роль: `qa_lead`  
Назначение: полный pre-release пакет для SPA/PWA, backend, billing, estimates,
Control Plane, GitHub Project, agent feed, mobile/PWA и living bird.

## 1. Релизное правило

Релиз разрешается только если выполнены все обязательные гейты:

- frontend lint/build/mobile layout guard прошли без ошибок;
- backend, billing, estimates, PDF/document и factory contract tests прошли;
- публичные smoke-проверки приложения, `/api/providers`, `/api/billing/plans`
  и `/api/factory/status` успешны;
- Control Plane отвечает по `/health`, видит живые ноды, очередь не содержит
  необъяснённых `dead_letter`/stale lease;
- billing не активирует подписку в fallback lead-mode и корректно отклоняет
  невалидные T-Банк notifications;
- deterministic estimates воспроизводят один и тот же JSON/result для одного
  input hash, pricebook version и региона;
- PWA устанавливается на Android, открывается как Home Screen app на iOS и
  показывает offline shell;
- GitHub PR/Project/CI содержит проверяемый след: статус, артефакты, логи,
  блокеры и следующий шаг;
- owner-facing сообщения не раскрывают task id, node id, локальные пути, логи
  и артефакты без явного запроса владельца;
- нет секретов в diff, логах, screenshots и GitHub comments.

## 2. Области проверки

### SPA/PWA

Проверять:

- первый экран загружается без белого экрана, hydration/runtime errors и
  бесконечных loading states;
- чат принимает ввод, отправляет сообщение, показывает thinking state,
  результат, ошибку и retry/fallback;
- composer не перекрывается клавиатурой, sticky bottom работает на mobile;
- quick actions для смет, КП и документов вставляют корректный prompt;
- кнопка `Control` находится в правом нижнем углу и доступна на desktop/mobile;
- Control Panel открывает Documents, Cluster, Billing, Search, Settings без
  layout shift и перекрытий;
- billing UI показывает тарифы, цену, fallback/checkout state и ошибки;
- factory status UI показывает degraded state без падения SPA;
- service worker, manifest, icons 192/512, standalone mode и update flow
  работают предсказуемо;
- светлая/системная тема, contrast, focus states и keyboard navigation
  пригодны для работы;
- console не содержит uncaught errors, failed chunk load, mixed content,
  service worker install loop или CORS noise.

Expected evidence:

- вывод `npm run lint`, `npm run build`, `npm run test:mobile-layout`;
- screenshots desktop 1440px, mobile 390px, iOS safe area;
- browser console/network screenshot без красных ошибок;
- screenshot PWA install prompt или установленного standalone окна;
- screenshot Control Panel с открытым Cluster/Billing.

### Backend/API

Проверять:

- `/api/health`, `/api/providers`, `/api/models`;
- `/api/chat` с happy path, empty/invalid payload, rate limit, provider error;
- `/ws/chat` с корректным JSON, пустыми messages и disconnect;
- conversations CRUD: create/list/messages/delete;
- `/api/pipeline` и `/api/pipeline/health`;
- `/api/factory/status` возвращает degraded JSON при недоступном Control Plane,
  а не traceback;
- proxy routes `/api/knowledge`, `/api/agent`, `/api/inference`, `/cluster`
  корректно отвечают или честно возвращают upstream error;
- CORS, JSON error shape, timeout и отсутствие секретов в ошибках.

Expected evidence:

- curl outputs с HTTP 2xx/4xx/5xx там, где ожидается;
- backend log без stack trace на happy path;
- один зафиксированный degraded response для недоступного upstream;
- подтверждение, что rate limit возвращает `429`, а не ломает процесс.

### Billing

Проверять:

- `/api/billing/plans` возвращает `solo`, `team`, `studio`, суммы в копейках,
  RUB и `configured`;
- checkout без `TBANK_TERMINAL_KEY`/`TBANK_PASSWORD` создаёт lead, не создаёт
  active subscription и не вызывает T-Банк;
- checkout с sandbox credentials создаёт pending subscription, order id,
  payment id и payment URL;
- token generation сортирует flat values, игнорирует вложенные объекты,
  `Token` и `None`, bool приводит к lower-case строкам;
- notification с валидным token переводит подписку в `active` для
  `AUTHORIZED`/`CONFIRMED`/`COMPLETED`;
- notification с `REJECTED`, `CANCELED`, `DEADLINE_EXPIRED`,
  `ATTEMPTS_EXPIRED`, `REVERSED`, `REFUNDED` переводит подписку в безопасное
  состояние и пишет billing event;
- notification с плохим token возвращает `400`;
- `/api/billing/tbank/charge-due` требует `X-Kolibri-Billing-Token`, без него
  возвращает `403`;
- retry/duplicate notification идемпотентен для order/payment state;
- персональные данные не уходят в публичные логи и owner-facing статусы.

Expected evidence:

- pytest по `backend/tests/test_billing.py`;
- curl output `/plans` и fallback `/checkout`;
- screenshot или sanitized log sandbox Init/Notification/Charge;
- DB evidence: lead создан в fallback, active subscription не создан;
- негативный тест invalid token -> `400`.

### Estimates и документы

Проверять:

- одинаковый prompt, client, region, quality level и pricebook version дают
  одинаковый `estimate_id`, `input_hash`, totals и audit;
- golden case `100 м2 штукатурки в Татарстане` стабилен:
  `EST-A1B5B0B498`, `Республика Татарстан`,
  `kolibri-ru-2026q2-v1`, labor `106500.00`, materials `44000.00`,
  grand total `161035.00`;
- LLM не является источником истины для итогов: totals пересчитываются кодом;
- каждая строка имеет unit, quantity, labor/material unit price, provenance;
- audit содержит fingerprint, formula, pricebook version и input hash;
- PDF сметы и документов начинается с `%PDF`, содержит кириллицу и не пустой;
- document pack содержит КП, договор подряда, акт выполненных работ и счёт;
- коммерческая выдача клиенту запрещена без human QA для высокорисковых смет,
  пользовательских цен, неизвестных позиций, выбросов и больших допущений.

Expected evidence:

- pytest по `backend/tests/test_estimate_document_pdf_engines.py`;
- sample estimate JSON с input hash и audit fingerprint;
- sample PDF сметы и договора;
- QA note: какие допущения видит клиент и какой статус публикации у сметы.

### Control Plane и agent runtime

Проверять:

- `/health`, `/v1/nodes`, `/v1/tasks`, `/v1/filesystem` отвечают;
- node register принимает `node_id`, `agent_id`, `pid`, `capabilities`,
  `active_task`;
- heartbeat свежий, `draining=false`, нет stale `active_task`;
- task lifecycle: `queued -> leased -> running -> waiting_review/review ->
  completed` или контролируемые `failed`, `cancelled`, `retry_scheduled`,
  `dead_letter`;
- lease выдаётся только подходящему агенту, продлевается heartbeat и истекает
  предсказуемо;
- drain включает и снимает запрет на новые lease;
- cancel/retry/dead_letter не теряют result/error reference;
- filesystem namespace имеет вид `/kolibri/nodes/<node_id>`;
- Control Plane хранит manifests/namespaces как metadata и не читает node-local
  files напрямую;
- фабрика держит целевую нагрузку около 80%, оставляя 20% резерва;
- owner-facing summary редактирует технические id/path/logs.

Expected evidence:

- `ops/kolibri-dispatch doctor`, `nodes`, `status`;
- curl output `/health`, `/v1/nodes`, `/v1/tasks?summary=1&compact=1`,
  `/v1/filesystem`;
- sample task envelope и result envelope;
- список stale/dead_letter задач с решением: requeue, cancel, rollback или
  documented blocker.

### GitHub Project и CI

Проверять:

- каждая релизная задача имеет issue или PR на русском языке;
- PR содержит summary, проверки, блокеры, links на artifacts;
- CI зелёный или есть blocker report с точной причиной;
- GitHub Project содержит поля `Статус`, `Приоритет`, `Направление`, `Агент`,
  `Следующий отчёт`, `Артефакты`;
- статусы агентов не рекламные: факты, команды, ссылки, выводы;
- OAuth scopes для Project API проверены: `project`, `read:project`;
- secrets не попали в commits, PR comments, CI logs и artifacts;
- упавшие checks разобраны: кодовая ошибка исправлена, внешняя проблема
  оформлена blocker report.

Expected evidence:

- ссылка на PR/issue;
- screenshot или export GitHub Project row;
- `gh auth status` с нужными scopes или documented blocker;
- список checks и conclusion по каждому red/yellow пункту.

### Agent feed

Проверять:

- `POST /v1/agent-messages` принимает status, task_started, task_completed,
  task_failed, blocker, review_requested;
- без recipients сообщение попадает в `["all"]`;
- addressed updates корректно парсят `to` в массив recipients;
- artifact update содержит result reference, но owner-facing UI не раскрывает
  локальные пути без запроса;
- feed возвращает `GET /v1/agent-messages?target=all` и адресный inbox;
- дубликаты/повторные сообщения не ломают ленту;
- message body на русском, без секретов, токенов, приватных URL и лишних логов;
- task state в Control Plane и событие agent feed не расходятся.

Expected evidence:

- pytest `tests/test_factory_agent_messages.py`;
- curl output последних сообщений `target=all`;
- пример task_completed с artifacts и sanitized owner-facing summary.

### Mobile/PWA и GoMesh boundary

Проверять:

- Android Chrome: installability, standalone launch, icon, splash, back button;
- iOS Safari/Home Screen: safe area, keyboard, scroll, standalone viewport;
- offline shell открывается, не показывает пустую страницу;
- reconnect после offline/online обновляет chat/factory status без reload loop;
- composer, Control FAB и bottom panels не перекрываются keyboard/safe area;
- минимальные viewport: 360x740, 390x844, 768x1024;
- service worker не отдаёт старый bundle после нового deploy;
- `KOLIBRI_GOMESH_ENABLED=false` оставляет fallback через Control Plane;
- GoMesh код другой команды не трогается без передачи ответственности;
- при включённом GoMesh контракте проверяются registration, health/backpressure,
  task/message bridge и signed service-to-service requests.

Expected evidence:

- `npm run test:mobile-layout`;
- screenshots Android install, iOS Home Screen, offline shell;
- network log offline/online;
- запись feature flag state и fallback path.

### Living bird

Проверять:

- текущий `KolibriBird` показывает корректные states: idle, greeting,
  listening, thinking, writing, learning, success, error, happy, surprised,
  angry-soft, calm, sleepy, flying;
- будущий `LivingKolibri`/Rive contract покрывает idle, listening, thinking,
  working, success, warning, error, offline, sleepy, celebrating;
- реакции подключены к событиям `chat:focus`, `chat:send`, `ai:thinking`,
  `factory:task_started`, `factory:task_completed`, `factory:task_failed`,
  `billing:success`, `network:offline`, `network:online`;
- `prefers-reduced-motion` выключает или резко снижает бесконечные анимации;
- птица не перекрывает composer, Control FAB, toast/error и текст;
- нет layout shift при смене состояния;
- aria-label и `role="img"` присутствуют;
- FPS приемлемый на low-power mobile, bundle size не растёт без объяснения;
- personality profile не раздражает пользователя постоянным движением.

Expected evidence:

- screenshot/video states idle/thinking/success/error/offline;
- reduced motion screenshot или devtools recording;
- performance note: FPS, layout shift, bundle delta;
- accessibility note: aria-label/focus не ломаются.

## 3. Команды

Запускать из корня репозитория:

```bash
git status --short
node --version
npm --prefix frontend ci
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout
```

Backend/test environment без записи в репозиторий:

```bash
python3 -m venv /tmp/kolibri-qa-venv
source /tmp/kolibri-qa-venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt pytest
PYTHONPATH=backend python -m pytest backend/tests tests
```

Локальный backend smoke:

```bash
cd backend
KOLIBRI_DB_PATH=/tmp/kolibri-qa.db python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Во втором терминале:

```bash
curl -fsS http://127.0.0.1:8000/api/health | jq .
curl -fsS http://127.0.0.1:8000/api/providers | jq .
curl -fsS http://127.0.0.1:8000/api/billing/plans | jq .
curl -fsS http://127.0.0.1:8000/api/factory/status | jq .
curl -fsS -X POST http://127.0.0.1:8000/api/billing/checkout \
  -H 'Content-Type: application/json' \
  -d '{"plan_id":"solo","email":"qa@example.com","company":"Kolibri QA","name":"QA","phone":"+79990000000"}' | jq .
curl -sS -o /tmp/kolibri-invalid-token.out -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8000/api/billing/tbank/notification \
  -H 'Content-Type: application/json' \
  -d '{"OrderId":"qa_bad_token","PaymentId":"1","Status":"CONFIRMED","Success":true,"Token":"bad"}'
```

Frontend preview:

```bash
npm --prefix frontend run preview -- --host 127.0.0.1 --port 4173
```

Public smoke:

```bash
curl -fsSI http://104.253.43.117
curl -fsS http://104.253.43.117/api/providers | jq .
curl -fsS http://104.253.43.117/api/billing/plans | jq .
curl -fsS http://104.253.43.117/api/factory/status | jq .
npx -y wscat -c ws://104.253.43.117/ws/chat
```

WebSocket payload для `wscat`:

```json
{"messages":[{"role":"user","content":"ping"}],"model":"auto"}
```

Control Plane:

```bash
export KOLIBRI_FACTORY_CONTROL_URL=http://10.99.0.2:9101
python3 ops/kolibri-dispatch doctor
python3 ops/kolibri-dispatch nodes
python3 ops/kolibri-dispatch status --limit 50
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/health" | jq .
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/v1/tasks?summary=1&compact=1&limit=50" | jq .
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/v1/filesystem" | jq .
curl -fsS "$KOLIBRI_FACTORY_CONTROL_URL/v1/agent-messages?target=all" | jq .
```

Read-only QA task через фабрику, если live-контур готов:

```bash
python3 ops/kolibri-dispatch submit --file ops/envelopes/KOL-PRODUCT-QA-E2E-20260629.json
python3 ops/kolibri-dispatch status KOL-PRODUCT-QA-E2E-20260629 --full
python3 ops/kolibri-dispatch collect KOL-PRODUCT-QA-E2E-20260629
```

GitHub Project/CI:

```bash
gh auth status
gh pr status
gh run list --limit 10
gh run view --log-failed
```

Секреты и технический след:

```bash
git diff --check
git diff --cached --check
rg -n "TBANK_PASSWORD|TOKEN|SECRET|PRIVATE KEY|Authorization: Bearer|sk-" .
```

## 4. Expected evidence к релизу

Минимальный evidence pack:

- commit SHA, branch, PR URL, дата и ответственный QA;
- `git status --short` перед началом и перед release decision;
- вывод frontend commands: `ci`, `lint`, `build`, `test:mobile-layout`;
- вывод backend pytest: `backend/tests` и `tests`;
- public smoke curl outputs;
- Control Plane health/nodes/tasks/filesystem/agent feed outputs;
- billing evidence: plans, fallback checkout, invalid token rejection,
  sandbox payment flow если credentials доступны;
- estimates evidence: golden deterministic test, sample JSON, sample PDF;
- mobile evidence: Android install, iOS Home Screen, offline shell,
  keyboard/safe-area screenshots;
- living bird evidence: states, reduced motion, no overlap, performance note;
- GitHub evidence: PR, CI checks, Project row, blocker report если есть;
- sanitized incident/rollback note, если во время проверки был сбой.

Evidence должен быть воспроизводимым: команды, URL, входные payload, время,
ожидаемый и фактический результат. Screenshots без команд и версий не считаются
достаточным доказательством для P0/P1 контуров.

## 5. Blocker policy

### P0 - релиз запрещён

P0 блокирует deploy/merge до исправления или rollback:

- SPA не загружается, чат неработоспособен или есть white screen;
- `npm run build`, backend pytest, billing tests, estimates tests или factory
  contract tests падают;
- backend health/providers недоступны в целевом окружении;
- billing может активировать подписку без подтверждённой оплаты, неверно
  принимает T-Банк token или создаёт active subscription в fallback lead-mode;
- estimates дают разные totals/id/hash для одинаковых входных данных;
- PDF/документы коммерческого контура генерируются битые или без кириллицы;
- Control Plane недоступен, lease lifecycle сломан, stale active task массово
  блокирует ноды или filesystem namespace нарушает `/kolibri/nodes/<node_id>`;
- owner-facing канал раскрывает секреты, приватные URL, local paths, node ids
  или task ids без запроса;
- GitHub CI красный по продуктовой/кодовой причине без approved exception;
- PWA после deploy отдаёт старый bundle или не открывается на mobile;
- найден секрет в diff, логах, artifacts или PR comments.

### P1 - релиз только по письменному exception

P1 допускается только с owner approval, workaround и датой исправления:

- один из вторичных Control Panel plugins degraded, но core chat/billing/status
  работают;
- GitHub Project API недоступен из-за OAuth scope, но PR/issue trail полный;
- GoMesh feature flag выключен и fallback через Control Plane подтверждён;
- отдельная remote node stale, но capacity остаётся в рамках 80/20 и очередь
  не деградирует;
- living bird имеет некритичный animation bug без перекрытия UI и с reduced
  motion fallback;
- WebSocket degraded, но `/api/chat` работает и пользователь получает ответ.

### P2 - можно выпускать с задачей в backlog

P2 не блокирует релиз, если есть issue:

- косметические spacing/typography дефекты без overlap;
- неидеальная microcopy, не влияющая на юридический/billing смысл;
- недостающий hover/focus polish при сохранённой keyboard доступности;
- minor performance regression без влияния на low-power mobile;
- неполный analytics/evidence dashboard при наличии ручного evidence pack.

### External blocker

Если причина внешняя, релизное решение всё равно фиксируется явно:

- указать внешний сервис, время, endpoint/command, error text, impact;
- приложить fallback или rollback plan;
- определить owner и срок повторной проверки;
- создать GitHub issue/Project item со статусом `Заблокирована`;
- не маскировать внешний blocker как успешный QA.

## 6. Release decision template

```text
QA decision: GO / NO-GO / GO WITH EXCEPTION
Дата:
Commit/branch:
PR:
Окружение:

Passed gates:
- Frontend:
- Backend:
- Billing:
- Estimates:
- Control Plane:
- GitHub Project/CI:
- Agent feed:
- Mobile/PWA:
- Living bird:

Blockers:
- P0:
- P1:
- P2:

Evidence:
- Commands:
- Screenshots:
- Logs:
- Artifacts:

Rollback plan:
- Trigger:
- Команда/действие:
- Проверка после rollback:
```
