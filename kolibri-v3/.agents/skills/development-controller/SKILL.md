---
name: development-controller
description: "Контроллер production-цикла Kolibri V3: DISCOVER → SELECT SKILLS → PLAN → IMPLEMENT → INTEGRATE → VERIFY → FIX → DONE, состояние в progress-ledger, anti-loop и definition-of-done. Use when: любая задача разработки/изменения продукта в kolibri-v3."
---

# Development Controller

Обязательный цикл для каждой задачи в `kolibri-v3/`:

1. **DISCOVER** — затронутая поверхность (mobile/backend/ai/release), entry
   point, контракты, текущее состояние.
2. **SELECT SKILLS** — `node .agents/scripts/skill-router.mjs "<задача>" --top 5`;
   прочитай выбранные `SKILL.md` целиком.
3. **PLAN** — вертикальный slice + acceptance criteria; запись в
   `.agents/progress-ledger.md` (состояние `IMPLEMENTING`).
4. **IMPLEMENT** — production-код раньше тестов; минимальный связный change.
5. **INTEGRATE** — реальные entry point/state/API; без mock-заглушек на пути.
6. **VERIFY** — узкая проверка поведения; затем typecheck/lint/тесты по риску.
7. **FIX** — корень первого failure; не повторяй одинаковые команды без
   изменения кода или гипотезы.
8. **DONE** — по `definition-of-done`: поведение работает через entry point,
   контракты обновлены, нет плейсхолдеров, diff без хлама; обнови леджер и
   evidence.

## Анти-циклы (запрещено)

- Тесты как завершение без реализованного поведения.
- Mock вместо реальной интеграции.
- Повторный прогон одной и той же проверки без изменений.
- DONE только по зелёным тестам.
- Бесконечные уточнения вместо продвижения; при блокере — evidence в
  failure-gate и остановка на безопасной границе.

## Леджер

- Файл: `.agents/progress-ledger.md`; состояния
  `DISCOVERING | IMPLEMENTING | INTEGRATING | VERIFYING | BLOCKED | DONE`.
- Обновляй при старте, на каждом завершённом slice и в конце задачи.
- После проверки текущей задачи следующая берётся из раздела `Next` леджера.
