# API Kolibri AI Platform

## Базовый URL

- **Production**: `https://kolibri.ai` (через Main server)
- **Development**: `http://localhost:8000`

## Health & Status

### GET /api/health
Проверка работоспособности backend.

```bash
curl http://localhost:8000/api/health
```

```json
{
  "status": "ok",
  "provider_status": [
    {"name": "mimo", "available": true, "status": "online"},
    {"name": "openai", "available": false, "status": "offline"}
  ]
}
```

### GET /api/providers
Список доступных AI-провайдеров.

### GET /api/models
Каталог моделей и системный промпт.

```json
{
  "models": [
    {"name": "mimo-v2.5-pro", "description": "High quality reasoning", "available": true},
    {"name": "mimo-v2.5-lite", "description": "Fast lightweight model", "available": true}
  ],
  "system_prompt": "Ты — Kolibri AI, большая языковая модель..."
}
```

### GET /metrics
Prometheus-format метрики.

```json
{
  "uptime_seconds": 86400,
  "total_requests": 12345,
  "total_errors": 42
}
```

---

## Auth API

### POST /api/auth/register
Регистрация нового пользователя.

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "securepass"}'
```

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### POST /api/auth/login
Логин. Возвращает JWT токены.

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "securepass"}'
```

```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer"
}
```

### POST /api/auth/refresh
Обновление access токена.

```bash
curl -X POST http://localhost:8000/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "eyJ..."}'
```

### GET /api/auth/me
Получить текущего авторизованного пользователя (требует auth).

```bash
curl http://localhost:8000/api/auth/me \
  -H "Authorization: Bearer eyJ..."
```

```json
{"id": 1, "username": "user1"}
```

---

## Chat API

### POST /api/chat
Основной чат с AI. Поддерживает кеширование.

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"role": "user", "content": "Привет!"}],
    "model": "mimo-v2.5-pro",
    "provider": "mimo",
    "temperature": 0.7,
    "max_tokens": 2048,
    "enable_thinking": false
  }'
```

**Параметры запроса**:
| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| messages | ChatMessage[] | *обязательно* | История сообщений |
| model | string | null | Имя модели |
| provider | string | null | Провайдер (mimo, openai, anthropic) |
| temperature | float | null | Температура генерации |
| max_tokens | int | null | Максимум токенов |
| enable_thinking | bool | false | Включить reasoning |
| system_prompt | string | null | Доп. системный промпт |
| conversation_id | string | null | ID диалога для сохранения сообщений |

**Ответ**:
```json
{
  "response": "Привет! Чем могу помочь?",
  "provider": "mimo",
  "model": "mimo-v2.5-pro",
  "cached": false
}
```

### WebSocket /ws/chat
Стриминг чата через WebSocket. Поддерживает JWT auth через query param.

```javascript
const ws = new WebSocket("ws://localhost:8000/ws/chat?token=eyJ...");
ws.onopen = () => {
  ws.send(JSON.stringify({
    messages: [{role: "user", content: "Привет!"}],
    model: "mimo-v2.5-pro"
  }));
};
ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  console.log(data.response);
};
```

---

## Pipeline API

### POST /api/pipeline
Единый пайплайн: RAG + Agent + Inference с автоопределением намерения.

```bash
curl -X POST http://localhost:8000/api/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Найди расценку на штукатурку в документах",
    "intent": "auto",
    "top_k": 5,
    "max_tokens": 2048,
    "temperature": 0.7
  }'
