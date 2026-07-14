# AGENTS.md — Kolibri

## Mandatory toolchain policy

- Use only the versions pinned in `toolchains.json`; today that means Node.js
  24.18.0 LTS, Python 3.14.6 and Rust 1.97.0.
- EOL, preview, beta, nightly and unpinned system toolchains are forbidden for
  builds, tests and releases.
- A version update starts by updating `toolchains.json`, `.node-version`,
  `.python-version`, `rust-toolchain.toml`, CI and container bases in one
  reviewed commit. Official checksums or signatures must be verified before a
  runtime is installed on Home or a worker.
- Production never follows an unbounded `latest` tag. The newest supported
  stable/LTS release is pinned, tested on canary, then rolled out to the fleet.
- A release is blocked when its build/runtime version differs from the pinned
  manifest or when a canonical node reports an EOL toolchain.

## Project overview

Колибри (Kolibri) is an AI workspace platform for construction estimates, documents, and agents. Two main parts:

- **`kolibri-v2/`** — React SPA frontend (Vite + React 19 + TypeScript + Tailwind v3 + shadcn/ui)
- **`kolibri-backend/`** — FastAPI Python backend (Pydantic v2, WeasyPrint PDF)

No monorepo tool — these are independent projects. Root `plan.md` and `plan-phase2.md` track the development roadmap.

## Commands

```bash
# Frontend (run from kolibri-v2/ with Node from toolchains.json)
npm ci
npm run dev        # Vite dev server on port 3000 (proxies /api → :8000)
npm run build      # tsc -b && vite build
npm run lint       # ESLint

# Backend (run from kolibri-backend/ with Python from toolchains.json)
python3 -m venv .venv && source .venv/bin/activate
pip install --require-hashes -r requirements.lock
uvicorn app.main:app --reload   # API on :8000

# Docker (from repo root)
docker compose up --build       # Frontend :80, Backend :8000, PostgreSQL :5432

# Tests (from kolibri-backend/)
python -m pytest app/tests/ -v  # 34 golden tests
```

Both servers must be running for the app to work. Vite proxies `/api/*` to `http://127.0.0.1:8000`.

No test runner configured in frontend. Backend tests directory exists at `kolibri-backend/app/tests/` but is empty.

## Architecture

### Frontend (`kolibri-v2/src/`)

- **Routing**: `react-router` v7 with `HashRouter` (not BrowserRouter). Routes defined in `App.tsx`.
- **Path alias**: `@/` maps to `./src/` (configured in tsconfig + vite config).
- **Layout**: `Layout.tsx` renders sidebar (desktop) + drawer (mobile) + `<Outlet />`. Home page hides the sidebar.
- **Pages**: `pages/` — Home, ChatPage, LibraryPage, AppsPage, EstimatesPage, DocumentsPage, AgentsPage, ServersPage, SettingsPage.
- **UI components**: `components/ui/` — 50+ shadcn/ui components (new-york style). Import as `@/components/ui/button`.
- **API client**: `src/lib/api.ts` — typed fetch wrapper for all backend endpoints. Frontend pages import from here.
- **Icons**: `lucide-react` throughout.

### Design system

CSS custom properties in `index.css`, NOT Tailwind theme tokens. The Kolibri-specific design uses `var(--xxx)` directly:

- Colors: `var(--bg-primary)`, `var(--text-secondary)`, `var(--accent-teal)`, etc.
- Typography: `var(--font-sans)`, `var(--font-mono)`
- Spacing: `var(--radius-sm/md/lg)`, `var(--sidebar-width)`
- Shadows: `var(--shadow-sm/md/lg)`

shadcn/ui components use HSL-based `--primary`, `--secondary`, etc. from `tailwind.config.js`. Both systems coexist — new Kolibri-specific UI uses CSS vars, shadcn components use Tailwind theme.

### Backend (`kolibri-backend/`)

- **Database**: SQLAlchemy ORM + Alembic migrations. SQLite for dev (`kolibri.db`), PostgreSQL for production via `DATABASE_URL` env var.
- **Storage**: `storage.py` — `DBStorage` class wraps all DB operations. `seed_db()` populates sample data on startup.
- **Calculator**: `calculator.py` — deterministic Decimal arithmetic engine. All money uses `Decimal`, rounding is `ROUND_HALF_UP`. Allowed units defined in `ALLOWED_UNITS`.
- **PDF**: `pdf_generator.py` — WeasyPrint-based HTML→PDF.
- **Schemas**: `schemas.py` — Pydantic v2 models. `PositionResponse` uses `sum` field with alias `sum_` (Python reserved word).
- **CORS**: Wide open (`allow_origins=["*"]`) for dev.
- **API prefix**: All endpoints under `/api/v1/`.

## Key conventions

- **Language**: UI is in Russian. All labels, messages, placeholder text use Cyrillic.
- **CSS approach**: Use `var(--xxx)` for Kolibri-brand elements. Use Tailwind utility classes for layout/spacing. Use shadcn `cn()` for conditional classes.
- **No test framework**: Neither frontend nor backend has tests configured. When adding tests, choose and configure explicitly.
- **No CI/CD**: Not set up yet. `plan.md` references GitHub Actions as future work.
- **Dev tooling**: `plugin-inspect-react-code` adds `data-inspect` attributes for debugging React components in dev mode.

## Gotchas

- `tailwind.config.js` uses `module.exports` (CJS) while the rest of the project is ESM — this is intentional, Tailwind v3 requires it.
- `PositionResponse.sum` has `alias="sum_"` — when reading from dict, use key `"sum"`, not `"sum_"`.
- Backend seed data uses `random.seed(i)` for deterministic node/task generation — don't change the seed order.
- `HashRouter` means URLs have `#/` prefix. If you need clean URLs, that's a migration task.
- `base: './'` in vite.config.ts makes build output use relative paths — important for static hosting.

## Files to read first

- `plan.md` — full project roadmap and phase structure
- `kolibri-v2/src/App.tsx` — route definitions
- `kolibri-v2/src/components/Layout.tsx` — sidebar/navigation structure
- `kolibri-v2/src/index.css` — complete design token system
- `kolibri-v2/src/lib/api.ts` — typed API client for all backend endpoints
- `kolibri-backend/app/main.py` — all API endpoints, data models, seed logic
- `kolibri-backend/app/calculator.py` — estimate calculation engine
- `kolibri-backend/app/storage.py` — DB storage layer (SQLAlchemy)
- `kolibri-backend/app/models.py` — ORM models
- `kolibri-backend/app/tests/test_calculator.py` — 34 golden tests
