# Home Visibility Recovery Diagnostic Result

## Статус для владельца

Статус: `blocked_classified`, не `completed`.

Узел выполнения: `mesh-agent-13` на сервере `kolibri`, не локальный Mac.

Home сейчас виден через Control Plane, но прямой SSH-путь с этого серверного узла до Home не восстановлен. Поэтому я не могу честно подтвердить, что Home Agent Host, tmux wallboard и GitHub clone/auth на самом Home полностью рабочие. Эти пункты классифицированы как блокеры, а не как завершенная починка.

## Точное состояние

- `home`: Control Plane видит карточку `hostname=plastilin`, `reported_health=online`, но `health=degraded`, `freshness=degraded`; heartbeat свежий на момент проверки.
- `home-live`: Control Plane видит карточку `hostname=plastilin`, `reported_health=online`, но `health=degraded`, `freshness=degraded`; heartbeat свежий на момент проверки.
- `mesh-home`: stale mesh-card; heartbeat был старше примерно 28 минут на момент проверки.
- SSH `home`/`kolibri-home`: alias настроен, но фактическое подключение блокируется на banner exchange.
- SSH `kolibri-main` и другие прямые серверные алиасы: прямой SSH с `kolibri` также таймаутится, значит проблема шире, чем один Home alias.
- GitHub из текущего серверного worktree: `git ls-remote origin HEAD` успешен.
- Wallboard: предыдущая задача `P0_HOME_FACTORY_TERMINAL_UI_RU_2026_07_01` не подняла Home wallboard; она упала на `git clone ... rc=128`. Нового подтвержденного tmux-session на Home нет, потому что SSH до Home не прошел.

## Что восстановлено или подтверждено

- Серверное выполнение подтверждено.
- Control Plane health доступен: `http://10.99.0.10:9101/health`.
- Control Plane видит свежие `home` и `home-live` heartbeat, но помечает их degraded.
- Локальный factory status endpoint отвечает JSON `status=ok`.
- Короткие SSH aliases `home` и `kolibri-home` существуют и резолвятся в `10.99.0.1` с пользователем `ladik`.
- GitHub read из текущего серверного checkout работает.

## Блокеры

1. Прямой SSH с серверного узла `kolibri` до `home` не проходит: `Connection timed out during banner exchange`.
2. Прямой SSH с `kolibri` до `kolibri-main` и первых проверенных fleet aliases тоже таймаутится, что указывает на сетевой или egress/route блокер для SSH-диагностики.
3. Home Agent Host runtime state не подтвержден host-level командой из-за SSH блокера; доступна только Control Plane карточка.
4. Home wallboard не подтвержден: tmux-сессии на Home нельзя прочитать без SSH, а предыдущая wallboard-задача упала на clone/auth.
5. GitHub clone/auth именно на Home не подтвержден; подтвержден только GitHub read из текущего server checkout.

## Артефакты

Созданы требуемые артефакты:

- `docs/agent/runs/2026-07-02-repair-wave/P0_HOME_HOME_LIVE_AGENT_HOST_RECOVERY_DIAGNOSTIC_2026_07_02/PLAN.md`
- `docs/agent/runs/2026-07-02-repair-wave/P0_HOME_HOME_LIVE_AGENT_HOST_RECOVERY_DIAGNOSTIC_2026_07_02/ACTIONS.md`
- `docs/agent/runs/2026-07-02-repair-wave/P0_HOME_HOME_LIVE_AGENT_HOST_RECOVERY_DIAGNOSTIC_2026_07_02/TESTS.md`
- `docs/agent/runs/2026-07-02-repair-wave/P0_HOME_HOME_LIVE_AGENT_HOST_RECOVERY_DIAGNOSTIC_2026_07_02/RESULT.md`
- `docs/agent/runs/2026-07-02-repair-wave/P0_HOME_HOME_LIVE_AGENT_HOST_RECOVERY_DIAGNOSTIC_2026_07_02/NEXT.md`

## Решение

Не заявлять `completed`. Правильная классификация: Home visibility path partially visible through Control Plane, but Home host-level recovery and wallboard verification are blocked by SSH route/banner timeout and prior Home wallboard clone/auth failure.

