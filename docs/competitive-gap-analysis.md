# Gap-анализ: Kolibri AI vs Конкуренты

> Дата: 2026-06-17
> Статус: Заполнено (deep-research: 103 агента, 98 фактов, 20 источников)
> Автор: Kolibri AI Architect

---

## 1. Executive Summary

**Kolibri AI занимает уникальную нишу, но критически отстаёт по инфраструктуре.**

- **Уникальная позиция**: единственный self-hosted AI-продукт с Rust-ядром поведенческого моделирования, распределённой архитектурой 6 серверов и строительной специализацией. Ни один конкурент не имеет аналога.
- **Рынок пуст**: российский сегмент self-hosted AI-платформ фактически не существует — GigaChat и YandexGPT это SaaS API-провайдеры, а не платформы. Это окно возможностей.
- **Главные пробелы (P0)**: нет авторизации, SQLite вместо PostgreSQL, CORS wildcard, нет SSL — блокеры для любого продакшена.
- **RAG значительно отстаёт**: конкуренты предлагают 6-9 vector DB, hybrid search, advanced chunking, reranking. Kolibri — только ChromaDB + basic semantic search.
- **Приоритет №1**: Phase 5.5 (безопасность) → Phase 5.6 (DevOps) — без этого продукт нельзя показывать вне dev-среды.

---

## 2. Текущее состояние Kolibri AI

### 2.1 Что реализовано (MVP, фазы 1-4)

| Модуль | Статус | Описание |
|--------|--------|----------|
| Chat Core | ✅ Работает | REST + WebSocket, streaming, история в SQLite |
| Kolibri Canvas | ✅ Работает | 8 типов карточек (смета, документ, таблица, код, план, чеклист, память, действие) |
| Kolibri Nano (Rust) | ✅ Работает | Следы, ассоциации, микровеса, confidence, персональное ядро, estimate engine |
| Memory Engine | ✅ Базовый | Trace-based память с 9 типами, pattern extraction |
| Knowledge Engine | ✅ Работает | ChromaDB + sentence-transformers, RAG pipeline |
| Estimate Engine | ✅ Работает | JSON-сметы, расчёт totals, привязка к клиенту/объекту |
| Document Engine | ⚠️ Заготовка | Типы документов определены, экспорт не реализован |
| Action Engine | ⚠️ Заготовка | Tool calling — stub endpoint |
| Provider Layer | ✅ Работает | MiMo CLI как основной провайдер, абстракция для OpenAI/Anthropic/Local |
| Training Layer | ⚠️ Скрипты | LoRA fine-tuning для Qwen2.5-1.5B, пайплайн готов |
| Security Layer | ❌ Нет | Нет авторизации, RBAC, шифрования |
| Orchestration | ✅ Работает | Kolibri Organism v3: Redis job queue, heartbeat, 6 серверов |

### 2.2 Архитектура

```
MacBook (оркестратор)
    │
    ├── Home (10.99.0.1)    — Training Hub, Redis, Organism API
    ├── Main (10.99.0.2)    — API Gateway, FastAPI, React SPA, Nginx
    ├── UIAP (10.99.0.3)    — RAG Engine, ChromaDB, sentence-transformers
    ├── QJNS (10.99.0.4)    — Agent Executor, MiMo CLI
    ├── 9FTS (10.99.0.5)    — Inference, TinyLlama-1.1B, llama.cpp
    └── Joau (10.99.0.6)    — Worker, Organism agent
```

### 2.3 Технологический стек

| Слой | Технологии |
|------|------------|
| Frontend | React 19, Vite 8, Tailwind CSS, Framer Motion |
| Backend | Python 3.11+, FastAPI 0.115, SQLite, Pydantic 2.9 |
| AI | MiMo CLI, TinyLlama-1.1B (Q4_K_M), llama.cpp |
| RAG | ChromaDB, sentence-transformers |
| Orchestration | Redis, WireGuard mesh, custom Organism v3 |
| Core | Rust 2021 (kolibri_nano crate) |
| Training | PyTorch, PEFT, TRL, HuggingFace Transformers |

### 2.4 Известные проблемы

- 9FTS нестабилен (1.9GB RAM, часто падает)
- Нет авторизации (CORS wildcard `*`)
- SQLite не для продакшена
- Монолитный фронтенд (~700 строк App.jsx)
- Нет CI/CD, нет SSL, нет мониторинга

---

## 3. Конкурентный ландшафт

### 3.1 Обзор конкурентов

<!-- Будет заполнено после research -->

