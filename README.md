# Колибри — AI Workspace Platform

AI-платформа для строительных смет, документов и агентов.

## Быстрый старт

```bash
# Frontend
cd kolibri-v2
npm install
npm run dev        # → http://localhost:3000

# Backend
cd kolibri-backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # → http://localhost:8000
```

## Архитектура

```
kolibri-v2/          React 19 + Vite + Tailwind + shadcn/ui
kolibri-backend/     FastAPI + SQLAlchemy + SQLite
```

### Frontend
- **Routing**: react-router v7 (HashRouter)
- **UI**: shadcn/ui + CSS custom properties
- **API client**: `src/lib/api.ts` — typed fetch wrapper

### Backend
- **Database**: SQLAlchemy ORM + Alembic migrations
- **Calculator**: Decimal arithmetic engine (34 golden tests)
- **PDF**: WeasyPrint HTML→PDF
- **AI**: 7 провайдеров (Kimi, DeepSeek, MiMo, CFBT)

## Страницы

| Страница | Описание |
|----------|----------|
| Чат | AI-чат с reasoning, actions, провайдер fallback |
| Библиотека | Поиск, фильтры, grid/list view |
| Сметы | Редактор, AI-анализ, PDF/CSV/JSON экспорт |
| Документы | Rich-text, шаблоны, PDF/DOCX экспорт |
| Агенты | CRUD, пауза/старт, управление задачами |
| Серверы | Dashboard, управление нодами |
| Настройки | Профиль, тема, горячие клавиши |

## API

Все endpoints под `/api/v1/`:

| Endpoint | Описание |
|----------|----------|
| `POST /chat` | AI-чат |
| `GET/POST /estimates` | CRUD смет |
| `GET/POST /documents` | CRUD документов |
| `GET /library` | Библиотека |
| `GET/POST /agents` | Управление агентами |
| `GET /nodes` | Серверы |
| `POST /search` | Глобальный поиск |
| `POST /auth/login` | Авторизация |

## Каталог

1,048,459 позиций строительных материалов:
- 1,082 города России с региональными коэффициентами
- 85 категорий (электрика, HVAC, сантехника, инструменты...)
- 10 JSON-файлов с ценами + 4 скрапинга (Yandex Market, Leroy Merlin, Maxidom, VseInstrumenti)

## Стек

**Frontend**: React 19, TypeScript, Vite 7, Tailwind 3, shadcn/ui, lucide-react
**Backend**: Python 3.12, FastAPI, SQLAlchemy, Pydantic v2, WeasyPrint, openpyxl
**AI**: Kimi K2.7, DeepSeek v4, MiMo v2.5, CFBT proxy
**DevOps**: Docker Compose, GitHub Actions CI

## Команды

```bash
npm run build      # tsc -b && vite build
npm run lint       # ESLint
npm run dev        # Vite dev server :3000

# Backend
python -m pytest app/tests/ -v   # 34 golden tests
```
