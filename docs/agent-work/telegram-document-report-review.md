# Ревизия Telegram-документов

Роль отчета: Ревизор Telegram-документов.  
Дата: 2026-06-29.  
Статус: документационная ревизия без изменений кода.

## Короткий вывод

`docs/agent-work/telegram-reporting-plan.md` и
`docs/agent-work/telegram-report-letter-template.md` уже закрывают основной
контракт: агенты не ходят в Telegram напрямую, отчеты идут через Control Plane
task и `kolibri-telegram-gateway.service`, а текст письма должен быть коротким,
проверяемым и очищенным от секретов.

Главное, что нужно добавить в automation prompts: явное требование формировать
`result.response` как owner-facing Telegram-письмо по единому шаблону,
запрещать raw logs/секреты/внутренние пути, указывать проверки и честно
называть блокеры по `owner_chat_id`, `TELEGRAM_BOT_TOKEN` и
`TELEGRAM_OWNER_IDS`.

## Уже покрыто

### Маршрут доставки

План фиксирует правильную границу ответственности:

- единственный процесс, который пишет владельцу в Telegram, -
  `kolibri-telegram-gateway.service`;
- агенты и automations не получают `TELEGRAM_BOT_TOKEN`;
- task/result/status фиксируются в Control Plane;
- Telegram gateway сам опрашивает Control Plane и отправляет owner-visible
  статусы;
- `/v1/agent-messages` остается audit feed и сам по себе не является
  Telegram-доставкой.

### Безопасность и redaction

Документы уже описывают, что нельзя отправлять:

- bot token, API keys, auth/session данные и env dumps;
- raw stdout/stderr, traceback, большие JSON payloads;
- внутренние абсолютные пути, `result_path`, `log_path`, `env_file`;
- task/node/agent ids без явной debug-просьбы;
- приватные customer/investor/financial данные без отдельного основания.

Также отмечено важное правило: gateway redaction - последняя страховка, а не
нормальный способ подготовки отчета. Агент должен отдавать уже очищенный
`result.response`.

### Формат письма

Шаблон задает стабильную структуру:

- тема;
- дата;
- ответственный с понятным русским именем;
- статус;
- контекст;
- сделано;
- проверки;
- блокеры;
- риски;
- следующие шаги;
- ссылки на безопасные артефакты;
- подпись агента.

Это хорошо подходит для owner-facing отчетов, потому что одинаковый порядок
полей делает Telegram-ленту аудируемой и читаемой с телефона.

### Лимиты и chunking

Шаблон уже покрывает практические лимиты:

- `sendMessage` Telegram: до 4096 символов plain text;
- локальный `TelegramClient.send_message`: до 3900 символов;
- документальный `REPORT_CHUNK_LIMIT`: 3600 символов;
- caption у фото: до 1024 символов;
- длинные письма делятся по смысловым блокам, а не по сырому счетчику символов.

### Idempotency и retry

План уже задает полезный контракт:

- каждый отчет получает стабильный `idempotency_key`;
- повтор logical report не должен создавать новую задачу;
- `max_retries=1` достаточно для owner notifications;
- delivery Telegram считается at-least-once, поэтому повтор сообщения не должен
  запускать дополнительные действия.

## Что добавить в automation prompts

Automation prompts стоит дополнить отдельным блоком "Telegram owner report".
Его нужно вставлять в prompts задач, которые могут завершиться owner-visible
отчетом.

```text
Telegram owner report:
- Не отправляй сообщения в Telegram напрямую и не запрашивай TELEGRAM_BOT_TOKEN.
- Заверши исходную Control Plane task через штатный complete/fail/annotate path.
- В result.response подготовь короткое owner-facing письмо на русском по шаблону:
  Тема, Дата, Ответственный, Статус, Контекст, Сделано, Проверки, Блокеры,
  Риски, Следующие шаги, Ссылки на артефакты, Подпись агента.
- Используй понятное русское имя агента в поле "Ответственный".
- Укажи фактические проверки с результатом. Если проверки не запускались,
  напиши "Не запускалось: <причина>".
- Если доставка зависит от Telegram gateway, явно проверь и назови блокеры:
  owner_chat_id не сохранен, TELEGRAM_BOT_TOKEN отсутствует/недоступен,
  TELEGRAM_OWNER_IDS не задан или не совпадает с Telegram user id владельца.
- Не включай raw logs, traceback, env dumps, секреты, внутренние абсолютные пути,
  task/node/agent ids, private URLs и длинные JSON payloads.
- Если текст длиннее 3600 символов, сделай executive summary в Telegram, а
  детали оставь в безопасном repo-документе, PR, issue или artifact.
- Если задача заблокирована, статус должен быть "заблокировано" или
  "требует решения", а блокер должен содержать владельца следующего действия.
```

Для prompts, которые создают отдельную report task, также нужно требовать:

```text
Control Plane report task:
- kind: owner_remote_task.
- required_capability: generic_implementation.
- source.kind: automation.
- idempotency_key: telegram-report:<automation>:<topic-or-input-hash>:<date-or-version>.
- max_retries: 1, если это только уведомление или статусный отчет.
- objective: подготовить короткий безопасный отчет владельцу, а не выполнить
  скрытые действия через Telegram.
```

