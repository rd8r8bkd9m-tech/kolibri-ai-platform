---
name: skill-router
description: "Автоматический подбор минимального набора .agents/skills под задачу Kolibri V3: keyword-скоринг по skills-index.json и явные оверрайды проекта (composer, streaming, смета, backend и т.д.). Use when: начало любой задачи в kolibri-v3 — до разработки выбрать и прочитать релевантные SKILL.md."
---

# Skill Router

Первый шаг любой задачи в `kolibri-v3/`:

```bash
node .agents/scripts/skill-router.mjs "<формулировка задачи>" --top 5
```

## Правила

- Прочитай **целиком** `SKILL.md` всех выбранных скиллов до разработки; не
  грузи весь каталог (см. `context-budgeting`).
- Точное имя скилла в задаче — обязательное чтение, даже если скоринг его не
  поднял.
- Нет совпадений — выбери ближайшие по категории (00–15) или описаниям и
  зафиксируй решение в `decision-log`.
- `--rebuild` пересобирает `skills-index.json` из файловой системы — запускай
  после установки/создания новых скиллов.
- После выбора скиллов работай по циклу `development-controller` и веди
  `.agents/progress-ledger.md`.
