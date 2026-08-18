# Kolibri V3 — индекс скиллов

Таблица «скилл → категория» для всех установленных agent-skills в
`.agents/skills/`. Категории — по таксации продукта (00–15). Компоновка на
диске смешанная: плоские скиллы (K/A/E/X) и сгруппированные пакеты
`<группа>/<скилл>/`. Discovery идёт по frontmatter `description`, не по путям.

## Пакет `kolibri-agent-skills-v3` (250 скиллов)

Установлен из `kolibri-agent-skills-v3-250.zip` в
`.agents/skills/<группа>/<скилл>/` (16 групп: 00-orchestration …
15-release). Машиночитаемый индекс — `skills-index.json` (250 записей),
профили агентов — `agent-profiles.json`. Валидация пакета:
`bash .agents/scripts/validate-skills.sh`. `AGENTS.md` из пакета не
установлен — в `.agents/AGENTS.md` живёт системный промпт ассистента Kolibri.

Легенда происхождения:
- **K** — Kolibri-нативный скилл (создан в этом репо)
- **A** — assistant-ui официальный пак
- **E** — официальный Expo/EAS пак (установлен через `npx skills@latest add expo/skills --skill '*'`)
- **X** — внешний (gemini-skills)

## 00 — Orchestration

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-orchestration` | K | Декомпозиция, параллельные субагенты, definition-of-done |

## 01 — Project / Architecture

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-v3-development` | K | Guardrails и регрессионные ловушки V3 |
| `kolibri-dev-stack` | K | Dev-стек: запуск, порты, health-гейты, verify-пайплайн |
| `kolibri-vertical-registry` | K | Вертикали: allowlist, capability/entitlement/rendererKey гейты |
| `expo-project-structure` | E | Структура папок Expo-приложения |
| `expo-brownfield` | E | Добавление Expo/RN в существующее приложение |
| `expo-web-to-native` | E | Миграция web/React приложения в нативное |

## 02 — React Native

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-mobile-perf` | K | Производительность Expo-клиента: скролл, рендеры, бандл, Metro |
| `expo-native-ui` | E | Нативные стили: семантические цвета, контролы, медиа, анимации |
| `expo-module` | E | Нативные модули и вью (Swift/Kotlin, config plugins) |
| `expo-app-clip` | E | iOS App Clip, AASA, associated domains |

## 03 — Expo

| Скилл | Откуда | Назначение |
|---|---|---|
| `expo-router` | E | Файловые маршруты, стеки, модалки, вкладки, хедеры |
| `expo-ui` | E | `@expo/ui` нативные компоненты |
| `expo-dom` | E | DOM-компоненты для веб-кода в нативе |
| `expo-dev-client` | E | Development-билды |
| `expo-examples` | E | Репозиторий `with-*` интеграций |
| `expo-upgrade` | E | Апгрейд Expo SDK, конфликты зависимостей |
| `expo-migrate-module` | E | (экспериментальный) Миграция Swift-модуля на Modules API 2.0 |
| `kolibri-mobile-navigation` | K | Навигация Expo-клиента: drawer, bottom sheets, back-переходы, вертикали |

## 04 — UI / UX

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-mobile-ui` | K | Пиксельный UI мобильного клиента: токены, RN-web квирки, Liquid Glass |
| `expo-tailwind-setup` | E | Tailwind v4 / NativeWind v5 (внимание: в этом проекте arbitrary-variable utilities не эмитятся — см. `kolibri-v3-development`) |

## 05 — State / Data

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-mobile-state` | K | Дисциплина состояния: Context + useAui/useAuiState, без внешних сторов |
| `expo-data-fetching` | E | API-вызовы, кэширование, оффлайн, data loaders |

## 06 — Backend

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-backend` | K | FastAPI-домены, тонкие роутеры, миграции, venv, pytest |
| `kolibri-auth-session` | K | Bearer + refresh rotation, same-origin gateway auth |
| `kolibri-billing` | K | Биллинг: T-Банк, подписки, renewals, entitlements |

## 07 — AI / LLM

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-agui-transport` | K | AG-UI SSE транспорт, события, контракты, маршрутизация карточек |
| `gemini-interactions-api` | X | Вызовы Gemini API (внешний пак) |

## 08 — Assistant UI

| Скилл | Откуда | Назначение |
|---|---|---|
| `assistant-ui` | A | Обзор и маршрутизатор assistant-ui |
| `setup` | A | Установка и конфигурация assistant-ui |
| `runtime` | A | Runtime-система, состояние, aui-клиент |
| `primitives` | A | Композируемые примитивы чата |
| `tools` | A | Регистрация LLM-тулов и их UI |
| `streaming` | A | Стриминговые протоколы (assistant-stream) |
| `thread-list` | A | Мульти-треды (история диалогов) |
| `copilots` | A | Управление поведением ассистента |
| `markdown` | A | Рендер markdown в сообщениях |
| `cloud` | A | Cloud persistence и авторизация |
| `react-mcp` | A | MCP-серверы пользователя в браузере |
| `observability` | A | Трейсинг и телеметрия backend |
| `update` | A | Обновления и миграции assistant-ui |
| `kolibri-mobile-chat` | K | Чат-поверхность Expo-клиента: composer, стриминг, карточки, голос |

## 09 — Estimator (сметы)

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-estimates-engine` | K | Детерминированный расчёт, durable-генерация, каталог, документы, экспорты |
| `estimate-generation` | K | (legacy) Генерация смет — устаревший, только чтение |

## 10 — Testing / QA

| Скилл | Откуда | Назначение |
|---|---|---|
| `kolibri-mobile-qa` | K | Проверка мобильного PWA: gateway, stale-бандлы, Playwright, пиксели |
| `expo-skill-eval` | E | (служебный, Expo) Harness оценки скиллов — не для продакшн-задач |

## 11 — Debugging

*(в проекте отладка покрывается `kolibri-dev-stack`, `kolibri-mobile-qa` и официальными expo/eas-скиллами)*

## 12 — Security

*(сейчас покрывается правилами `kolibri-v3-development` и `kolibri-auth-session`)*

## 13 — DevOps

| Скилл | Откуда | Назначение |
|---|---|---|
| `eas-workflows` | E | EAS Workflow YAML, CI/CD автоматизация |
| `eas-hosting` | E | Хостинг Expo-сайтов и API-роутов |

## 14 — GitHub

*(GitHub-операции — tool-команды, роли не вводятся)*

## 15 — Release

| Скилл | Откуда | Назначение |
|---|---|---|
| `eas-app-stores` | E | Продакшн-билды, App Store, Play Store, TestFlight |
| `eas-observe` | E | Метрики запуска/маршрутов/событий |
| `eas-update-insights` | E | Здоровье EAS Update, rollout-гейты |
| `eas-simulator` | E | Удалённый симулятор/эмулятор из CLI |
| `expo-skill-feedback` | E | Обратная связь по Expo-скиллам и телеметрия (опт-ин) |

## Роли агентов

Роль-файлы: `.agents/agents/{orchestrator,architect,frontend,mobile,backend,ai,estimator,qa}.md`
— каждый перечисляет маршрутизируемые скиллы в frontmatter `skills:`.
