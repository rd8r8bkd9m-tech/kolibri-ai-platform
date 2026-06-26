# КОЛИБРИ — План исполнения

## Артефакты на входе
- Master Build Directive (полная спецификация)
- Product Design Spec (UI/UX детали)
- 22 скриншота (собственный экран Колибри + референсы Gemini)
- Фирменная птичка (asset)

## Этапы

### Phase 0 — FREEZE LEGACY
- [x] Сохранить загруженные файлы как reference assets
- [x] Создать SHA-256 manifest загруженных файлов

### Phase 1 — FOUNDATION
- [ ] Создать monorepo scaffold (структура из секции 9)
- [ ] Design system: CSS tokens, цвета, типографика, радиусы, отступы
- [ ] API contracts: Zod/Pydantic схемы
- [ ] Auth foundation
- [ ] Database schema (PostgreSQL + SQLite dev mode)
- [ ] Docker compose для локальной разработки
- [ ] CI pipeline (GitHub Actions)

### Phase 2 — PRODUCT VERTICAL SLICE (Чат → Смета → PDF)
- [ ] Главный экран (приветствие + птичка + поле ввода)
- [ ] Боковое меню
- [ ] AI-чат (история, сообщения, quick actions)
- [ ] Птичка состояния (все 9 состояний)
- [ ] Создание сметы из чата
- [ ] Редактор смет (mobile + desktop)
- [ ] Calculator engine (100% arithmetic accuracy)
- [ ] PDF generation (Playwright/Chromium)
- [ ] Библиотека (хранение, фильтры, поиск)
- [ ] PWA setup
- [ ] Golden tests (30+ cases)

### Phase 3 — DOCUMENTS
- [ ] Шаблоны документов
- [ ] Rich-text редактор
- [ ] DOCX/HTML/TXT export
- [ ] Связь смет ↔ документы

### Phase 4 — REMOTE CONTROL
- [ ] Primary server integration
- [ ] Telegram bot
- [ ] Control Plane scaffold

### Phase 5+ — AGENT FACTORY, SCALE, PRODUCTION
- Последующие фазы по мере прохождения Phase 2-4

## Скиллы
- Phase 1-3: `vibecoding-webapp-swarm` (React + TS + Vite + Tailwind)
- Phase 4+: `vibecoding-general-swarm` (backend, infra)
- Артефакты: `webapp-building-swarm`

## Начало: Phase 1 — Foundation
Начинаем немедленно. Первый шаг: monorepo scaffold + design system.