## Как форматировать длинные текстовые письма в Telegram

Длинное письмо не должно превращаться в поток логов. Правило: Telegram получает
решение владельца, доказательство проверки и следующий шаг, а не весь
технический архив.

Рекомендуемый порядок:

1. Сначала сжать отчет до executive summary: тема, статус, 2-5 результатов,
   проверки, блокер, следующий шаг.
2. Если письмо все еще длиннее 3600 символов, разбить по смысловым блокам:
   шапка/контекст, сделано/проверки, блокеры/риски/следующие шаги,
   артефакты/подпись.
3. Каждую часть начинать одинаково:
   `Тема: <короткая тема> (1/3)`.
4. Не разрывать одну проверку, один блокер или одну ссылку между частями.
5. Если получается больше 3 частей, оставить в Telegram только summary и ссылку
   на безопасный документ.
6. Не использовать Markdown-таблицы, декоративные символы и сложную разметку.
   Gateway работает с plain text, мобильный Telegram должен читать письмо без
   горизонтального скролла.
7. Фото и media captions не использовать как основной канал документального
   отчета: caption держать до 1024 символов, а полноценный отчет отправлять
   текстом.

Мини-форма для длинного отчета:

```text
Тема: <...> (1/2)
Дата: <YYYY-MM-DD HH:MM TZ>
Ответственный: <русское имя агента>
Статус: <...>

Контекст:
...

Сделано:
- ...

Проверки:
- ...
```

```text
Тема: <...> (2/2)

Блокеры:
- ...

Риски:
- ...

Следующие шаги:
1. ...

Ссылки на артефакты:
- ...

Подпись агента:
<...>
```

## Blocker-ы по owner_chat_id и token

### owner_chat_id не сохранен

Симптом: gateway может читать Telegram, но не знает, в какой private chat
отправлять owner-visible updates.

Причина: владелец еще не написал боту private сообщение, либо state file
потерян/недоступен.

Что писать в отчете:

```text
Блокеры:
- Telegram delivery заблокирована: owner_chat_id не сохранен. Нужно, чтобы
  владелец написал боту одно private сообщение, после чего gateway сохранит chat id.
```

Проверки для оператора:

- state file `TELEGRAM_GATEWAY_STATE` существует;
- service user может писать в state dir;
- gateway не находится в restart loop;
- владелец писал именно в private chat, а не только в группу.

### TELEGRAM_BOT_TOKEN отсутствует или недоступен

Симптом: gateway не может вызывать Telegram Bot API.

Причина: token не установлен в `/etc/kolibri/telegram.env`, файл не подключен к
systemd unit, права/owner не позволяют прочитать секрет, либо token неверный.

Что писать в отчете:

```text
Блокеры:
- Telegram delivery заблокирована: TELEGRAM_BOT_TOKEN отсутствует или недоступен
  gateway service. Токен должен быть установлен в root-readable secret file,
  не в repo и не в task envelope.
```

Важно: значение token никогда не вставлять в отчет, логи, prompt или artifact.

### TELEGRAM_OWNER_IDS не задан или не совпадает

Симптом: gateway получает сообщения, но считает владельца неавторизованным или
не принимает нужный private chat.

Причина: указан chat id вместо Telegram user id, id владельца отсутствует в
`TELEGRAM_OWNER_IDS`, список записан с ошибкой.

Что писать в отчете:

```text
Блокеры:
- Telegram delivery заблокирована: TELEGRAM_OWNER_IDS не задан или не совпадает
  с Telegram user id владельца. Нужна проверка owner id в secret env gateway.
```

### State dir недоступен

Симптом: после сообщения владельца gateway не сохраняет `owner_chat_id`, а
после restart снова теряет привязку.

Причина: каталог state file не создан или не writable для service user.

Что писать в отчете:

```text
Блокеры:
- Telegram delivery нестабильна: gateway не может сохранить state file с
  owner_chat_id. Нужно проверить state directory и права service user.
```

## Итоговая рекомендация

Документы уже достаточно хорошо задают безопасный маршрут и формат письма.
Следующий документационный шаг - встроить prompt-блок "Telegram owner report" в
automation templates и role prompts, чтобы каждый агент завершал задачу
готовым `result.response`, а не оставлял gateway угадывать, что можно показать
владельцу.

Код в рамках этой ревизии менять не нужно. Кодовые улучшения из
`telegram-reporting-plan.md` лучше вести отдельными задачами с тестами:
env example для gateway, проверка `TELEGRAM_OWNER_IDS` в installer, state dir в
systemd unit, расширение forbidden markers и отдельный feed -> Telegram bridge,
если он действительно понадобится.

## Проверки этой ревизии

- Прочитан `docs/agent-work/telegram-reporting-plan.md`.
- Прочитан `docs/agent-work/telegram-report-letter-template.md`.
- Подготовлен этот документ:
  `docs/agent-work/telegram-document-report-review.md`.
- Кодовые файлы не изменялись.
