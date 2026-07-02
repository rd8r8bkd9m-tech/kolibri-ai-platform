# Сводка для владельца

Режим: `repair_only`.

Запуск 2-часового окна autopilot на 50% мощности начат через удаленный Control Plane, но широкое продолжение надо держать в repair-only: governor 50% мощности упал на `main` из-за ошибки Codex auth refresh / HTTP 401, а runner-contract steward упал на `qjns`, потому что Codex executable там недоступен.

Созданы задачи:

- `P0_AUTOPILOT_CANONICAL_20_SERVER_READINESS_MATRIX_2026_07_02` - canonical 20-server readiness matrix, статус `queued`.
- `P0_AUTOPILOT_50PCT_CAPACITY_GOVERNOR_2026_07_02` - 50% capacity governor, статус `failed`, blocker: Codex auth refresh / HTTP 401 на `main`.
- `P0_AUTOPILOT_GUARDIAN_CONTROL_PLANE_STEWARD_2026_07_02` - Control Plane guardian, статус `queued`.
- `P0_AUTOPILOT_GUARDIAN_PR105_RELEASE_STEWARD_2026_07_02` - PR #105 steward, статус `queued`.
- `P0_AUTOPILOT_GUARDIAN_RUNNER_CONTRACT_STEWARD_2026_07_02` - runner-contract steward, статус `failed`, blocker: Codex executable недоступен на `qjns`.

Блокеры: подробная metadata PR #105 через `gh pr view` не снята, потому что `gh` не установлен на этом Agent Host; governor не активен; qjns не готов для Codex-задач. Git refs PR #105 записаны, owner merge gate сохраняется. Merge, auto-merge, push to main, force push и destructive git commands не выполнялись.
