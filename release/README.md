# Release packaging

## Что включено в релизный пакет

- Исходный архив с исходниками (`source snapshot`)
- Машиночитаемый manifest (`release/manifest.json`)
- Тестовый отчёт (`release/checklist.md` + результаты запусков)
- Документы foundation (`docs/*`)
- Исполняемые артефакты (если доступны в окружении сборки)
- Логи сборки и контрольные хэши

## Как собрать вручную

```bash
make fmt
make clippy
make test
make locald
```

Если все сервисы собраны, повторите:

```bash
make release
```
