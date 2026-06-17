# Frontend Kolibri AI

## Обзор

Одностраничное React-приложение с чат-интерфейсом, управлением документами,
поиском по базе знаний и мониторингом кластера.

## Стек

| Технология | Версия | Назначение |
|-----------|--------|-----------|
| React | 19.2.6 | UI-фреймворк |
| Vite | 8.0.12 | Сборка и dev-сервер |
| Framer Motion | 12.40.0 | Анимации |
| react-markdown | 10.1.0 | Рендеринг Markdown |
| remark-gfm | 4.0.1 | GitHub Flavored Markdown |
| tailwind-merge | 3.6.0 | Утилита для Tailwind |
| clsx | 2.1.1 | Условные классы |

## Структура проекта

```
frontend/
├── index.html
├── vite.config.js
├── package.json
└── src/
    ├── main.jsx              # Точка входа
    ├── App.jsx               # Основной компонент (~700 строк)
    ├── App.css               # Стили приложения
    ├── index.css             # Глобальные стили
    ├── globals.css           # CSS переменные (темы)
    ├── components/
    │   ├── KolibriBird.jsx   # Анимированный талисман колибри
    │   ├── KolibriAvatar.tsx # Аватар пользователя
    │   ├── MessageBubble.tsx # Пузырь сообщения
    │   └── ThinkingIndicator.tsx # Индикатор "Думаю..."
    ├── features/
    │   ├── canvas/
    │   │   └── CanvasCard.tsx    # Карточки для Canvas системы
    │   ├── chat/                 # (заготовка)
    │   ├── documents/            # (заготовка)
    │   ├── estimates/            # (заготовка)
    │   ├── memory/               # (заготовка)
    │   └── settings/             # (заготовка)
    ├── shared/
    │   └── types.ts              # TypeScript типы
    ├── lib/
    │   └── utils.js              # Утилиты
    └── assets/
        └── kolibri-mascot.png    # Талисман
```

## Основной компонент (App.jsx)

Монолитный компонент, управляющий всем UI. Содержит:

### Состояние (useState)
- `messages` — массив сообщений чата
- `input` — текст ввода
- `loading` — индикатор загрузки
- `ws` — WebSocket соединение
- `connected` — статус подключения
- `providers` — список AI-провайдеров
- `selectedProvider` — выбранный провайдер
- `sidebar` — открытие/закрытие сайдбара
- `theme` — тема (dark/light)
- `activeTab` — активная вкладка (chat/documents/search/cluster)
- `documents` — список документов
- `clusterStatus` — статус кластера
- `conversations` — история диалогов
- `conversationId` — текущий диалог

### Навигация (вкладки)

| Вкладка | Описание |
|---------|----------|
| **Чат** | Основной чат с AI |
| **Документы** | Загрузка и просмотр документов |
| **Поиск** | Семантический поиск по базе знаний |
| **Сеть** | Мониторинг кластера |

### API интеграция

```javascript
// Базовый URL определяется автоматически
const API_BASE = window.location.hostname === "localhost"
  ? `http://${window.location.hostname}:8000`
  : ""
```

- `GET /api/providers` — загрузка провайдеров
- `POST /api/chat` — отправка сообщений (fallback)
- `WS /ws/chat` — WebSocket чат (приоритет)
- `GET /cluster/status` — статус кластера (каждые 15 сек)
- `GET /api/conversations` — история диалогов
- `POST /api/conversations` — создание диалога
- `GET /api/conversations/{id}/messages` — сообщения
- `POST /rag/search` — семантический поиск

## Компоненты

### KolibriBird
Анимированный талисман колибри с состояниями:

| Состояние | Описание | Анимация |
|-----------|----------|----------|
| idle | Спокойна | Нет |
| thinking | Думает | Покачивание вверх-вниз |
| happy | Радуется | Увеличение |
| error | Ошибка | Тряска |
| flying | Летит | Движение по кругу |
| listening | Слушает | — |
| learning | Учится | Покачивание |
| success | Успех | Увеличение |

```jsx
import { KolibriBird } from "./components/KolibriBird"

<KolibriBird size={64} state="thinking" />
```

### CanvasCard (features/canvas/)
Система карточек для отображения структурированных данных AI.

**Типы карточек**:
- `estimate` — строительная смета с таблицей работ
- `document` — документ с превью
- `table` — табличные данные
- `code` — блок кода
- `plan` — пошаговый план
- `checklist` — чек-лист
- `memory` — данные из памяти
- `action` — действие

```tsx
import { CanvasCard } from './features/canvas/CanvasCard';

<CanvasCard
  card={{
    type: 'estimate',
    title: 'Смета на ремонт',
    data: {
      title: 'Ремонт комнаты',
      items: [...],
      totals: { grand_total: 150000 }
    },
    status: 'ready'
  }}
  onAction={(action, card) => console.log(action, card)}
/>
```

### ThinkingBlock
Блок рассуждений модели. Парсит `<thinking>...</thinking>` из ответа.

```jsx
function parseThinking(text) {
  const match = text.match(/<thinking>([\s\S]*?)<\/thinking>/)
  if (match) return { thinking: match[1].trim(), content: text.replace(...) }
  return { thinking: null, content: text }
}
```

### MarkdownRenderer
Рендерит Markdown с подсветкой кода и кнопкой копирования.

### ClusterView
Визуализация состояния кластера:
- Статистика (узлы, RAM, CPU, очередь)
- Карточки нод с индикаторами нагрузки
- Полоски использования RAM

### ErrorBoundary
Перехватывает ошибки React и показывает талисман с ошибкой.

## Темы

Две темы: dark и light. Переключаются через сайдбар.

```css
:root.theme-dark {
  --bg: #0a0a0f;
  --text-primary: #e2e8f0;
  --accent: #6366f1;
  /* ... */
}

:root.theme-light {
  --bg: #f0f4f8;
  --text-primary: #1a202c;
  /* ... */
}
```

Тема сохраняется в `localStorage("kolibri-theme")`.

## Конфигурация Vite

```javascript
// vite.config.js
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws': { target: 'ws://localhost:8000', ws: true }
    }
  }
})
```

В dev-режиме все `/api` и `/ws` запросы проксируются на backend.

## Сборка

```bash
cd frontend
npm install
npm run dev      # Development (port 5173)
npm run build    # Production build → dist/
npm run lint     # ESLint
```

Production build раздается через FastAPI static files на Main сервере.

## Sidebar

Содержит:
- Логотип Kolibri + кнопка "Новый чат"
- Навигация (Чат, Документы, Поиск, Сеть)
- История диалогов (до 20 последних)
- Выбор модели
- Переключатель темы
- Индикатор подключения

## Quick Actions

На главном экране (без сообщений):
- **Чат с AI** — начать диалог
- **Смета** — генерация сметы
- **Документы** — пакет документов
- **Поиск** — база знаний
