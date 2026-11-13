# Коли V3 — production release notes

Проверено на `plastilin` после релизного цикла.

## Рабочий контур

- `coli-app` — Next.js standalone, PostgreSQL `coli_db`.
- `koliai-harness` — агентный интерфейс и tools bridge.
- FormulaLM V85/V86 — локальный ридер, память, морфология и автономный генератор.
- Ollama — локальный AI provider.
- gpt2giga/GigaChat — дополнительный provider.
- nginx — публичный TLS вход `https://koliai.ru`.

## Проверенные маршруты

- `/`
- `/pricing`
- `/blog`
- `/login`
- `/templates`
- `/projects`

Все возвращают HTTP 200 в production-приложении.

## Агентские инструменты

Инструментарий `@deepseek-ai/koliai-tools` покрывает:

- health/readiness;
- поиск и чтение блога;
- документы и контекст проекта;
- каталог цен и нормативы;
- запуск, resume/retry/cancel генерации сметы;
- статусы, детали, technology card и строки генерации;
- текущую смету и версии;
- экспорт PDF/XLSX/DOCX/CSV/ZIP.

## Безопасность

- Платные тарифы без подтверждённой оплаты возвращают HTTP 402.
- PDF экспорт использует установленный Chromium и проверен реальным PDF-файлом.
- Блоговый AI fallback возвращает безопасный черновик при недоступности provider.
- Харнесс использует стабильный операторский токен; секреты не входят в Git.

## AI policy

Production chat по умолчанию настроен через локальный provider из env/profile.
GigaChat подключён как дополнительный provider и требует учёта тарифного лимита
параллелизма. DeepSeek cloud route не является обязательным для работы продукта.

## Regression evidence

Проверены focused tests приложения: 96 tests passed в последнем regression run,
а также полные сборки харнесса с 10/10 пройденными gates в последних изменениях
agent/tools слоя.
