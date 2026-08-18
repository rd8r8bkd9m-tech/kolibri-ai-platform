# Mobile device E2E

Запускать после сборки native-клиента и запуска dev-стека.

```bash
maestro test apps/kolibri-mobile/.maestro/auth.yaml
maestro test apps/kolibri-mobile/.maestro/chat-estimate.yaml
maestro test apps/kolibri-mobile/.maestro/estimate-export.yaml
```

`estimate-export` требует сохранённую смету в текущем аккаунте.
