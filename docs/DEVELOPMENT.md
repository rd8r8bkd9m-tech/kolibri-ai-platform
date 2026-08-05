# Development

## Безопасное добавление регрессионных тестов

Перед вставкой нового теста рядом с существующим длинным сценарием прочитайте
файл до следующего `def` и убедитесь, что исходные `with`, `try` и `finally`
закрыты. После патча повторно просмотрите обе функции целиком: новый `def` не
должен разрывать активный клиент, транзакцию или проверку соседнего теста.

Use the branch-local Python environment for tests:

```bash
backend/venv/bin/python -m compileall -q backend ops scripts
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

Frontend checks should use the package manager already present in `frontend/`.

Do not run live deploy/bootstrap/DNS actions without approval.
### Проверки `kolibri-v3`

В `kolibri-v3` доступны `npm run typecheck`, `npm test` и `npm run build`.
Перед добавлением другой проверки сверяйте scripts в `kolibri-v3/package.json`;
отдельного `lint` script сейчас нет.

Backend V3 проверяется из каталога пакета, чтобы импорт `app` разрешался
канонически:

```bash
cd kolibri-v3
PYTHONPATH=backend backend/venv/bin/python -m pytest -q backend/tests
```

Запуск `pytest kolibri-v3/backend/tests` из корня без `PYTHONPATH` не является
валидной проверкой и завершится collection error `No module named 'app'`.

V3 использует собственное окружение `kolibri-v3/backend/venv`. Общий
`backend/venv` родительского проекта и путь `.venv` для V3 не использовать.
Перед диагностикой из каталога `kolibri-v3` проверять:

```bash
test -x backend/venv/bin/python
```

После изменения миграции или обязательных полей Product Chat projection
перезапустите локальный backend. Проверьте не только schema version и API, но и
то, что assistant-ui загрузил историю, а Composer допускает ввод: при
несовместимой history projection runtime намеренно блокирует отправку.

Полный V3 runtime запускайте только каноническим supervisor:

```bash
cd kolibri-v3
npm run dev
```

Эта команда до открытия frontend применяет миграции к точной базе
`kolibri-v3/var/kolibri-v3.db`, требует единственного активного platform owner
и проверяет launch-bound health именно поднятого экземпляра backend.
`npm run dev:web` намеренно заблокирован. Readiness считается успешным только
когда backend сообщает `service=kolibri-v3` с instance ID, а `/app` отвечает
`200`. Один HTTP 200 от HTML не доказывает, что BFF видит правильный backend.

В browser-client навигация принадлежит объекту вкладки, а DOM/locators —
вложенному Playwright API:

```js
await tab.reload();
await tab.playwright.waitForLoadState({ state: "domcontentloaded" });
await tab.playwright.domSnapshot();
```

Не вызывайте `reload()` или `documentation()` на `tab.playwright`.

IAB handles из `browser.user.openTabs()` не являются постоянными tab IDs.
Перед каждым новым `claimTab` получайте свежий список, выбирайте точный объект
по URL/title и передавайте этот объект целиком. Не переиспользуйте старый
handle после предыдущего claim.

Для локального Home/AgentHost smoke создавайте разные временные bearer/HMAC
файлы с правами `0600`; содержимое не печатайте и не переиспользуйте между
каналами:

```bash
umask 077
openssl rand -hex -out <runtime-dir>/product-bearer.token 32
openssl rand -hex -out <runtime-dir>/product-identity-hmac.key 32
openssl rand -hex -out <runtime-dir>/agent-control.token 32
openssl rand -hex -out <runtime-dir>/provider-execution.token 32
chmod 600 <runtime-dir>/*
ls -l <runtime-dir>
wc -c <runtime-dir>/*
```

В используемой OpenSSL длина обязана быть последним позиционным аргументом.
Проверка выводит только режим/имена/размер, но не секретный материал.

### Локальная ротация учётных данных owner

Ротация email/пароля локального owner выполняется только после явного запроса
владельца и одной атомарной транзакцией Product DB:

1. создать SQLite backup и проверить его через `PRAGMA integrity_check`;
2. подтвердить, что в БД ровно один `role='owner'`, а новый email не занят;
3. получить пароль через защищённый интерактивный ввод либо сгенерировать его
   внутри процесса, не передавая в argv и не сохраняя в исходниках;
4. использовать штатный `app.security.hash_password` и сразу проверить digest
   через `verify_password`;
5. обновить `email_normalized`, `email`, `password_hash`, `updated_at`, отозвать
   активные owner-сессии и записать разрешённый audit-event `profile_updated`
   с метаданными только об изменённых полях;
6. после commit проверить единственность owner, scrypt-схему, отсутствие
   открытых старых сессий, integrity/FK и настоящий login через BFF.

`identity_events.event_type` имеет CHECK-allowlist. Нельзя придумывать новый
тип события в ad-hoc SQL: сначала требуется versioned migration и тест. При
любой ошибке до commit транзакция закрывается rollback, после чего состояние
проверяется read-only запросом.

### Поиск необязательных файлов в zsh

Не передавайте необязательный glob вроде `.env.example*` неэкранированным
аргументом в `zsh`: при отсутствии совпадений оболочка завершит всю команду до
запуска `rg`. Сначала находите существующие пути через `rg --files` либо
передавайте только явно подтверждённые файлы.

Перед любым ad-hoc SQLite SELECT по runtime-таблице сначала выполняйте
`PRAGMA table_info(<table>)`. Нельзя переносить имена полей из соседней
projection или угадывать `state`/`last_error_code`: один неверный столбец
отменяет весь диагностический запрос и задерживает incident recovery.

### Диагностика процессов на macOS

Не угадывайте абсолютный путь к системной утилите. Сначала разрешите его:

```bash
command -v ps
```

В текущем локальном окружении используется `/bin/ps`; `/usr/bin/ps`
отсутствует. При фильтрации окружения процесса выводите только заранее
разрешённые имена переменных и никогда не печатайте значения токенов,
паролей или HMAC-ключей.
