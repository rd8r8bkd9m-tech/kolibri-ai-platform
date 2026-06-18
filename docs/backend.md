# Backend Kolibri AI

## Обзор

FastAPI-сервер на Main сервере (104.253.43.117:8000).
Основной API Gateway, проксирующий запросы к RAG, Agent и Inference сервисам.

## Структура

```
backend/
├── main.py              # FastAPI app, routes, proxy, SQLite, middleware
├── config.py            # Централизованная конфигурация (env vars)
├── auth.py              # JWT аутентификация (register, login, refresh)
├── providers.py         # AI Provider Manager (OpenAI-compatible HTTP API)
├── pipeline.py          # Unified pipeline (RAG + Agent + Inference)
├── routes_v1.py         # v1 API endpoints (MiMo CLI adapter)
├── adapter.py           # Adapter для MiMo CLI (port 8001)
├── health_checker.py    # Фоновая проверка нод кластера
├── logging_config.py    # JSON structured logging
├── tts.py               # Text-to-Speech engine
├── stt.py               # Speech-to-Text (заглушка)
├── websearch.py         # Web search (DuckDuckGo)
└── requirements.txt     # Зависимости
```

## Запуск

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## config.py — Конфигурация

Централизованная конфигурация через переменные окружения (python-dotenv).

```python
from dotenv import load_dotenv
load_dotenv()

DB_PATH = DATA_DIR / "kolibri.db"                    # KOLIBRI_DATA_DIR
JWT_SECRET = os.getenv("JWT_SECRET", "kolibri-secret")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "http://localhost:8080/v1")
AI_MODEL = os.getenv("AI_MODEL", "mimo-v2.5-pro")
```

---

## auth.py — JWT Аутентификация

Полная система JWT auth с регистрацией, логином и refresh токенами.

### База данных

Две дополнительные таблицы:

```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL
)

CREATE TABLE refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    token TEXT UNIQUE,
    expires_at REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
```

### Функции

| Функция | Описание |
|---------|----------|
| `register_user(username, password)` | Регистрация (bcrypt хеширование) |
| `login_user(username, password)` | Логин → access + refresh токены |
| `refresh_access_token(token)` | Обновление access токена |
| `get_current_user(token)` | Dependency для защищённых endpoints |
| `get_current_user_optional(token)` | Опциональная авторизация |

### Использование в endpoints

```python
@app.get("/api/auth/me")
async def get_me(user=Depends(get_current_user)):
    return {"username": user["username"], "id": user["id"]}
```

---

## health_checker.py — Проверка кластера

Фоновая asyncio задача, пингующая все ноды кластера через VPN каждые 30 секунд.

```python
class HealthChecker:
    async def check_all_nodes(self) -> dict    # Проверить все ноды
    def get_cached_status(self) -> dict         # Получить кешированный статус
```

Результаты кешируются и используются endpoint `/api/v1/cluster`.

---

## logging_config.py — Структурированное логирование

JSON логирование в stdout. Подавляет шумные логгеры uvicorn.access и httpx.

```python
import structlog
structlog.configure(processors=[...])
```

---

## main.py — Главный модуль

### Инициализация

```python
DB_PATH = DATA_DIR / "kolibri.db"

ai_manager = AIProviderManager()
tts_engine = TTSEngine()
stt_engine = STTEngine()
web_engine = WebSearchEngine()
health_checker = HealthChecker()
```

### Lifespan

```python
@asynccontextmanager
async def lifespan(app):
    await health_checker.start()    # Запуск фоновой проверки
    yield
    await health_checker.stop()     # Остановка
```

### Middleware

**RequestLoggingMiddleware** — логирует каждый запрос как JSON:
```json
{"method": "POST", "path": "/api/chat", "status": 200, "duration_ms": 1250, "client_ip": "10.0.0.1"}
```

### База данных (SQLite)

6 таблиц:

#### cache
```sql
CREATE TABLE cache (
    key TEXT PRIMARY KEY,        -- SHA-256 hash
    response TEXT,               -- Ответ AI
    provider TEXT,               -- Имя провайдера
    created_at REAL              -- Unix timestamp
)
```

#### conversations
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,         -- "conv_{timestamp}"
    title TEXT,                  -- Название диалога
    created_at REAL,
    updated_at REAL
)
```

#### messages
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT,        -- FK → conversations
    role TEXT,                   -- "user" | "assistant"
    content TEXT,
    provider TEXT,
    created_at REAL,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
)
```

#### rate_limits
```sql
CREATE TABLE rate_limits (
    ip TEXT,
    timestamp REAL,
    PRIMARY KEY (ip, timestamp)
)
```

#### users
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL
)
```

#### refresh_tokens
```sql
CREATE TABLE refresh_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    token TEXT UNIQUE,
    expires_at REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