| # | Платформа | Тип | GitHub Stars | Последний релиз | Pricing |
|---|-----------|-----|-------------|-----------------|---------|
| 1 | Dify | Open-source | 146k | v1.14.2 (May 2026) | Free / Cloud от $59/mo / Enterprise |
| 2 | FlowiseAI | Open-source | 53.7k | Apr 2026 | Free / Starter $35/mo / Enterprise |
| 3 | AnythingLLM | Open-source | 61.7k | v1.14.1 (Jun 2026) | Free / Cloud |
| 4 | n8n | Open-source (fair-code) | 193k | v2.26.5 (Jun 2026) | Free self-hosted / Cloud от €20/mo |
| 5 | LibreChat | Open-source | — | — | Free |
| 6 | Open WebUI | Open-source | 142k | v0.9.6 (Jun 2026) | Free |
| 7 | LocalAI | Open-source | 46.9k | v4.4.3 (Jun 2026) | Free (MIT) |
| 8 | GigaChat | SaaS API | N/A | N/A | Pay-per-token (Lite/Pro/MAX tiers) |
| 9 | YandexGPT | SaaS API | N/A | N/A | Pay-per-token via Yandex Cloud |
| 10 | Aragorn.ai | SaaS | N/A | N/A | Нет данных |

### 3.2 Технологический стек конкурентов

<!-- Будет заполнено после research -->

| Платформа | Vector DB | Embeddings | Auth | DB | Deployment |
|-----------|-----------|------------|------|-----|------------|
| Dify | Встроенный | Встроенный | Built-in JWT/OAuth | PostgreSQL | Docker, K8s |
| FlowiseAI | ChromaDB + others (via LangChain) | Via LangChain | Built-in | SQLite/PostgreSQL | Docker, npm |
| AnythingLLM | 9 backends (LanceDB default, ChromaDB, PGVector, Pinecone, Qdrant, Milvus, Weaviate, Astra, Zilliz) | Native + 12+ внешних (OpenAI, Azure, Gemini, Ollama, Cohere, Voyage, Mistral и др.) | Docker-only multi-user | SQLite/PostgreSQL | Docker, desktop |
| n8n | 8+ (via LangChain: Pinecone, Qdrant, Milvus, ChromaDB, PGVector, Weaviate, Redis, MongoDB Atlas) | Via LangChain | Built-in | PostgreSQL/SQLite | Docker, npm, K8s |
| LibreChat | — | — | Built-in | MongoDB | Docker |
| Open WebUI | 9 backends (ChromaDB, PGVector, Qdrant, Milvus, Elasticsearch, OpenSearch, Pinecone, S3Vector, Oracle 23ai) | External | Built-in JWT, Redis revocation | PostgreSQL/SQLite | Docker, K8s, pip |
| LocalAI | External | External | OIDC (Google, Keycloak, Authentik), NATS JWT, API keys, per-user quotas | PostgreSQL (distributed) | Docker, binary, NATS cluster |
| GigaChat | N/A | N/A | API key | N/A | SaaS only |
| YandexGPT | N/A | N/A | OAuth/Yandex IAM | N/A | SaaS only |

---

## 4. Gap-анализ по осям

### 4.1 Архитектура и масштабируемость

**Текущее состояние Kolibri:**
- 6 серверов, WireGuard mesh, custom Organism v3 orchestration
- SQLite (не масштабируется), single-instance FastAPI
- Нет horizontal scaling, нет load balancing

**Что есть у конкурентов:**
- **LocalAI**: distributed mode на PostgreSQL + NATS для horizontal scaling. NATS JWT auth + TLS/mtls (Jun 2026). Ближайший архитектурный аналог Kolibri.
- **Open WebUI**: Redis-backed session management для horizontal scalability. Multi-worker, multi-node. Redis Sentinel/Cluster/Standalone topology. JWT revocation в Redis с TTL.
- **Dify**: single-instance по умолчанию, но Docker/K8s deployment-ready. PostgreSQL backend.
- **n8n**: single-instance, TypeScript + Vue. Fair-code license限制 коммерческое использование.
- **AnythingLLM**: монолитный NodeJS backend (аналогично монолитному App.jsx Kolibri). Multi-user только в Docker.

**Пробелы:**
| Пробел | Критичность | Конкурент с решением |
|--------|-------------|---------------------|
| SQLite вместо PostgreSQL | 🔴 Критично | Все крупные платформы используют PostgreSQL |
| Нет Docker контейнеризации | 🔴 Критично | Все конкуренты имеют Docker образы |
| Нет horizontal scaling для API | 🟡 Важно | Open WebUI (Redis), LocalAI (NATS) |
| Монолитный фронтенд (~700 строк App.jsx) | 🟡 Важно | Dify, n8n — модульные фронтенды |
| Нет load balancing | 🟡 Важно | Open WebUI (Redis multi-worker) |

