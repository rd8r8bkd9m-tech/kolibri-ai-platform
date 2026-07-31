# Contributing to Kolibri V3

## Стек (2026)

| Слой | Технологии |
|------|-----------|
| Frontend | Next.js 16, React 19, TypeScript 6/7, Tailwind CSS 4, shadcn/ui |
| Backend | Python 3.10+, FastAPI, SQLite (raw SQL, без ORM) |
| AI Runtime | AG-UI, assistant-ui |
| **Tooling** | **Biome** (lint + format), **Ruff** (Python), **lefthook** (git hooks), **uv** (Python deps) |

## Правила разработки

### Общие

1. **Один файл — одна ответственность.** Строго не более 300 строк.
2. **Комментарии** — только WHY, не WHAT. Код должен быть самодокументирован.
3. **Дублирование** лучше premature abstraction. Три одинаковых строки допустимы.
4. **Обработка ошибок** — на границах системы (API, ввод пользователя). Внутри доверяем типам.

### TypeScript / Frontend

- **Именование:** `camelCase` для переменных/функций, `PascalCase` для компонентов/типов, `kebab-case` для файлов.
- **Компоненты:** `function ComponentName({ prop }: PropsType)` — именованные экспорты.
- **Нет `any`** — всегда конкретный тип. Если неизвестно — `unknown` + type guard.
- **Imports:** абсолютные пути через `@/`, сортировка автоматическая (Biome).
- **State:** Zustand для глобального, `useState` для локального. Context — только для темы/провайдеров.

### Python / Backend

- **Именование:** `snake_case` для всего, `PascalCase` для классов.
- **Роуты** — тонкие контроллеры: валидация → вызов сервиса → ответ.
- **Бизнес-логика** — в `services/`, без импортов из FastAPI.
- **SQL** — параметризованные запросы, никогда строковая конкатенация.
- **Типизация** — аннотации на всех функциях, `pyright` для проверки.

### Git

- **Ветки:** `feature/описание`, `fix/описание`, `chore/описание`
- **Коммиты:** [Conventional Commits](https://www.conventionalcommits.org/)
  - `feat: добавить экспорт сметы в PDF`
  - `fix: исправить дублирование сессий`
  - `chore: обновить зависимости`
  - `refactor: выделить сервис авторизации`
- **Один коммит = одна логическая изменения.** Не смешивать фичи и рефакторинг.

## Запуск

```bash
npm run dev              # полный стек (backend + frontend)
npm run lint             # проверка Biome (lint + format)
npm run lint:fix         # автоисправление Biome
npm run format           # форматирование Biome
npm run check            # полная проверка + автоисправление
npm run typecheck        # проверка типов TypeScript
npm run test             # тесты frontend
npm run backend:lint     # проверка Ruff (Python)
npm run backend:format   # форматирование Ruff (Python)

cd backend && python -m pytest  # тесты backend
```

## Pre-commit хуки (lefthook)

При каждом коммите автоматически запускаются:
- **Biome** — линтинг и форматирование `.ts/.tsx/.json/.css`
- **Ruff** — линтинг и форматирование `.py`
- **Conventional Commits** — проверка формата сообщения коммита

Если хук падает — исправьте ошибки перед повторным коммитом.

## Code Review

- Каждый PR проходит ревью перед мержем.
- Ревьюер проверяет: логику, тесты, стилизацию, безопасность.
- Минимум один тест на новую логику.
