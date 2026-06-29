# Home Mimo tty9 screen recovery — 2026-06-29

## Резюме

2026-06-29 15:58 MSK по фото владельца и live-проверке восстановлен чистый видимый Mimo-сеанс на home-узле `plastilin` (`10.99.0.1`).

Итог: монитор переключён с зашумлённого `tty1` на новый `tty9`, где запущен Mimo от пользователя `ladik` в `/srv/kolibri/repo`.

## Видимый Mimo

Команда запуска через root SSH:

```bash
openvt -f -c 9 -s -- /bin/bash -lc 'export HOME=/home/ladik USER=ladik LOGNAME=ladik; clear; cd /srv/kolibri/repo; exec runuser -u ladik -- /usr/local/bin/mimo --trust /srv/kolibri/repo'
```

Проверка после запуска:

```text
current_vt=9
root  1668532 ... runuser -u ladik -- /usr/local/bin/mimo --trust /srv/kolibri/repo
ladik 1668544 ... /usr/local/bin/mimo --trust /srv/kolibri/repo
```

Это означает, что физический экран сейчас должен показывать новый Mimo на `tty9`, а не старый garbled-сеанс на `tty1`.

## Что было на фото

Фото показало:

- Mimo реально открыт на физическом мониторе;
- ввод в старом root-сеансе был зашумлён случайными символами;
- внизу экрана появились kernel/RAS сообщения по памяти;
- Mimo показывал `Build · MiMo Auto` и `interrupted`.

Live-проверка подтвердила старый процесс:

```text
root 269747 tty1 ... mimo
```

Старый `tty1` Mimo не был убит, чтобы не срывать активную root-консоль без отдельной команды владельца. Вместо этого поднят чистый `tty9`.

## Memory/RAS finding

Root-доступом подтверждены kernel-события:

```text
mce: [Hardware Error]: Machine check events logged
RAS: Soft-offlining pfn: 0x10cb39
Memory failure: 0x10cb39: unhandlable page.
RAS: Soft-offlining pfn: 0x61f89
```

Текущее состояние памяти:

```text
MemTotal: 16239692 kB
MemAvailable: около 12104980 kB
HardwareCorrupted: 52 kB
```

Вывод: home работает, но RAM/железо нужно держать под наблюдением. Это не блокирует текущий запуск Mimo, но является infrastructure risk для фабрики.

## Что очищено

Временная tmux-сессия `mimo-home-demo`, созданная ранее для проверки, была остановлена, потому что её Mimo поймал timeout и больше не нужен.

Остался основной Codex tmux:

```text
codex-home
```

## Проверки

- `fgconsole` вернул `9`.
- `ps -t tty9` показал активный Mimo от `ladik`.
- `curl http://127.0.0.1:8081/api/health` на home ранее возвращал `Kolibri Mesh Agent`, node `home`, status `ok`.
- `mimo serve` на `4096` по-прежнему слушает, но HTTP UI отдаёт `503 Web UI is temporarily unavailable`.

## Следующее исполнение

1. Оформить штатную Control Plane задачу/runner для `visible_mimo_session`, чтобы запуск на `tty9` выполнялся не вручную, а через lease.
2. Добавить health-check по `HardwareCorrupted` и RAS/MCE в SRE watchdog.
3. После отдельного подтверждения владельца можно остановить старый `tty1` Mimo (`root 269747`), если он больше не нужен.
