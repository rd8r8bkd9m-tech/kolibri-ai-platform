# Desktop-First Architecture & UX Audit

## 1. Inventory of Routes and Contracts

### Аудит Маршрутов (Backend FastAPI)

#### Auth & Sessions
- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `GET /v1/session`
- `POST /v1/auth/logout`

#### Identity & Profile
- `GET /v1/profile`
- `PATCH /v1/profile`
- `PUT /v1/profile/agent-profile`
- `PUT /v1/profile/model-settings`

#### Project & Estimates
- `GET /v1/projects/{project_id}/estimate`
- `PATCH /v1/projects/{project_id}/estimate`
- `GET /v1/projects/{project_id}/estimate/versions`
- `PATCH /v1/projects/{project_id}/estimate/rows`
- `GET /v1/projects/{project_id}/estimate/generation`
- `POST /v1/projects/{project_id}/estimate/document-pack`
- `GET /v1/projects/{project_id}/estimate/export/{export_format}`

#### Chat & AI Generation
- `GET /v1/chat/threads`
- `PATCH /v1/chat/threads/{thread_id}`
- `GET /v1/chat/threads/{thread_id}/messages`
- `POST /v1/chat/ag-ui`
- `POST /v1/chat/runs/{run_id}/cancel`

#### Agent Control Plane (Admin)
- `GET /v1/platform-admin/models`
- `POST /v1/platform-admin/models`
- `POST /v1/platform-admin/models/{model_id}/test`
- `GET /v1/platform-admin/trusted-agents/profiles`

### Существующие контракты
В проекте реализованы жестко типизированные JSON-схемы (находятся в папке `contracts/v1/`), которые покрывают `a2a`, `agents`, `artifacts`, `cases`, `chat`, `product`, `provider-execution`, `tasks`.

---

## 2. Gap Analysis (Анализ разрывов)

### 2.1. UX и Разрешения Экрана
**Текущее состояние:** 
Интерфейс в `app/` адаптирован под гибридное использование с мобильным клиентом. Однако, как показал тест с масштабом 200% (`window.matchMedia("(max-width: 959px)")`), логика редиректа жестко связывает узкие экраны с мобильным приложением Expo.
**Разрыв:** 
- Desktop web app должен корректно работать при zoom 200% без принудительного редиректа на `?client=mobile`.
- Отсутствует оптимизированная левая навигационная панель, поддерживающая сворачивание (collapsible sidebar) и доступность через клавиатуру.

### 2.2. Табличный редактор смет
**Текущее состояние:** 
Смета рендерится, но не готова к нагрузкам B2B (1000+ строк) с плавным редактированием без блокировки UI.
**Разрыв:** 
- Отсутствует виртуализация строк (`@tanstack/react-virtual` или аналог).
- Не реализован Batch Edit и Copy/Paste из Excel/Spreadsheet.
- Конфликты ревизий (Optimistic Concurrency) необходимо выводить в удобный интерфейс разрешения конфликтов.

### 2.3. Agent Control Plane
**Текущее состояние:** 
Роуты `platform-admin` существуют, но UI-страницы для управления AI провайдерами либо минимальны, либо не соответствуют строгим требованиям безопасности.
**Разрыв:** 
- Необходим специализированный интерфейс для администрирования моделей и агентов.
- Необходимо скрыть токены (только статус `hasSecret`).
- Требуется безопасный компонент `Test Connection` с обработкой SSRF (на бекэнде) и понятным выводом latency в UI.

### 2.4. Доступность (Accessibility WCAG 2.2 AA)
**Разрыв:** 
- Необходимо внедрить строгую иерархию заголовков и ARIA-labels для всех диалогов и таблиц.
- Требуется реализация Focus Trap для `dialogs` и глобальных шорткатов (`Ctrl+K`, `Ctrl+S`).

### 2.5. OpenAPI 3.1 & API Standards
**Разрыв:** 
- Backend выдает `openapi.json`, но он не формализован с точки зрения примеров (examples), стандартных `Error Body` конвертаций для клиента, пагинации и Rate-limit заголовков.

---

## 3. Этапы реализации (PR Breakdown)

Разработка разбивается на следующие независимые Pull Requests (PR):

### PR 1: Настройка OpenAPI 3.1, Security Headers и Инфраструктуры
- Формализация Swagger/OpenAPI спецификации, добавление стандартизированных схем ошибок и пагинации.
- Настройка Content-Security-Policy (CSP) в Next.js `next.config.ts` и CORS заголовков.
- Внедрение тестов безопасности API (SSRF block, session expiry).

### PR 2: Desktop Layout & Keyboard Navigation
- Переработка корневого Layout (`app/app/layout.tsx`): добавление сворачиваемого Sidebar и Context Panel.
- Добавление системы Keyboard Shortcuts (`Ctrl+K`, `Ctrl+S`) через глобальные хуки.
- Разделение редиректа для узких экранов: отвязка Zoom 200% от мобильного клиента (корректировка логики `window.matchMedia` в `MobileEnvironment`).
- Прохождение автоматизированных тестов axe-core.

### PR 3: Высокопроизводительный Редактор Смет (Data Grid)
- Внедрение виртуализации строк для отображения до 1000 элементов без потери кадров.
- Реализация Keyboard-only навигации по ячейкам таблиц.
- Добавление функций Copy/Paste из Spreadsheet.
- Внедрение UI для Optimistic Concurrency и разрешения конфликтов версий.

### PR 4: Advanced Chat & Generation
- Доработка интерфейса чата (отмена генерации, retry, streaming progress, виртуализация длинных диалогов).
- Обработка rate limit / timeout ошибок с понятным UX.

### PR 5: Agent Control Plane
- Разработка UI страниц для `platform-admin`.
- Создание/редактирование/тестирование провайдеров (Codex, OpenAI, HTTP Agent).
- Сокрытие секретов (`hasSecret`), отображение latency, confirmation dialogs для удалений.

### PR 6: Документы и Экспорт
- Настройка экспорта (PDFMake), печатных версий документов (КС-2, КС-3, Договоры).
- Lazy loading модулей экспорта для сокращения `initial JS payload`.

### PR 7: Финализация QA, E2E и Lighthouse
- Написание полного покрытия через React Testing Library и Playwright.
- Оптимизация Web Vitals (LCP < 2.5s, INP < 200ms).
- Настройка GitHub Actions (nightly cross-browser, Lighthouse CI).