```

**Параметры**:
| Поле | Тип | По умолчанию | Описание |
|------|-----|-------------|----------|
| message | string | *обязательно* | Сообщение пользователя |
| intent | string | "auto" | auto, chat, rag, agent |
| conversation | dict[] | null | Контекст разговора |
| top_k | int | 5 | Количество RAG-результатов |
| max_tokens | int | 2048 | Максимум токенов |
| temperature | float | 0.7 | Температура |
| system_prompt | string | null | Системный промпт |
| stream | bool | false | Стриминг (заглушка) |

**Автоопределение intent** (ключевые слова):
- **agent**: "выполни", "сделай", "запусти", "вычисли", "посчитай", "deploy", "shell", "execute", "run", "calculate", "compute", "найди файл", "прочитай файл", "создай файл", "установи", "настрой", "проверь сервер", "скрипт", "команда", "терминал"
- **rag**: "документ", "смета", "расценк", "цена на", "гост", "снип", "стоимость", "какие материалы", "нормы", "спец", "по документам", "в базе", "найди в документации", "согласно", "по данным", "из файла"
- **chat**: всё остальное

**Ответ**:
```json
{
  "response": "Согласно документам, расценка на штукатурку...",
  "intent_used": "rag",
  "sources": [
    {"content": "Штукатурка стен, расценка 350 руб/м2", "metadata": {}, "distance": 0.23}
  ],
  "tools_used": null,
  "model": "inference",
  "latency_ms": 1250,
  "pipeline": ["rag_search", "inference_generate"]
}
```

### GET /api/pipeline/health
Health check всех сервисов пайплайна.

```json
{
  "pipeline": "ok",
  "services": {
    "rag": {"url": "http://10.99.0.3:8002", "status": "ok"},
    "agent": {"url": "http://10.99.0.4:8003", "status": "ok"},
    "inference": {"url": "http://10.99.0.5:8001", "status": "down"}
  }
}
```

---

## Conversations API

### POST /api/conversations
Создать диалог.

```bash
curl -X POST "http://localhost:8000/api/conversations?title=Мой%20чат"
```

```json
{"id": "conv_1718000000000", "title": "Мой чат"}
```

### GET /api/conversations
Список всех диалогов (sorted by updated_at DESC).

### GET /api/conversations/{conv_id}/messages
Сообщения конкретного диалога.

### DELETE /api/conversations/{conv_id}
Удалить диалог и все его сообщения.

---

## Voice API

### POST /api/tts
Синтез речи (Text-to-Speech).

```bash
curl -X POST http://localhost:8000/api/tts \
  -H "Content-Type: application/json" \
  -d '{"text": "Привет, мир!", "voice": "ru-RU-DmitryNeural"}'
```

```json
{"audio": "/api/tts/audio/tts_12345.mp3", "provider": "edge-tts", "voice": "ru-RU-DmitryNeural"}
```

Движки (приоритет): edge-tts → gtts → ошибка.

### GET /api/tts/voices
Список доступных голосов (до 50).

### POST /api/search
Веб-поиск через DuckDuckGo.

```bash
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "Kolibri AI", "num_results": 5}'
```

---

## Tools API

### POST /api/tools
Вызов инструментов (tool calling). Заглушка.

```bash
curl -X POST http://localhost:8000/api/tools \
  -H "Content-Type: application/json" \
  -d '{"message": "Посчитай 2+2", "tools": []}'
