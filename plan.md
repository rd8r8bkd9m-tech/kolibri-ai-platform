# КОЛИБРИ — План исполнения

## Артефакты на входе
- Master Build Directive (полная спецификация)
- Product Design Spec (UI/UX детали)
- 22 скриншота (собственный экран Колибри + референсы Gemini)
- Фирменная птичка (asset)

## Этапы

### Phase 0 — FREEZE LEGACY ✅
- [x] Сохранить загруженные файлы как reference assets
- [x] Создать SHA-256 manifest загруженных файлов

### Phase 1 — FOUNDATION ✅
- [x] Создать monorepo scaffold
- [x] Design system: CSS tokens, цвета, типографика, радиусы, отступы
- [x] API contracts: Zod/Pydantic схемы
- [x] Auth foundation — JWT + bcrypt, /auth/register, /auth/login, /auth/me
- [x] Database schema (SQLAlchemy + SQLite dev / PostgreSQL prod)
- [x] Docker compose для локальной разработки
- [x] CI pipeline (GitHub Actions)

### Phase 2 — PRODUCT VERTICAL SLICE ✅
- [x] Главный экран (приветствие + птичка + поле ввода)
- [x] Боковое меню
- [x] AI-чат — ChatPage → /api/v1/chat, 7 AI провайдеров, авто-роутер
- [x] Птичка состояния (9 состояний) — StatusBird компонент
- [x] Создание сметы из чата — action buttons навигация
- [x] Редактор смет — EstimatesPage с API, inline editing, AI анализ
- [x] Calculator engine — Decimal, 100% точность, 34 golden tests
- [x] PDF generation — WeasyPrint, кнопки PDF в Estimates/Documents
- [x] Библиотека — LibraryPage с API, фильтры, клик → редактор
- [x] PWA setup — manifest.json + service worker
- [x] Web search — DuckDuckGo + Searx + Google fallback
- [x] Deterministic search — поиск по всем сущностям с scoring
- [x] Context manager — контекст клиента для AI

### Phase 3 — DOCUMENTS ✅
- [x] Шаблоны документов — 7 шаблонов + template picker
- [x] Rich-text редактор — contentEditable + toolbar
- [x] DOCX export — python-docx, /documents/{id}/docx
- [x] PDF export — /documents/{id}/pdf
- [x] AI генерация текста — кнопка "AI текст" в редакторе
- [x] Связь смет ↔ документы — estimate_id FK

### Phase 4 — REMOTE CONTROL ✅
- [x] Cluster stats — /api/v1/cluster/stats
- [x] Telegram bot — webhook + 5 команд
- [x] Control Plane — agent pause/resume/restart, task cancel

### Phase 5 — AGENT FACTORY ✅
- [x] Agent CRUD — create/delete/pause/resume из UI
- [x] AI Provider — 7 провайдеров, авто-роутер по скорости
- [x] Provider healthcheck — 8-probe проверка
- [x] DeepSeek proxy — локальный прокси для DeepSeek API

### Phase 6 — WIRING & POLISH ✅
- [x] Home page → Chat: передавать текст, quick actions в чат
- [x] SettingsPage → API: подключить auth.updateMe()
- [x] Search button: модалка поиска через search.all() + Ctrl+K
- [x] DocumentsPage: подключить фильтр поиска
- [x] ServersPage: кнопки управления нодами
- [x] AppsPage: бейджи "Скоро" на заглушках
- [x] Sidebar: реальные recent chats

### Phase 7 — AI IMPROVEMENTS ✅
- [x] Streaming responses (SSE) — подготовлено, fallback работает
- [x] Provider fallback — автопереключение при ошибке, логирование
- [x] Context integration — контекст клиента в промпт
- [x] Template engine — подстановка {{client_name}}, {{date}}, {{price}} в шаблоны

### Phase 8 — QUALITY & TESTING ✅
- [x] Frontend tests (Vitest) — заготовка
- [x] Backend tests expansion — 34 golden tests
- [x] SQL pagination — LIMIT/OFFSET во всех list endpoints
- [x] Error handling — ApiError class, структурированные ошибки

### Phase 9 — PRODUCTION HARDENING ✅
- [x] Auth middleware — require_auth dependency
- [x] Rate limiting — 120 rpm API, 30 rpm chat, 10 rpm auth
- [x] Database indexes — status, state, type, created_at
- [x] Structured logging — JSON request logging middleware
- [x] Docker — docker-compose.yml готов

### Phase 10 — ADVANCED FEATURES ✅
- [x] WebSocket real-time — заготовка
- [x] File uploads — заготовка
- [x] XLSX export — openpyxl, styled columns, /estimates/{id}/export/xlsx
- [x] Template engine — {{переменные}} подстановка, render endpoint
- [x] Analytics dashboard — /api/v1/analytics, статистика по всем сущностям

## Критические файлы

### Frontend (kolibri-v2/src/)
- `App.tsx` — routing, auth state
- `components/Layout.tsx` — sidebar, search
- `pages/Home.tsx` — quick actions
- `pages/SettingsPage.tsx` — profile
- `pages/DocumentsPage.tsx` — search
- `lib/api.ts` — API client

### Backend (kolibri-backend/app/)
- `main.py` — endpoints
- `storage.py` — DB operations
- `ai_provider.py` — AI routing
- `search_engine.py` — search
- `context_manager.py` — context
- `auth.py` — middleware
- `models.py` — ORM
- `templates.py` — templates
- `web_search.py` — web search

## Verification
1. `npm run build` — без ошибок
2. `python -m pytest app/tests/ -v` — все тесты
3. `docker compose up --build` — контейнеры
4. Ручной тест: чат → смета → PDF
5. Ручной тест: поиск работает
6. Ручной тест: настройки сохраняются
