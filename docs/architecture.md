# Архитектура Kolibri AI Platform

## Обзор

Kolibri AI — распределённая AI-платформа на 6 серверах с mesh-сетью WireGuard.
Платформа объединяет API Gateway, RAG Engine, Agent Executor, Inference и Training Hub
в единую систему с общим состоянием через Redis.

## Схема кластера

```
                        ┌─────────────────────────────────────────────┐
                        │            INTERNET                         │
                        └──────────────┬──────────────────────────────┘
                                       │
                                       ▼
                        ┌──────────────────────────────┐
                        │         MAIN (Gateway)        │
                        │       104.253.43.117          │
                        │       10.99.0.2 (VPN)         │
                        │                               │
                        │  ┌───────────┐ ┌───────────┐ │
                        │  │  FastAPI   │ │  React 19 │ │
                        │  │  :8000    │ │  Vite     │ │
                        │  └─────┬─────┘ └───────────┘ │
                        │        │ proxy                │
                        └────────┼──────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   UIAP (RAG)    │ │   QJNS (Agent)  │ │  9FTS (Inference)│
│  31.57.26.151   │ │  217.60.63.97   │ │  94.183.235.154  │
│  10.99.0.3      │ │  10.99.0.4      │ │  10.99.0.5       │
│                 │ │                 │ │                  │
│  ChromaDB       │ │  MiMo CLI       │ │  TinyLlama       │
│  sentence-trans │ │  Agent Planner  │ │  llama.cpp       │
│  :8002          │ │  :8003          │ │  :8001           │
└─────────────────┘ └─────────────────┘ └─────────────────┘

              ┌──────────────────┬──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
┌─────────────────┐ ┌─────────────────┐
│   HOME (Redis)  │ │   JOAU (Worker) │
│  178.207.11.90  │ │  109.248.161.39 │
│  10.99.0.1      │ │  10.99.0.6      │
│                 │ │                 │
│  Redis 6379     │ │  Organism Agent │
│  Training Hub   │ │  :9001          │
│  Organism API   │ │                 │
│  :9001          │ │                 │
└─────────────────┘ └─────────────────┘
```

## Топология WireGuard Mesh

Подсеть: `10.99.0.0/24`

| Узел | VPN IP | Внешний IP | SSH |
|------|--------|------------|-----|
| Home | 10.99.0.1 | 178.207.11.90 | порт 2222 |
| Main | 10.99.0.2 | 104.253.43.117 | порт 22 |
| UIAP | 10.99.0.3 | 31.57.26.151 | порт 22 |
| QJNS | 10.99.0.4 | 217.60.63.97 | порт 22 |
| 9FTS | 10.99.0.5 | 94.183.235.154 | порт 22 |
| Joau | 10.99.0.6 | 109.248.161.39 | порт 22 |

Каждый узел подключён ко всем остальным (full mesh).
Redis на Home доступен всем узлям через VPN.

## Роли серверов

### Main (API Gateway)
- **IP**: 104.253.43.117 / 10.99.0.2
- **Порты**: 80 (nginx), 8000 (FastAPI), 9001 (Organism)
- **Сервисы**:
  - FastAPI backend — основной API
  - React 19 + Vite frontend (SPA)
  - Proxy routes к UIAP, QJNS, 9FTS
  - Nginx reverse proxy
  - Organism agent (job processor)
- **Данные**: SQLite (`/opt/kolibri-ai/data/kolibri.db`)

### Home (Training Hub)
- **IP**: 178.207.11.90 / 10.99.0.1
- **Порты**: 6379 (Redis), 9001 (Organism)
- **Сервисы**:
  - Redis — shared state store
  - Training scripts (fine-tune, dataset prep)
  - Organism API (cluster coordinator)

### UIAP (RAG Engine)
- **IP**: 31.57.26.151 / 10.99.0.3
- **Порты**: 8002
- **Сервисы**:
  - ChromaDB — векторная база данных
  - sentence-transformers — эмбеддинги
  - RAG search API
  - Organism agent

### QJNS (Agent Executor)
- **IP**: 217.60.63.97 / 10.99.0.4
- **Порты**: 8003
- **Сервисы**:
  - MiMo CLI — AI агент
  - Agent planner — цепочки рассуждений
  - Tool execution
  - Organism agent

### 9FTS (Inference)
- **IP**: 94.183.235.154 / 10.99.0.5
- **Порты**: 8001
- **Статус**: нестабилен (часто down)
- **Сервисы**:
  - TinyLlama-1.1B (Q4_K_M)
  - llama.cpp HTTP server
  - Organism agent

### Joau (Worker)
- **IP**: 109.248.161.39 / 10.99.0.6
- **Порты**: 9001
- **Сервисы**:
  - Organism agent (worker mode)
  - Backup inference (MiMo CLI)
  - Job processor

## Потоки данных

### 1. Chat Request Flow
```
User → Main:8000 /api/chat
  → AIProviderManager.generate()
  → subprocess: mimo CLI
  → Response → Cache (SQLite)
  → User
```

### 2. Pipeline Request Flow
```
User → Main:8000 /api/pipeline
  → Intent Detection (auto/rag/agent/chat)
  ├─ chat: Inference → Response
  ├─ rag: UIAP search → Context → Inference → Response
  ├─ agent: QJNS planning + tools → Response
  └─ auto: RAG + Agent combined → Response
```

### 3. RAG Search Flow
```
User → Main /api/knowledge → Proxy → UIAP:8002/rag/search
  → ChromaDB vector search
  → Top-K results with scores
  → Response via proxy
```

### 4. Organism Job Flow
```
Any node → Submit Job → Redis Queue
  → Best node selected (CPU/RAM scoring)
  → Job dispatched to target
  → Result stored in Redis
  → Polling returns result
```

## Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Frontend | React 19, Vite 8, Framer Motion, Tailwind CSS |
| Backend | FastAPI, SQLite, httpx |
| RAG | ChromaDB, sentence-transformers |
| Inference | TinyLlama-1.1B (Q4_K_M), llama.cpp |
| Agent | MiMo CLI |
| Network | WireGuard mesh VPN |
| Orchestration | Kolibri Organism v3 (Redis) |
| Core | Rust (kolibri_nano) |
| Languages | Python 3.11+, Rust 2021, JavaScript ESM |

## Безопасность

- CORS: `allow_origins=["*"]` (development)
- Rate limiting: 60 req/min per IP (SQLite-based)
- WireGuard: все межсерверные соединения через VPN
- SSH: ключевая аутентификация
- Нет аутентификации пользователей (MVP stage)
