# Быстрый запуск

Этот документ нужен разработчикам и агентам, чтобы поднять Kolibri локально
или на сервере без устных инструкций.

## Требования

- Python 3.11+
- Node.js 20+
- npm
- Git
- доступ к переменным окружения backend при работе с платежами и внешними AI
  провайдерами

## Backend

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Проверка:

```bash
curl http://localhost:8000/api/providers
```

## Frontend

```bash
cd frontend
npm install
npm run dev
```

По умолчанию Vite проксирует:

- `/api` на `http://localhost:8000`;
- `/ws` на `ws://localhost:8000`.

## Сборка PWA

```bash
npm --prefix frontend run build
```

После сборки проверить:

- `frontend/dist/index.html`;
- `frontend/dist/manifest.webmanifest`;
- `frontend/dist/service-worker.js`;
- icons для Android/iOS;
- deep links `/` и `/app`.

## Локальные проверки

```bash
python3 -m compileall -q backend ops scripts
npm --prefix frontend run build
npm --prefix frontend run test:mobile-layout
```

Если используется временный venv для backend tests:

```bash
python -m pytest -q backend/tests tests
```

## Control Plane

Статус фабрики:

```bash
ops/kolibri-dispatch --control-url http://10.99.0.2:9101 nodes
ops/kolibri-dispatch --control-url http://10.99.0.2:9101 status --limit 50
```

Отправка задачи:

```bash
ops/kolibri-dispatch --control-url http://10.99.0.2:9101 \
  submit --file ops/envelopes/KOL-DOCS-STEWARD-20260629.json
```

## Важные запреты

- Не запускать модельные эксперименты на Mac.
- Не печатать токены.
- Не коммитить `.env`, ключи, auth files.
- Не отправлять задачи без acceptance criteria.
