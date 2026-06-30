# Kolibri AI Platform

Собственная AI-платформа на 5 серверах с WireGuard mesh сетью.

## Архитектура

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Home      │     │    Main     │     │    UIAP     │
│ 10.99.0.1   │────▶│ 10.99.0.2   │────▶│ 10.99.0.3   │
│ Training    │     │ API Gateway │     │  RAG Engine │
│ Redis       │     │ Frontend    │     │ ChromaDB    │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
                    ┌──────┴──────┐
                    │             │
              ┌─────▼─────┐ ┌────▼──────┐
              │   QJNS    │ │   9FTS    │
              │ 10.99.0.4 │ │ 10.99.0.5 │
              │   Agent   │ │ Inference │
              │ MiMo CLI  │ │ TinyLlama │
              └───────────┘ └───────────┘
```

## Серверы

| Сервер | IP | Роль | Порт |
|--------|-----|------|------|
| Home | 178.207.11.90 | Training Hub, Redis | 2222 |
| Main | 104.253.43.117 | API Gateway, Frontend | 80, 8000 |
| UIAP | 31.57.26.151 | RAG Engine | 8002 |
| QJNS | 217.60.63.97 | Agent Executor | 8003 |
| 9FTS | 94.183.235.154 | Inference | 8001 |

## Стек

- **Frontend**: React 19, Vite, Framer Motion, Tailwind CSS
- **Backend**: FastAPI, SQLite, httpx
- **RAG**: ChromaDB, sentence-transformers
- **Inference**: TinyLlama-1.1B (Q4_K_M), llama.cpp
- **Network**: WireGuard mesh (10.99.0.0/24)
- **Orchestration**: Kolibri Organism v3 (Redis State Store, Job Queue)

## Быстрый старт

```bash
# Клонировать
git clone https://github.com/YOUR_USER/kolibri-ai-platform.git
cd kolibri-ai-platform

# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Деплой

Основной путь управления фабрикой — защищенный Fabric API control plane. SSH не является control plane и допускается только для bootstrap, emergency recovery и диагностики, когда API недоступен или еще не установлен. Контракт API-first управления описан в [docs/fabric-api-first-control.md](docs/fabric-api-first-control.md).

```bash
# На каждый сервер
./scripts/deploy.sh main    # API Gateway + Frontend
./scripts/deploy.sh uiap    # RAG Engine
./scripts/deploy.sh qjns    # Agent
./scripts/deploy.sh 9fts    # Inference
./scripts/deploy.sh home    # Training
```

## API Endpoints

| Endpoint | Описание |
|----------|----------|
| `POST /api/chat` | Чат с AI |
| `POST /api/pipeline` | Unified pipeline (RAG + Agent + Inference) |
| `GET /api/pipeline/health` | Health check всех сервисов |
| `POST /rag/search` | Поиск по базе знаний |
| `POST /inference/generate` | Генерация текста |
| `GET /cluster/status` | Статус кластера |

### Fabric Control API

| Endpoint | Описание |
|----------|----------|
| `GET /v1/fabric/health` | Health защищенного Fabric API |
| `GET /v1/fabric/policy` | Owner rights, auth/authz/scope/logging/rotation policy |
| `GET /v1/fabric/routes` | Представление всех серверов через API или fallback relay |
| `POST /v1/fabric/route` | Direct route или structured blocked status |
| `POST /v1/fabric/relay` | Safe relay contract |
| `POST /v1/fabric/bootstrap` | Контракт bootstrap нового сервера без вывода секретов |
| `GET /v1/fabric/keys/rotation` | Node identity и key rotation policy |

## Структура

```
kolibri-ai-platform/
├── backend/          # FastAPI backend (Main)
├── frontend/         # React frontend
├── infra/
│   ├── network/      # WireGuard, Kolibri Organism, Nginx
│   └── inference/    # Inference server (9FTS)
├── scripts/          # Deploy & training scripts
└── docs/             # Документация
```

## Лицензия

Kolibri AI Platform
