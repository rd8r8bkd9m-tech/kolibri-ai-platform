# Kimi Agent КолибриФин

Интеграционный пакет добавлен как изолированный модуль проекта Колибри.

## Что внутри

- `source/kolibri-backend` — Python backend пакета.
- `source/kolibri-v2` — React/Vite frontend пакета.
- `source/kolibri-web` — готовая статическая сборка.
- `source/*.png`, `source/plan*.md`, `source/research_analysis.md` — визуальные и исследовательские материалы.
- `manifest.json` — машинно-читаемое описание пакета для фабрики.

## Проверки

Минимальные проверки выполняются без production-секретов:

```bash
python3 -m compileall integrations/kimi-agent-kolibrifin/source/kolibri-backend/app
python3 integrations/kimi-agent-kolibrifin/scripts/smoke_check.py
```

Frontend-пакет сохранён с `package.json` и lock-файлом; полноценная сборка выполняется отдельной задачей после выбора способа включения в основной портал.

## Статус Mimo Auto

Mimo Code Auto был запущен на удалённом `main`, но остановился на provider-блокере: `mimo-free bootstrap failed: 403 illegal_access`. Поэтому пакет добавлен fallback-задачей удалённого implementation agent, а Mimo Auto требует отдельного восстановления авторизации provider.