**Рекомендации:**
1. **P0**: Миграция SQLite → PostgreSQL (критично для multi-user и масштабирования)
2. **P1**: Docker Compose для всех 6 сервисов (упростит деплой и разработку)
3. **P2**: Разбить App.jsx на feature-модули (chat, canvas, estimates, documents, settings)
4. **P3**: Рассмотреть Redis-backed sessions для horizontal scaling (аналог Open WebUI)

---

### 4.2 RAG-возможности

**Текущее состояние Kolibri:**
- ChromaDB + sentence-transformers
- Базовый semantic search, top-K
- Нет hybrid search, нет reranking, нет advanced chunking

**Что есть у конкурентов:**
- **AnythingLLM**: 9 vector DB backends (LanceDB default + ChromaDB, PGVector, Pinecone, Qdrant, Milvus, Weaviate, Astra, Zilliz). Native embedder + 12+ внешних провайдеров. Самый широкий выбор.
- **Open WebUI**: 9 vector DB (ChromaDB, PGVector, Qdrant, Milvus, Elasticsearch, OpenSearch, Pinecone, S3Vector, Oracle 23ai). Production-grade.
- **FlowiseAI**: 6 стратегий чанкинга (Character, Token, Recursive Character, Markdown, Code, HTML-to-Markdown). Record Manager для дедупликации embeddings при re-upsert. Upsert pipeline: loader → splitter → embedding → vectorStore → recordManager. Лучший RAG pipeline среди drag-n-drop конструкторов.
- **Dify**: встроенный vector DB и embeddings. Поддержка PDF, PPT, common formats.
- **n8n**: 8+ vector store интеграций через LangChain (Pinecone, Qdrant, Milvus, ChromaDB, PGVector, Weaviate, Redis, MongoDB Atlas).

**Пробелы:**
| Пробел | Критичность | Конкурент с решением |
|--------|-------------|---------------------|
| Только 1 vector DB (ChromaDB) | 🟡 Важно | AnythingLLM (9), Open WebUI (9) |
| Нет advanced chunking | 🟡 Важно | FlowiseAI (6 стратегий) |
| Нет hybrid search (BM25 + semantic) | 🟡 Важно | Open WebUI (Elasticsearch), n8n (LangChain retrievers) |
| Нет reranking | 🟢 Нужно | Dify, FlowiseAI (через LangChain) |
| Нет Record Manager (дедупликация) | 🟢 Нужно | FlowiseAI (Record Manager) |
| Один embedding provider | 🟢 Нужно | AnythingLLM (12+ providers) |

**Рекомендации:**
1. **P2**: Добавить Qdrant как второй vector DB (лучше для фильтрации по метаданным, критично для ГОСТ/СНиП поиска)
2. **P2**: Implement hybrid search — BM25 (keyword) + semantic (vector) для точного поиска по нормативным документам
3. **P2**: Advanced chunking — recursive character + semantic splitting для длинных ГОСТ/СНиП документов
4. **P3**: Reranking через cross-encoder для повышения точности RAG

---

### 4.3 AI-агентная система

**Текущее состояние Kolibri:**
- MiMo CLI subprocess на QJNS
- Chain-of-thought planning (ранний этап)
- Tool calling — stub endpoint
- Нет agent memory, нет custom tools

**Что есть у конкурентов:**
- **LocalAI v4.0.0** (Mar 2026): нативная агентная оркестрация — AgentHub, MCP Apps, tool use, RAG, skills. Самая продвинутая агентная система среди inference-платформ.
- **n8n**: AI Agent nodes на LangChain. Vector store nodes, embedding nodes, memory nodes, retriever nodes. Workflow-based agent orchestration.
- **Dify**: визуальный workflow builder для агентов. Agent definitions на LLM Function Calling или ReAct.
- **FlowiseAI**: AgentFlow v2 — drag-n-drop конструктор агентных цепочек на LangChain.

**Пробелы:**
| Пробел | Критичность | Конкурент с решением |
|--------|-------------|---------------------|
| Tool calling — stub | 🔴 Критично | LocalAI (AgentHub, MCP), Dify (workflow) |
| Нет agent memory | 🟡 Важно | n8n (memory nodes), LocalAI (RAG agents) |
| Нет custom tools API | 🟡 Важно | LocalAI (skills), Dify (tool definitions) |
| Нет multi-step planning | 🟡 Важно | n8n (workflow chains), Dify (visual workflow) |
| Нет agent marketplace | 🟢 Нужно | LocalAI (AgentHub) |

