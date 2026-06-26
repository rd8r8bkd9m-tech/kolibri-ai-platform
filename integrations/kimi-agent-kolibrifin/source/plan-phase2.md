# КОЛИБРИ — Phase 2: Backend + PDF + Tests + CI/CD

## Что уже сделано
- Frontend SPA (8 страниц, React + TypeScript + Tailwind)
- Design system с CSS tokens
- UI компоненты (sidebar, chat, status indicator, etc.)

## Что нужно доделать

### Phase 8 — Backend API
- FastAPI app в `apps/api/`
- PostgreSQL schema (estimates, documents, tasks, agents, nodes, users)
- Pydantic models + Zod contracts
- CRUD endpoints: estimates, documents, library items
- Calculator engine (детерминированный, 100% точность)
- Alembic migrations
- Docker Compose (API + PostgreSQL + Redis)
- PDF generation endpoint (HTML → Playwright → PDF)
- Golden estimate tests (30+ cases)
- GitHub Actions CI/CD

### Phase 9 — Integration
- Frontend → Backend API calls
- Real data persistence
- PDF download from UI
- File export (XLSX, CSV, JSON)
