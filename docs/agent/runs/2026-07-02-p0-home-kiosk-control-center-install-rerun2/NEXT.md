# Next Steps: Home Kiosk Control Center — RERUN2

## Завершено
- [x] WireGuard tunnel восстановлен
- [x] kolibri-agent-host KeyError исправлен
- [x] Wallboard/tty10 работает
- [x] Firefox kiosk запущен и отображает Kolibri UI
- [x] Все kolibri сервисы active

## Follow-up задачи
1. **Мониторинг стабильности kiosk** — Firefox может crash/use memory over time; kolibri-home-kiosk.service имеет `Restart=always` для auto-recovery
2. **home heartbeat staleness** — node home показывает stale (3min) из-за CPU contention от mimo процесса; нормализуется после завершения RERUN2 task
3. **X Authority при reboot** — Ladik session может не быть активной при reboot; убедиться что LightDM autologin настроен для ladik
