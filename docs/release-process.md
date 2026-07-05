# Release процесс Foundation

## Что включаем в релиз

- Исходники (`source snapshot`)
- manifest + checksums
- документацию
- тест-отчёт
- известные ограничения и следующие шаги

## Минимальный pipeline

1. `make test`
2. `cargo fmt --check`
3. `cargo test --workspace`
4. `pnpm build` (для станции/фронта, если присутствует)
5. Сборка релиз-пакета и публикация артефактов

## Проверки v1

- `/health` каждого сервиса
- task flow: create → lease → complete/fail
- проверка policy/gate в демонстрационных сценариях