**Рекомендации:**
1. **P2**: Реализовать tool calling — базовый набор: файловые операции, web search, calculator, code execution
2. **P2**: Agent memory — per-agent контекст, persisted между вызовами
3. **P3**: Visual workflow builder (аналог Dify/FlowiseAI) — drag-n-drop конструктор цепочек
4. **P3**: Agent marketplace для строительных инструментов (смета, документы, расчёты)

---

### 4.4 UI/UX

**Текущее состояние Kolibri:**
- React 19 SPA, dark/light themes, mobile swipe
- Kolibri Canvas (8 типов карточек)
- KolibriBird mascot (8 состояний)
- Document mode для длинных ответов
- Нет drag-n-drop, нет visual workflow

**Что есть у конкурентов:**
- **Dify**: визуальный workflow builder (drag-n-drop). Модульный React фронтенд. Chatbot, text generator, agent режимы.
- **FlowiseAI**: drag-n-drop конструктор цепочек. Document Stores UI для управления RAG pipeline.
- **Open WebUI**: production-grade UI с 16,810 коммитами. Responsive. Multi-model switching.
- **n8n**: Vue-based workflow editor. 500+ интеграций. Самый mature UI среди workflow-платформ.

**Пробелы:**
| Пробел | Критичность | Конкурент с решением |
|--------|-------------|---------------------|
| Нет visual workflow builder | 🟡 Важно | Dify, FlowiseAI, n8n |
| Монолитный App.jsx | 🟡 Важно | Все крупные платформы — модульные |
| Нет drag-n-drop | 🟢 Нужно | Dify, FlowiseAI |
| Нет multi-model switching UI | 🟢 Нужно | Open WebUI |

**Преимущества Kolibri:**
- **Canvas cards** — уникальный подход: 8 типов карточек прямо в потоке чата. Ни один конкурент не имеет аналога.
- **KolibriBird mascot** — живой AI-компаньон с 8 состояниями. Эмоциональная связь.
- **Document mode** — auto-detection длинных ответов как документов.

**Рекомендации:**
1. **P2**: Разбить App.jsx на feature-модули (chat, canvas, estimates, documents, settings, cluster)
2. **P3**: Visual workflow builder для пользовательских цепочек (аналог Dify)
3. **P3**: Multi-model switching UI (выбор модели прямо в чате)

---

### 4.5 Безопасность

**Текущее состояние Kolibri:**
- ❌ Нет авторизации (ни JWT, ни OAuth, ни SSO)
- ❌ CORS wildcard `allow_origins=["*"]`
- ❌ Нет RBAC
- ❌ Нет audit logs
- ❌ Нет encryption at rest
- ✅ Rate limiting (60 req/min per IP)
- ✅ .env для ключей

**Что есть у конкурентов:**
- **LocalAI v4.1.0** (Apr 2026): OIDC SSO (Google, Keycloak, Authentik), per-user API keys, quotas с predictive analytics. NATS JWT auth + TLS/mtls. Самая продвинутая безопасность.
- **Open WebUI**: JWT authentication, JWT revocation в Redis с TTL. Multi-user. Production-grade.
- **Dify**: built-in JWT/OAuth, multi-tenant workspace.
- **n8n**: built-in auth, credential management, workflow permissions.
- **AnythingLLM**: multi-user (Docker-only), API key management.

**Пробелы:**
| Пробел | Критичность | Конкурент с решением |
|--------|-------------|---------------------|
| Нет авторизации | 🔴 Критично | Все конкуренты (LocalAI OIDC, Open WebUI JWT, Dify OAuth) |
| CORS wildcard `*` | 🔴 Критично | Все конкуренты — whitelist |
| Нет RBAC | 🟡 Важно | LocalAI (per-user quotas), Dify (workspace roles) |
| Нет audit logs | 🟡 Важно | n8n, Dify |
| Нет SSO | 🟢 Нужно | LocalAI (OIDC: Google, Keycloak, Authentik) |
| Нет encryption at rest | 🟢 Нужно | LocalAI (TLS/mtls) |