```

### Rate Limiting

```python
def check_rate_limit(ip: str, limit: int = RATE_LIMIT_REQUESTS, window: int = RATE_LIMIT_WINDOW) -> bool
```
- Значения из env vars (по умолчанию 60 запросов в минуту на IP)
- Автоочистка старых записей

### Кеширование

```python
def get_cache_key(messages, model) -> str  # SHA-256
def cache_response(key, response, provider)
def get_cached_response(key) -> Optional[dict]
```

### Proxy Routes

```python
PROXY_ROUTES = {
    "/api/knowledge": {"target": RAG_SERVICE_URL, "strip": "/api/knowledge", "add": "/rag/documents"},
    "/api/agent":     {"target": AGENT_SERVICE_URL, "strip": "/api/agent", "add": "/agent"},
    "/api/inference": {"target": INFERENCE_SERVICE_URL, "strip": "/api/inference", "add": "/inference"},
    "/cluster":       {"target": "http://127.0.0.1:9001", "strip": "", "add": ""},
}
```

URL-ы берутся из env vars через `config.py`. Поле `strip` удаляет префикс перед проксированием.

### Estimate Mode

Автоматическое определение намерения на смету и специализированная обработка:

```python
def extract_estimate_json(text: str) -> dict     # Парсинг JSON из ответа AI
def normalize_estimate(data: dict) -> dict        # Нормализация RU/EN форматов
```

### WebSocket Auth

WebSocket endpoint принимает JWT токен через query param:
```
ws://localhost:8000/ws/chat?token=<jwt_token>
```

### Static Files

```python
frontend_path = FRONTEND_DIR
app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")))
```

SPA fallback: все неизвестные пути → `index.html`.

---

## providers.py — AI Provider Manager

### Класс AIProviderManager

HTTP-клиент для OpenAI-compatible API (не subprocess MiMo CLI).

```python
class AIProviderManager:
    def __init__(self):
        self.api_key = AI_API_KEY
        self.base_url = AI_BASE_URL
        self.model = AI_MODEL

    def get_status(self) -> list        # Статус провайдеров
    def get_model_catalog(self) -> list  # Каталог моделей
    def get_system_prompt(self) -> str   # Системный промпт
    async def generate(self, messages, model, provider, **kwargs) -> dict
    async def generate_stream(self, messages, model, provider, **kwargs) -> AsyncGenerator
```

### Генерация

Через httpx (OpenAI-compatible `/chat/completions` endpoint):

```python
async with httpx.AsyncClient(timeout=300.0) as client:
    response = await client.post(
        f"{self.base_url}/chat/completions",
        json={"model": self.model, "messages": messages, ...},
        headers={"Authorization": f"Bearer {self.api_key}"}
    )
```

### Стриминг

```python
async def generate_stream(self, messages, model, provider, **kwargs):
    async with httpx.AsyncClient(timeout=300.0) as client:
        async with client.stream("POST", url, json=payload) as response:
            async for line in response.aiter_lines():
                yield line  # SSE chunks
```

### Estimate Mode

Автоматическое определение сметного намерения:

```python
ESTIMATE_KEYWORDS = re.compile(r"смет|расценк|стоимость|посчитай|рассчитай|...", re.IGNORECASE)
ESTIMATE_SYSTEM_PROMPT = "Ты — эксперт по строительным сметам. Генерируй JSON..."

def is_estimate_intent(text: str) -> bool
```

При обнаружении сметного намерения:
- `max_tokens` увеличивается до 16384
- `temperature` снижается до 0.3
- Подставляется специализированный системный промпт

### Доступные модели

| Модель | Описание |
|--------|----------|
| mimo-v2.5-pro | Высокое качество рассуждений |
| mimo-v2.5-lite | Быстрая лёгкая модель |

### Экспорты

```python
# Модуль-level
manager = AIProviderManager()  # синглтон
is_estimate_intent(text)       # функция детекта смет
ESTIMATE_KEYWORDS              # regex паттерн
ESTIMATE_SYSTEM_PROMPT         # системный промпт для смет
```

---

## pipeline.py — Unified Pipeline

### Intent Detection

Определяет намерение пользователя по ключевым словам:

```python
AGENT_KEYWORDS = [
    "выполни", "сделай", "запусти", "deploy", "shell",
    "вычисли", "посчитай", "execute", "run", "calculate", "compute",
    "найди файл", "прочитай файл", "создай файл", "установи",
    "настрой", "проверь сервер", "скрипт", "команда", "терминал"
]

