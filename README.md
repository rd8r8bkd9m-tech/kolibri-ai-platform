# Kolibri AI Platform

Собственная AI-платформа на 6 серверах с WireGuard mesh сетью.

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
              │           │ │ TinyLlama │
              └───────────┘ └───────────┘
                    │
              ┌─────▼─────┐
              │    New    │
              │ 10.99.0.6 │
              │  Worker   │
              └───────────┘
```

## Серверы

| Сервер | IP | Роль | Порт |
|--------|-----|------|------|
| Home | 178.207.11.90 | Training Hub, Redis | 2222 |
| Main | 104.253.43.117 | API Gateway, Frontend | 80, 8000 |
| UIAP | 31.57.26.151 | RAG Engine | 8002 |
| QJNS | 217.60.63.97 | Agent Executor | 8003 |
| 9FTS | 94.183.235.154 | Inference | 8001 |
| New | 109.248.161.39 | Worker | 9001 |

## Стек

- **Frontend**: React 19, Vite, Framer Motion, tailwind-merge, CSS variables
- **Backend**: FastAPI, SQLite, httpx, PyJWT, bcrypt
- **RAG**: ChromaDB, sentence-transformers
- **Inference**: TinyLlama-1.1B (Q4_K_M), llama.cpp
- **Core**: Rust (kolibri_nano) — 11 модулей, 56 тестов
- **Network**: WireGuard mesh (10.99.0.0/24)
- **Orchestration**: Kolibri Organism v3 (Redis State Store, Job Queue)
- **Monitoring**: Prometheus + Grafana
- **CI/CD**: GitHub Actions

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

```bash
# На каждый сервер
./scripts/deploy.sh main    # API Gateway + Frontend
./scripts/deploy.sh uiap    # RAG Engine
./scripts/deploy.sh qjns    # Agent
./scripts/deploy.sh 9fts    # Inference
./scripts/deploy.sh home    # Training
./scripts/deploy.sh new     # Worker

# Расширенный деплой (с rollback и health check)
./scripts/auto-deploy.sh main
```

## API Endpoints

| Endpoint | Описание |
|----------|----------|
| `POST /api/chat` | Чат с AI |
| `POST /api/pipeline` | Unified pipeline (RAG + Agent + Inference) |
| `GET /api/pipeline/health` | Health check всех сервисов |
| `POST /api/auth/register` | Регистрация пользователя |
| `POST /api/auth/login` | Логин (JWT) |
| `GET /api/auth/me` | Текущий пользователь |
| `POST /rag/search` | Поиск по базе знаний |
| `POST /inference/generate` | Генерация текста |
| `GET /cluster/status` | Статус кластера |
| `GET /metrics` | Prometheus метрики |

## Структура

```
kolibri-ai-platform/
├── backend/          # FastAPI backend (Main)
├── frontend/         # React frontend
├── kolibri_nano/     # Rust core library (11 модулей)
├── infra/
│   ├── network/      # WireGuard, Kolibri Organism, Nginx, services
│   ├── inference/    # Inference server (9FTS)
│   └── systemd/      # Systemd service definitions
├── scripts/          # Deploy & training scripts
├── monitoring/       # Prometheus config
├── docs/             # Документация
└── docker-compose.yml # Docker Compose (6 services)
```

## Документация

- [Архитектура](docs/architecture.md)
- [API Reference](docs/api.md)
- [Backend](docs/backend.md)
- [Frontend](docs/frontend.md)
- [Deployment](docs/deployment.md)
- [Kolibri Nano (Rust)](docs/kolibri-nano.md)
- [Roadmap](docs/roadmap.md)
- [Training Pipeline](scripts/training/README.md)

## Лицензия

Proprietary — Xiaomi Kolibri AI Project
