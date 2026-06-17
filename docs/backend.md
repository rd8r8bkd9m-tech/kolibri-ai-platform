# Backend Kolibri AI

## Обзор

FastAPI-сервер на Main сервере (104.253.43.117:8000).
Основной API Gateway, проксирующий запросы к RAG, Agent и Inference сервисам.

## Структура

```
backend/
├── main.py           # FastAPI app, routes, proxy, SQLite
├── routes_v1.py      # v1 API endpoints (MiMo CLI adapter)
├── pipeline.py       # Unified pipeline (RAG + Agent + Inference)
├── providers.py      # AI Provider Manager (MiMo CLI)
├── adapter.py        # Adapter для MiMo CLI (port 8001)
├── tts.py            # Text-to-Speech engine
├── stt.py            # Speech-to-Text (заглушка)
└── websearch.py      # Web search (DuckDuckGo)
```

## Запуск

```bash
cd backend
pip install fastapi uvicorn httpx pydantic
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

## main.py — Главный модуль

### Инициализация

```python
DB_PATH = Path("/opt/kolibri-ai/data/kolibri.db")

ai_manager = AIProviderManager()
tts_engine = TTSEngine()
stt_engine = STTEngine()
web_engine = WebSearchEngine()
```

### База данных (SQLite)

4 таблицы:

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

### Rate Limiting

```python
def check_rate_limit(ip: str, limit: int = 60, window: int = 60) -> bool
```
- 60 запросов в минуту на IP
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
    "/api/knowledge": {"target": "http://10.99.0.3:8002", "add": "/rag"},
    "/api/agent":     {"target": "http://10.99.0.4:8003", "add": "/agent"},
    "/api/inference": {"target": "http://10.99.0.5:8001", "add": "/inference"},
    "/cluster":       {"target": "http://127.0.0.1:9001", "add": ""},
}
```

Все запросы к `/api/knowledge/*` проксируются на UIAP:8002/rag/*.

### Static Files

```python
frontend_path = Path("/opt/kolibri-ai/frontend/dist")
app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")))
```

SPA fallback: все неизвестные пути → `index.html`.

---

## providers.py — AI Provider Manager

### Класс AIProviderManager

```python
class AIProviderManager:
    def __init__(self):
        self.mimo_path = "/root/.mimocode/bin/mimo"

    def get_status(self) -> list        # Статус провайдеров
    def get_model_catalog(self) -> list  # Каталог моделей
    def get_system_prompt(self) -> str   # Системный промпт
    async def generate(self, messages, model, provider, **kwargs) -> dict
    async def tool_call(self, message, tools) -> dict
```

### Генерация

Вызывает MiMo CLI через subprocess:

```python
result = subprocess.run(
    [self.mimo_path, "run", "--dangerously-skip-permissions",
     "--model", "mimo/mimo-auto", prompt],
    capture_output=True, text=True, timeout=120
)
```

**Системный промпт**:
```
Ты — Kolibri AI, большая языковая модель. Отвечай на языке пользователя. Не используй эмодзи.
```

### Доступные модели

| Модель | Описание |
|--------|----------|
| mimo-auto | Auto mode (рекомендуется) |
| mimo-v2.5-pro | Высокое качество рассуждений |
| mimo-v2.5-lite | Быстрая лёгкая модель |

---

## pipeline.py — Unified Pipeline

### Intent Detection

Определяет намерение пользователя по ключевым словам:

```python
AGENT_KEYWORDS = ["выполни", "сделай", "запусти", "deploy", "shell", ...]
RAG_KEYWORDS = ["документ", "смета", "расценк", "гост", "снип", ...]
```

### Цепочки (Chains)

| Цепочка | Описание | Шаги |
|---------|----------|------|
| `chain_chat` | Прямой чат | inference_generate |
| `chain_rag` | RAG поиск + генерация | rag_search → inference_generate |
| `chain_agent` | Агент + инструменты | agent_chat |
| `chain_rag_agent` | RAG + Agent | rag_search → agent_chat |

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
@router.post("/api/v1/ai/chat/stream")  # SSE
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

Аудио сохраняется в `/opt/kolibri-ai/data/tts/`.

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

---

## adapter.py — MiMo CLI Adapter

Отдельный FastAPI-сервер (port 8001) для совместимости с MiMo CLI.
Проксирует все запросы на основной backend (port 8000).

```bash
python -m uvicorn adapter:app --host 0.0.0.0 --port 8001
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
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    system_prompt: Optional[str] = None
    enable_thinking: Optional[bool] = False

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

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Системные зависимости

```
fastapi
uvicorn
httpx
pydantic
edge-tts  (опционально)
gtts      (опционально)
psutil    (для Organism)
```