RAG_KEYWORDS = [
    "документ", "смета", "расценк", "цена на", "гост", "снип",
    "стоимость", "какие материалы", "нормы", "спец", "по документам",
    "в базе", "найди в документации", "согласно", "по данным", "из файла"
]
```

### Цепочки (Chains)

| Цепочка | Описание | Шаги |
|---------|----------|------|
| `chain_chat` | Прямой чат | inference_generate |
| `chain_rag` | RAG поиск + генерация | rag_search → inference_generate |
| `chain_agent` | Агент + инструменты | agent_chat |
| `chain_rag_agent` | RAG + Agent | rag_search → enrich context → agent_chat |

### Fallback режимы

- `chain_rag` имеет `fallback_direct`: если inference возвращает пустой ответ, форматирует сырые RAG-источники как ответ.
- `chain_rag_agent` аналогично имеет fallback.

### Retry Logic

Экспоненциальный backoff (3 попытки, базовая задержка 1с):
```python
async def _retry_request(func, *args, **kwargs):
    for attempt in range(3):
        try:
            return await func(*args, **kwargs)
        except (ConnectError, TimeoutException, ReadTimeout):
            await asyncio.sleep(2 ** attempt)
```

### Pipeline Endpoints

| Endpoint | Метод | Описание |
|----------|-------|----------|
| `/api/pipeline` | POST | Unified pipeline |
| `/api/pipeline/health` | GET | Health check сервисов |

---

## routes_v1.py — v1 API

Альтернативный API для совместимости.

```python
router = APIRouter()

@router.get("/api/v1/ai/models")
@router.get("/api/v1/model/stats")
@router.post("/api/v1/ai/chat")
@router.post("/api/v1/ai/chat/stream")  # SSE (single-event, не true streaming)
@router.post("/api/v1/ai/imagine")       # заглушка
@router.post("/api/v1/ai/vision/analyze") # заглушка
@router.get("/api/v1/swarm/runtime/status")
# ... и другие swarm endpoints
```

---

## tts.py — Text-to-Speech

### Класс TTSEngine

Движки (приоритет):
1. **edge-tts** — Microsoft Edge TTS (высокое качество)
2. **gtts** — Google TTS (fallback)

```python
class TTSEngine:
    async def synthesize(self, text, voice="en-US-AriaNeural") -> dict
    async def list_voices(self) -> list
```

Аудио сохраняется в `TTS_DIR` (из env var `KOLIBRI_TTS_DIR`, по умолчанию `/opt/kolibri-ai/data/tts/`).

---

## stt.py — Speech-to-Text

Заглушка. Требует GPU или значительных CPU ресурсов (Whisper).

```python
class STTEngine:
    async def transcribe(self, audio_data, language="en") -> dict
    # Returns: {"error": "STT not yet configured...", "text": None}
```

---

## websearch.py — Web Search

Поиск через DuckDuckGo API.

```python
class WebSearchEngine:
    async def search(self, query, num_results=5) -> list
```

Fallback при ошибке или пустых результатах:
```python
[{"title": "No results", "snippet": "Web search is not fully configured.", "url": ""}]
```

---

## adapter.py — MiMo CLI Adapter

Отдельный FastAPI-сервер (port 8001) для совместимости с MiMo CLI.
Проксирует `/api/v1/ai/chat` и `/api/v1/ai/chat/stream` на основной backend (port 8000).
Остальные endpoints возвращают заглушки локально.

```bash
python -m uvicorn adapter:app --host 0.0.0.0 --port 8001
```

Ответ swarm status:
```json
{"status": "active", "nodes": 4, "agents": ["main", "uiap", "qjns", "9fts"]}
```

---

## Модели данных (Pydantic)

```python
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None
    enable_thinking: Optional[bool] = False
    conversation_id: Optional[str] = None

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "en-US-AriaNeural"

class SearchRequest(BaseModel):
    query: str
    num_results: Optional[int] = 5

class ToolCallRequest(BaseModel):
    message: str
    tools: Optional[List[Dict[str, Any]]] = None

class PipelineRequest(BaseModel):
    message: str
    intent: Optional[Intent] = Intent.AUTO
    conversation: Optional[List[Dict[str, str]]] = None
    top_k: Optional[int] = 5
    max_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.7
    system_prompt: Optional[str] = None
    stream: Optional[bool] = False

class PipelineResponse(BaseModel):
    response: str
    intent_used: str
    sources: Optional[List[Dict[str, Any]]] = None
    tools_used: Optional[List[Dict[str, Any]]] = None
    model: Optional[str] = None
    latency_ms: int = 0
    pipeline: List[str] = []
```

## CORS

Конфигурируется через env var `CORS_ORIGINS` (comma-separated):

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS.split(","),    # По умолчанию: localhost:5173, localhost:3000
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)
```

## Системные зависимости

```
fastapi==0.115.0
uvicorn
httpx==0.27.0
pydantic==2.9.0
PyJWT==2.9.0
bcrypt>=4.0.0
python-dotenv==1.0.1
python-multipart==0.0.9
aiohttp==3.10.0
aiofiles==24.1.0
edge-tts  (опционально)
gtts      (опционально)
```
