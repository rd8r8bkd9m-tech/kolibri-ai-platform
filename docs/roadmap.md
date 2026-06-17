# Roadmap Kolibri AI Platform

## Статусы

- ✅ Готово
- 🔧 В работе
- 📋 Планируется
- ❌ Отклонено

---

## MVP Phase 1 — Базовая платформа ✅

| Функция | Статус | Описание |
|---------|--------|----------|
| FastAPI backend | ✅ | API Gateway на Main |
| React frontend | ✅ | SPA с чат-интерфейсом |
| WireGuard mesh | ✅ | 6 серверов в единой сети |
| MiMo CLI интеграция | ✅ | Генерация через subprocess |
| SQLite база данных | ✅ | Кеш, диалоги, rate limits |
| WebSocket чат | ✅ | Стриминг через WS |
| REST API | ✅ | Полный набор endpoints |
| Темы (dark/light) | ✅ | Переключение с сохранением |
| История диалогов | ✅ | CRUD для conversations |

## MVP Phase 2 — RAG + Pipeline ✅

| Функция | Статус | Описание |
|---------|--------|----------|
| ChromaDB RAG | ✅ | Векторный поиск на UIAP |
| Unified Pipeline | ✅ | auto/rag/agent/chat routing |
| Intent Detection | ✅ | Ключевые слова → intent |
| RAG Chain | ✅ | Search → Context → Generate |
| Agent Chain | ✅ | Planning + tool execution |
| RAG + Agent Chain | ✅ | Комбинированная цепочка |
| Proxy Routes | ✅ | Main → UIAP/QJNS/9FTS |
| Pipeline Health | ✅ | Мониторинг всех сервисов |

## MVP Phase 3 — Organism ✅

| Функция | Статус | Описание |
|---------|--------|----------|
| Redis State Store | ✅ | Общее состояние кластера |
| Job Queue | ✅ | Распределённая очередь задач |
| Resource Manager | ✅ | CPU/RAM scoring + auto-assign |
| Heartbeat | ✅ | 15-секундные heartbeat'ы |
| Node Registration | ✅ | Автоматическая регистрация |
| Cluster Status API | ✅ | Мониторинг кластера |
| Job Dispatch | ✅ | Auto-routing к лучшей ноде |
| Broadcast | ✅ | Широковещательные сообщения |

## MVP Phase 4 — Kolibri Nano ✅

| Функция | Статус | Описание |
|---------|--------|----------|
| Trace System | ✅ | 9 типов следов |
| Memory Engine | ✅ | Поиск, паттерны, контекст |
| Association Graph | ✅ | Граф связей между сущностями |
| Confidence Score | ✅ | 4-факторная оценка |
| Personal Core | ✅ | 7 параметров + core digits |
| Estimate Engine | ✅ | Создание и расчёт смет |
| Storage | ✅ | JSON файловое хранилище |
| 32 теста | ✅ | Полное покрытие модулей |

## Phase 5 — UI Enhancement 🔧

| Функция | Статус | Описание |
|---------|--------|----------|
| Canvas System | 🔧 | Карточки для структурированных данных |
| Estimate Cards | 🔧 | Превью смет в чате |
| Document Cards | 🔧 | Превью документов |
| Memory Cards | 🔧 | Отображение данных памяти |
| Thinking Block | ✅ | Блок рассуждений модели |
| Markdown рендеринг | ✅ | С подсветкой кода |
| Cluster Monitor | ✅ | Визуализация кластера |
| Mobile Responsive | 🔧 | Адаптивный дизайн |

## Phase 6 — Multimodal 📋

| Функция | Статус | Описание |
|---------|--------|----------|
| TTS (Text-to-Speech) | ✅ | edge-tts / gtts |
| STT (Speech-to-Text) | 📋 | Whisper интеграция |
| Image Generation | 📋 | DALL-E / Stable Diffusion |
| Vision Analysis | 📋 | Анализ изображений |
| Voice Chat | 📋 | Голосовой чат |
| File Upload | ✅ | Загрузка документов |

## Phase 7 — Document Generation 📋

| Функция | Статус | Описание |
|---------|--------|----------|
| PDF Export | 📋 | Экспорт смет в PDF |
| DOCX Export | 📋 | Экспорт в Word |
| Commercial Offer | 📋 | Коммерческое предложение |
| Contract Template | 📋 | Шаблон договора |
| Act of Work | 📋 | Акт выполненных работ |
| Document Pack | 📋 | Полный пакет документов |

## Phase 8 — Advanced Agent 📋

| Функция | Статус | Описание |
|---------|--------|----------|
| Tool Calling | 📋 | Реальные инструменты |
| File Operations | 📋 | Чтение/запись файлов |
| Code Execution | 📋 | Запуск кода |
| Web Browsing | 📋 | Навигация по сайтам |
| Multi-step Planning | 📋 | Сложные цепочки рассуждений |
| Agent Memory | 📋 | Долгосрочная память агента |

## Phase 9 — Training & Fine-tuning 📋

| Функция | Статус | Описание |
|---------|--------|----------|
| Dataset Preparation | 📋 | Скрипты подготовки данных |
| LoRA Fine-tuning | 📋 | Адаптеры для моделей |
| Model Merging | 📋 | Слияние адаптеров |
| Evaluation | 📋 | Оценка качества моделей |
| Auto-training Pipeline | 📋 | Автоматическое обучение |

## Phase 10 — Production Ready 📋

| Функция | Статус | Описание |
|---------|--------|----------|
| User Authentication | 📋 | JWT / OAuth |
| Rate Limiting (Redis) | 📋 | Перенос в Redis |
| Monitoring (Prometheus) | 📋 | Метрики |
| Logging (structured) | 📋 | Структурированные логи |
| CI/CD Pipeline | 📋 | GitHub Actions |
| Backup Strategy | 📋 | Автобэкапы |
| Load Balancing | 📋 | Балансировка нагрузки |
| SSL/TLS | 📋 | Let's Encrypt |

---

## Приоритеты

1. **Phase 5** (UI) — улучшить UX, закончить Canvas
2. **Phase 7** (Documents) — экспорт смет и документов
3. **Phase 8** (Agent) — реальные инструменты
4. **Phase 10** (Production) — аутентификация, мониторинг
5. **Phase 6** (Multimodal) — голос и изображения
6. **Phase 9** (Training) — fine-tuning моделей

## Известные проблемы

- **9FTS нестабилен**: inference сервер часто падает из-за нехватки RAM
- **Нет аутентификации**: все API открыты
- **CORS wildcard**: `allow_origins=["*"]`
- **Монолитный frontend**: App.jsx ~700 строк
- **SQLite**: не подходит для production с множеством запросов
- **Rate limit на SQLite**: медленно при высокой нагрузке
