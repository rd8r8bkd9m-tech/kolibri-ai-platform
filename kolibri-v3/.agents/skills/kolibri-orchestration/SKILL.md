---
name: kolibri-orchestration
description: "Decompose Kolibri V3 tasks, run parallel sub-agent work, and declare a definition-of-done before acting. Use for any multi-step V3 task spanning two or more surfaces (mobile+backend, web+contracts) or when a change needs an explicit done checklist."
license: MIT
---

# Kolibri Оркестрация

Работаем внутри `kolibri-v3/`. Сначала прочитать `kolibri-v3/AGENTS.md`.

## Когда использовать

- Задача затрагивает две и более поверхности (мобильный + backend, web + контракты).
- Нужно решить, что делать параллельно, а что последовательно.
- Изменение должно иметь явные критерии «готово».

## Workflow

1. **Сформулировать цель** одним предложением и назвать затронутые контуры (по `docs/PROJECT_MAP.md`).
2. **Декомпозировать** на независимые подзадачи: транспорт/контракты, UI, backend, тесты. Зависимые шаги — строго последовательно (например, контракт → клиент → UI).
3. **Определить, что можно параллелить**: независимые файлы/контуры — параллельные субагенты; один файл — один агент.
4. **Зафиксировать definition-of-done** до кода: какие гейты пройдут (`npm run verify`, `verify:full`, `mobile:typecheck`), какие тесты, какой смоук на живом стеке.
5. **Маршрутизировать скиллы**: мобильный UI → `kolibri-mobile-*`, backend → `kolibri-backend`, сметы → `kolibri-estimates-engine`, авторизация → `kolibri-auth-session`, dev-стек → `kolibri-dev-stack`.
6. После исполнения каждой подзадачи — сверка с done-чеклистом; не объявлять «готово» при не пройденном гейте.

## Rules

- Не создавать второй механизм там, где есть канонический (один runtime, один источник правды).
- Не делать общих агентских фреймворков — только нужное для V3.
- Параллельный субагент не видит ваш контекст — давать ему полное ТЗ с путями.

## Verification

- Все подзадачи имеют запись в трекере задач и статус.
- Финальный `git status` показывает только ожидаемые файлы.
- Definition-of-done выполнен: гейты и смоук пройдены, отчёт без «потерянных» шагов.

## Related skills

- `kolibri-v3-development` — guardrails и регрессионные ловушки V3
- `kolibri-dev-stack` — как запускать и проверять стек