```

---

## Cluster API

### GET /api/v1/cluster
Агрегированный статус здоровья всех нод кластера (данные от health_checker).

```json
{
  "nodes": {
    "home": {"status": "ok", "ip": "10.99.0.1", "role": "training"},
    "main": {"status": "ok", "ip": "10.99.0.2", "role": "gateway"},
    "uiap": {"status": "ok", "ip": "10.99.0.3", "role": "rag"},
    "qjns": {"status": "ok", "ip": "10.99.0.4", "role": "agent"},
    "9fts": {"status": "down", "ip": "10.99.0.5", "role": "inference"}
  }
}
```

---

## Proxy Routes

Main сервер проксирует запросы к другим сервисам.
URL-ы берутся из env vars. Префикс удаляется перед проксированием.

| Префикс | Target | Добавляется | Описание |
|---------|--------|-------------|----------|
| `/api/knowledge/*` | RAG_SERVICE_URL | `/rag/documents` | RAG Engine |
| `/api/agent/*` | AGENT_SERVICE_URL | `/agent` | Agent Executor |
| `/api/inference/*` | INFERENCE_SERVICE_URL | `/inference` | Inference |
| `/cluster/*` | localhost:9001 | (ничего) | Organism (local) |

---

## v1 API (Adapter)

Альтернативный API для совместимости с MiMo CLI.

### GET /api/v1/ai/models
### GET /api/v1/model/stats
### POST /api/v1/ai/chat
### POST /api/v1/ai/chat/stream (SSE — single-event, не true streaming)
### POST /api/v1/ai/imagine (заглушка)
### POST /api/v1/ai/vision/analyze (заглушка)
### POST /api/v1/ai/demo/learn/text (заглушка)
### GET /api/v1/ai/quality/benchmark/history

### Swarm Runtime API
| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/v1/swarm/runtime/status` | GET | Статус swarm |
| `/api/v1/swarm/runtime/start` | POST | Запуск swarm |
| `/api/v1/swarm/runtime/refresh` | POST | Обновление |
| `/api/v1/swarm/runtime/run` | POST | Запуск задачи |
| `/api/v1/swarm/runtime/ingest/text` | POST | Ингест текста |
| `/api/v1/swarm/runtime/ingest/url` | POST | Ингест URL |
| `/api/v1/swarm/runtime/kpack/export` | POST | Экспорт kpack |
| `/api/v1/swarm/runtime/kpack/import` | POST | Импорт kpack |
| `/api/v1/ai/training/queue/status` | GET | Очередь обучения |

---

## Organism API (Home:9001 / Joau:9001)

### Health

```
GET /health
```

```json
{
  "status": "ok",
  "node": "home",
  "role": "training",
  "ip": "10.99.0.1",
  "redis": "connected",
  "load": {"cpu_percent": 12.0, "ram_percent": 45.2, "ram_used_gb": 3.6, "ram_total_gb": 8.0}
}
```

### Cluster Status

```
GET /cluster/status
```

```json
{
  "cluster": "Kolibri Organism",
  "subnet": "10.99.0.0/24",
  "total_nodes": 6,
  "online_nodes": 5,
  "total_ram_gb": 48.0,
  "used_ram_gb": 22.5,
  "free_ram_gb": 25.5,
  "avg_cpu_percent": 18.3,
  "nodes": {
    "home": {"role": "training", "ip": "10.99.0.1", "cpu": 12.0, "ram": "3.6/8.0 GB"},
    "main": {"role": "gateway", "ip": "10.99.0.2", "cpu": 25.0, "ram": "5.2/16.0 GB"}
  }
}
```

### Job Queue

```
POST /job/submit          — Отправить задачу
GET  /job/{job_id}        — Статус задачи
GET  /job/{job_id}/wait   — Ожидание результата (polling)
POST /job/{job_id}/cancel — Отмена
GET  /jobs?status=all     — Список задач
```

### State Store

```
POST   /state/set         — {"key": "...", "value": "...", "ttl": 3600}
GET    /state/{key}       — Получить значение
DELETE /state/{key}       — Удалить
GET    /state?pattern=*   — Список всех
```

### Node Management

```
POST /node/register       — Регистрация ноды
POST /node/heartbeat      — Heartbeat
GET  /nodes               — Все ноды
GET  /nodes/online        — Онлайн ноды
```

### Compute

```
POST /compute             — Универсальный вычислительный endpoint
POST /task/execute        — Прямое выполнение на ноде
POST /broadcast           — Широковещательное сообщение
```

---

## Ошибки

| Код | Описание |
|-----|----------|
| 200 | Успех |
| 400 | Неверный запрос |
| 401 | Не авторизован |
| 404 | Не найдено |
| 429 | Rate limit (60 req/min) |
| 500 | Внутренняя ошибка сервера |

```json
{"detail": "Rate limit exceeded"}
```
