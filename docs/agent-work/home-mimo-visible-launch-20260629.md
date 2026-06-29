# Home Mimo visible launch — 2026-06-29

## Резюме

2026-06-29 15:51 MSK на home-узле `plastilin` (`10.99.0.1`) удалённо поднят отдельный Mimo TUI-сеанс от пользователя `ladik`.

Цель проверки: показать, что Mimo можно поднять удалённо как живого агента на home-узле, без запуска экспериментов на Mac и без изменения репозитория.

## Что запущено

Новая tmux-сессия:

```bash
tmux attach -t mimo-home-demo
```

Рабочая папка:

```bash
/srv/kolibri/repo
```

Команда запуска:

```bash
mimo --trust /srv/kolibri/repo
```

Проверенный процесс:

```text
ladik 1654364 ... mimo --trust /srv/kolibri/repo
```

Capture из tmux показал живой интерфейс Mimo:

```text
Ты удалённый агент Mimo на home-узле Kolibri...
Build · MiMo Auto
esc interrupt     tab сменить режим  ctrl+p настройки
```

## Что уже было на физическом tty1

На home также уже работали процессы Mimo от root:

```text
root 910    /usr/local/bin/mimo serve --port 4096 --hostname 0.0.0.0 --mdns
root 269747 mimo
```

`root 269747` привязан к `tty1`, то есть физический экран уже занят существующим Mimo-процессом.

## Ограничение

У пользователя `ladik` нет passwordless sudo:

```text
sudo: a password is required
```

Поэтому я не стал силой писать в `/dev/tty1` и не перезапускал root-процесс Mimo. Это безопаснее: текущий видимый Mimo на физическом экране не был сброшен.

`mimo serve` на `4096` слушает, но HTTP UI сейчас отдаёт:

```text
503 Web UI is temporarily unavailable.
```

## Как владельцу проверить

На home-узле можно подключиться к поднятому сеансу:

```bash
tmux attach -t mimo-home-demo
```

Если нужно вывести именно новый Mimo на физический `tty1`, требуется root-действие на home:

```bash
sudo chvt 1
```

или запуск/перезапуск Mimo непосредственно из активной root-консоли. Без sudo я оставил безопасный пользовательский сеанс `mimo-home-demo`.

## Проверки

- `curl http://127.0.0.1:8081/api/health` на home вернул `Kolibri Mesh Agent`, node `home`, status `ok`.
- `tmux ls` показывает `mimo-home-demo`.
- `tmux list-panes -t mimo-home-demo` показывает `command=mimo`, `dead=0`.
- Репозиторий `/srv/kolibri/repo` не менялся этим запуском.