**Рекомендации:**
1. **P0**: JWT авторизация (register/login/refresh tokens) — минимальный блокер
2. **P0**: CORS whitelist (заменить wildcard)
3. **P0**: SSL/TLS (Let's Encrypt + Nginx reverse proxy)
4. **P2**: RBAC (Admin/User/Viewer) для multi-user
5. **P3**: OIDC SSO (аналог LocalAI — Google, Keycloak)

---

### 4.6 Монетизация и Pricing

**Текущее состояние Kolibri:**
- Нет pricing, нет подписок, нет платежей
- Нет feature gating, нет tier differentiation
- Нет user accounts

**Что есть у конкурентов:**
| Платформа | Self-hosted | Cloud/SaaS | Enterprise |
|-----------|-------------|------------|------------|
| Dify | Free (Apache 2.0) | от $59/mo | Custom pricing |
| FlowiseAI | Free (Apache 2.0) | Starter $35/mo | Custom |
| n8n | Free (fair-code) | от €20/mo | Custom |
| AnythingLLM | Free (MIT) | Cloud available | — |
| Open WebUI | Free (MIT) | — | — |
| LocalAI | Free (MIT) | — | — |

**Модели монетизации конкурентов:**
- **Open-source + Cloud**: Dify, FlowiseAI, n8n (основная модель — self-hosted бесплатно, cloud с доп. фичами)
- **Open-source only**: Open WebUI, LocalAI, AnythingLLM (community-driven, без SaaS)
- **SaaS only**: GigaChat, YandexGPT (pay-per-token)

**Пробелы:**
| Пробел | Критичность | Конкурент с решением |
|--------|-------------|---------------------|
| Нет user accounts | 🔴 Критично | Все конкуренты |
| Нет pricing model | 🟡 Важно | Dify, FlowiseAI, n8n |
| Нет feature gating | 🟢 Нужно | Dify (Free/Pro/Enterprise) |

**Рекомендации:**
1. **P0**: User accounts (необходимо перед монетизацией)
2. **P2**: Freemium модель — self-hosted бесплатно, cloud-managed с доп. фичами (аналог Dify/FlowiseAI)
3. **P3**: Enterprise tier — multi-tenant, SSO, audit logs, priority support

---

### 4.7 Экосистема и документация

**Текущее состояние Kolibri:**
- docs/ с 7 файлами (architecture, api, roadmap, backend, frontend, kolibri-nano, deployment)
- Нет SDK, нет plugin system
- Нет community (проприетарный проект)
- API документация — базовая

**Что есть у конкурентов:**
| Платформа | GitHub Stars | Commits | Релизы | Contributors | SDK | Plugins |
|-----------|-------------|---------|--------|-------------|-----|---------|
| n8n | 193k | — | — | — | JS/Python SDK | 500+ интеграций |
| Open WebUI | 142k | 16,810 | 163 | — | — | Plugin system |
| Dify | 146k | 11,162 | 164 | — | Python/JS SDK | Plugin marketplace |
| AnythingLLM | 61.7k | — | — | — | — | — |
| FlowiseAI | 53.7k | — | — | — | — | LangChain ecosystem |
| LocalAI | 46.9k | — | — | — | — | AgentHub, MCP Apps |

**Пробелы:**
| Пробел | Критичность | Конкурент с решением |
|--------|-------------|---------------------|
| Нет SDK | 🟡 Важно | Dify (Python/JS), n8n (JS/Python) |
| Нет plugin system | 🟡 Важно | Open WebUI, Dify, n8n |
| Нет community | 🟡 Важно | Все open-source конкуренты (46k-193k stars) |
| API документация базовая | 🟢 Нужно | Dify (docs.dify.ai), n8n (docs.n8n.io) |
| Нет contribution guidelines | 🟢 Нужно | Все open-source проекты |

**Рекомендации:**
1. **P2**: Расширить API документацию (OpenAPI/Swagger auto-generation из FastAPI)
2. **P3**: Plugin system для строительных инструментов (estimate templates, document generators)
3. **P3**: SDK для внешних интеграций (Python, JS/TS)
4. **P4**: Рассмотреть open-source стратегию для community building (если цель — рост)

---

### 4.8 DevOps и Deployment

**Текущее состояние Kolibri:**
- SSH + scp deploy script (ручной)
- systemd services на каждом сервере
- Нет Docker, нет K8s
- Нет CI/CD pipeline
- Нет мониторинга (кроме cluster status dashboard)
- Нет логирования (print-based)
- Нет backup/restore

**Что есть у конкурентов:**
| Платформа | Docker | K8s | CI/CD | Monitoring | Logging | Backup |
|-----------|--------|-----|-------|------------|---------|--------|
| Dify | ✅ | ✅ | — | — | — | — |
| Open WebUI | ✅ | ✅ | — | — | — | — |
| n8n | ✅ | ✅ | — | — | — | — |
| LocalAI | ✅ | — | — | — | — | — |
| AnythingLLM | ✅ | — | — | — | — | — |
| FlowiseAI | ✅ | — | — | — | — | — |

**Все конкуренты** имеют Docker образы. Большинство — K8s Helm charts. Ни один не имеет встроенного CI/CD (это ответственность пользователя).

**Пробелы:**
| Пробел | Критичность | Конкурент с решением |
|--------|-------------|---------------------|
| Нет Docker | 🔴 Критично | Все конкуренты |
| Нет CI/CD | 🟡 Важно | Стандарт: GitHub Actions / GitLab CI |
| Print-based logging | 🟡 Важно | Стандарт: structured JSON logging |
| Нет мониторинга | 🟡 Важно | Стандарт: Prometheus + Grafana |
| Нет backup/restore | 🟡 Важно | Стандарт: pg_dump + cron |
| SSH + scp deploy | 🟢 Нужно | Docker Compose / K8s |

**Рекомендации:**
1. **P1**: Docker Compose для всех 6 сервисов (docker-compose.yml с profiles для каждого сервера)
2. **P1**: GitHub Actions CI/CD (lint → test → build → deploy)
3. **P1**: Structured logging (Python logging → JSON format → log aggregation)
4. **P1**: Prometheus + Grafana (CPU, RAM, request latency, queue size, model inference time)
5. **P1**: Automated backup (PostgreSQL pg_dump + ChromaDB snapshot + cron)

---

## 5. Уникальные преимущества Kolibri

<!-- Что есть у Kolibri, чего НЕТ ни у одного конкурента -->

| # | Преимущество | Описание | Конкуренты с аналогом |
|---|-------------|----------|----------------------|
| 1 | Распределённая архитектура 6 серверов | WireGuard mesh, Organism v3, resource-aware routing | Нет прямых аналогов |
| 2 | Rust-ядро Kolibri Nano | Следы, ассоциации, микровеса, персональное ядро | Нет прямых аналогов |
| 3 | Строительная специализация | Estimate Engine, ГОСТ/СНиП RAG, документы для стройки | Нет прямых аналогов |
| 4 | Живой Canvas в чате | 8 типов карточек прямо в потоке чата | Частично у Dify |
| 5 | Десятицифровое персональное ядро | Компактный цифровой отпечаток пользователя | Нет аналогов |
| 6 | LoRA fine-tuning pipeline | Обучение на своих данных, дистилляция | Частично у Dify |

---

## 6. Критические пробелы (блокеры для продакшена)

<!-- Ранг по критичности -->

| # | Пробел | Текущее | Целевое | Impact | Effort | Приоритет |
|---|--------|---------|---------|--------|--------|-----------|
| 1 | Авторизация (JWT/OAuth) | Нет | JWT + refresh tokens | 🔴 Критично | M | P0 |
| 2 | Production DB (PostgreSQL) | SQLite | PostgreSQL | 🔴 Критично | M | P0 |
| 3 | CORS policy | Wildcard `*` | Whitelist origins | 🔴 Критично | S | P0 |
| 4 | SSL/TLS | Нет | Let's Encrypt | 🔴 Критично | S | P0 |
| 5 | CI/CD pipeline | Нет | GitHub Actions | 🟡 Важно | M | P1 |
| 6 | Мониторинг | Cluster dashboard | Prometheus + Grafana | 🟡 Важно | M | P1 |
| 7 | Логирование | Print-based | Structured logging (JSON) | 🟡 Важно | S | P1 |
| 8 | Docker контейнеризация | Нет | Docker Compose | 🟡 Важно | M | P1 |
| 9 | Backup/restore | Нет | Automated backups | 🟡 Важно | M | P1 |
| 10 | Document export (PDF/DOCX) | Stub | Working export | 🟢 Нужно | L | P2 |
| 11 | Agent tool calling | Stub | Working tools | 🟢 Нужно | L | P2 |
| 12 | Hybrid RAG search | Только semantic | BM25 + semantic | 🟢 Нужно | M | P2 |
| 13 | User roles (RBAC) | Нет | Admin/User/Viewer | 🟢 Нужно | M | P2 |
| 14 | Rate limiting per user | Per IP only | Per user + tier | ⚪ Хорошо | S | P3 |
| 15 | Plugin system | Нет | Extension API | ⚪ Хорошо | XL | P3 |

---

## 7. Приоритетный Roadmap доработок

### Phase 5.5: Безопасность и продакшен (P0) — 2-3 недели
- [ ] JWT авторизация (register/login/refresh)
- [ ] PostgreSQL миграция (замена SQLite)
- [ ] CORS whitelist (вместо wildcard)
- [ ] SSL/TLS (Let's Encrypt + Nginx)
- [ ] Environment-based config (.env → config module)

### Phase 5.6: DevOps (P1) — 2 недели
- [ ] Docker Compose для всех сервисов
- [ ] CI/CD pipeline (GitHub Actions: lint → test → build → deploy)
- [ ] Structured logging (JSON, log levels)
- [ ] Prometheus + Grafana мониторинг
- [ ] Automated backup (PostgreSQL + ChromaDB)

### Phase 6: RAG и агенты (P2) — 3-4 недели
- [ ] Hybrid RAG (BM25 + semantic reranking)
- [ ] Advanced chunking (recursive, semantic)
- [ ] Agent tool calling (реальные инструменты)
- [ ] Agent memory (per-agent context)
- [ ] Document export (PDF, DOCX, XLSX)

### Phase 7: UI/UX и экосистема (P2-3) — 3-4 недели
- [ ] Visual workflow builder (drag-n-drop)
- [ ] Plugin/extension system
- [ ] Multi-user workspace
- [ ] Mobile PWA optimization
- [ ] SDK для внешних интеграций

### Phase 8: Оркестрация серверов — 2 недели
- [ ] MacBook → 6 серверов orchestration protocol
- [ ] Auto-deploy модулей на целевые серверы
- [ ] Parallel development task distribution
- [ ] Health check и auto-recovery

---

## 8. Рекомендации по позиционированию

### 8.1 Целевая аудитория
- Строительные компании (сметы, документы, расчёты, ГОСТ/СНиП)
- Малые команды, нуждающиеся в self-hosted AI (приватность, контроль данных)
- Рынок России/СНГ (русский язык, локальные нормативы, отсутствие аналогов)

### 8.2 УТП (Unique Value Proposition)

**Kolibri AI — единственная self-hosted AI-платформа с:**
1. **Строительной специализацией** — Estimate Engine, ГОСТ/СНиП knowledge base, строительные документы. Ни один конкурент не имеет отраслевой специализации.
2. **Распределённой архитектурой** — 6 серверов, WireGuard mesh, resource-aware routing. Ближайший аналог — LocalAI distributed mode, но без UI/канваса.
3. **Локальным ядром поведенческого моделирования** — Rust-based Kolibri Nano: следы, ассоциации, микровеса, персональное ядро. Уникальная технология.
4. **Живым Canvas** — 8 типов карточек прямо в потоке чата. Ни один конкурент не имеет аналога.
5. **Полной приватностью** — всё работает локально, данные не покидают инфраструктуру.

### 8.3 Конкурентная стратегия

**Не конкурировать с:**
- Dify/Open WebUI по размеру community (146k/142k stars) — это бессмысленно
- n8n по workflow automation (193k stars, 500+ интеграций)
- GigaChat/YandexGPT по cloud API (они SaaS, вы self-hosted)

**Конкурировать по:**
- Отраслевая глубина (строительство) vs горизонтальные платформы
- Приватность (self-hosted, WireGuard) vs cloud-решения
- Персонализация (Kolibri Nano) vs stateless chatbots
- Российский рынок (ГОСТ/СНиП, русский язык) vs англоцентричные конкуренты

**Позиционирование:**
> «Kolibri AI — self-hosted AI-платформа для строительной отрасли. Один чат, живой канвас, локальное ядро. Сметы, документы, расчёты — всё в одном месте, под полным контролем.»

---

## 9. Источники

### Open-source платформы (первичные)
1. https://github.com/n8n-io/n8n — 193k stars, 58.6k forks, v2.26.5 (Jun 2026)
2. https://github.com/mudler/LocalAI — 46.9k stars, v4.4.3 (Jun 2026)
3. https://github.com/langgenius/dify — 146k stars, 22.9k forks, v1.14.2 (May 2026)
4. https://docs.flowiseai.com/using-flowise/document-stores — 6 chunking strategies
5. https://docs.flowiseai.com/integrations/langchain/vector-stores — ChromaDB integration
6. https://github.com/Mintplex-Labs/anything-llm — 61.7k stars, v1.14.1 (Jun 2026)
7. https://github.com/open-webui/open-webui — 142k stars, 20.4k forks, v0.9.6 (Jun 2026)

### Российские платформы
8. https://developers.sber.ru/portal/products/gigachat-api — GigaChat API
9. https://yandex.ru — YandexGPT
10. https://aragorn.ai — RAG-платформа

### Pricing и enterprise
11. https://dify.ai/pricing
12. https://flowiseai.com/pricing
13. https://n8n.io/pricing/
14. https://github.com/danny-avila/LibreChat
15. https://anythingllm.com/pricing

### DevOps и deployment
16. https://docs.dify.ai/en/getting-started/install-self-hosted
17. https://docs.flowiseai.com/using-flowise/agentflowv2.md

### AI Agent системы
18. LocalAI v4.0.0 release notes — AgentHub, MCP Apps, tool use
19. LocalAI v4.1.0 release notes — OIDC SSO, per-user quotas

### Ограничения анализа
- LibreChat — факты не собраны (не проанализирован)
- Pricing для коммерческих tiers — данные приблизительные
- Российские платформы — неполные данные (SaaS API, не self-hosted)
- Все данные — snapshot на Jun 17 2026
- Нет данных о real-world performance (latency, throughput)

---

## Приложение A: Сводная матрица сравнения

| Ось | n8n | LocalAI | Dify | FlowiseAI | AnythingLLM | Open WebUI | Kolibri AI |
|---|---|---|---|---|---|---|---|
| **Stars** | 193k | 46.9k | 146k | 53.7k | 61.7k | 142k | MVP |
| **Релиз** | v2.26.5 Jun'26 | v4.4.3 Jun'26 | v1.14.2 May'26 | Apr'26 | v1.14.1 Jun'26 | v0.9.6 Jun'26 | MVP |
| **Distributed** | ✗ | ✓ (PostgreSQL+NATS) | ✗ | ✗ | ✗ (Docker only) | ✓ (Redis) | ✓ (WireGuard mesh) |
| **Vector DB** | 8+ (via LangChain) | external | built-in | ChromaDB+others | 9 backends | 9 backends | ChromaDB only |
| **Embeddings** | via LangChain | external | built-in | via LangChain | native+12 external | external | external |
| **AI Agents** | ✓ (LangChain) | ✓ (AgentHub, MCP) | ✓ (workflow) | ✓ (AgentFlow) | ✗ | ✗ | stub |
| **Chunking** | via LangChain | N/A | built-in | 6 strategies | built-in | built-in | basic |
| **Auth** | built-in | OIDC+API keys+quotas | built-in | built-in | Docker-only | built-in | ✗ |
| **License** | fair-code | MIT | Apache 2.0 | Apache 2.0 | MIT | MIT | proprietary |
| **Multi-tenant** | ✗ | ✓ (v4.1.0) | ✓ | ✗ | Docker-only | ✓ | ✗ |
| **Строит. специализация** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |
| **Canvas/Workspace** | workflow editor | ✗ | visual builder | drag-n-drop | ✗ | ✗ | ✓ (8 card types) |
| **Rust core** | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ |

## Приложение B: Pricing сравнение

| Платформа | Self-hosted | Cloud/Pro | Enterprise |
|-----------|-------------|-----------|------------|
| Dify | Free (Apache 2.0) | от $59/mo | Custom |
| FlowiseAI | Free (Apache 2.0) | Starter $35/mo | Custom |
| n8n | Free (fair-code) | от €20/mo | Custom |
| AnythingLLM | Free (MIT) | Cloud available | — |
| Open WebUI | Free (MIT) | — | — |
| LocalAI | Free (MIT) | — | — |
| GigaChat | N/A | Pay-per-token (Lite/Pro/MAX) | Custom |
| YandexGPT | N/A | Pay-per-token via Yandex Cloud | Custom |
| **Kolibri AI** | **Free (proprietary)** | **Нет** | **Нет** |

## Приложение C: Community и экосистема

| Платформа | Stars | Forks | Commits | Релизы | Язык | Интеграции |
|-----------|-------|-------|---------|--------|------|------------|
| n8n | 193k | 58.6k | — | — | TypeScript 91% | 500+ |
| Open WebUI | 142k | 20.4k | 16,810 | 163 | Python | 9 vector DB |
| Dify | 146k | 22.9k | 11,162 | 164 | Python | Plugin marketplace |
| AnythingLLM | 61.7k | — | — | — | NodeJS | 9 vector DB, 12+ embedders |
| FlowiseAI | 53.7k | — | — | — | NodeJS | LangChain ecosystem |
| LocalAI | 46.9k | — | — | — | Go | 36+ backends, AgentHub |
| **Kolibri AI** | **MVP** | — | — | — | **Python + Rust** | **MiMo CLI** |
