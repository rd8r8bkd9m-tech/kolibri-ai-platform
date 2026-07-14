# Contributing to Kolibri AI OS

Спасибо за вклад. Проект принимает изменения через небольшие, проверяемые pull
requests. Код, продуктовые claims и evidence должны описывать одно и то же
состояние системы.

## До начала работы

1. Проверьте существующие issues и pull requests.
2. Для существенного изменения сначала создайте issue с пользовательским
   сценарием, границами scope и acceptance criteria.
3. Для security-проблем не создавайте публичный issue — следуйте
   [SECURITY.md](SECURITY.md).
4. Не включайте в задачу production credentials, cookies, browser sessions,
   внутреннюю топологию или персональные данные.

## Среда

Используйте версии из корня репозитория:

- Node.js — [`.node-version`](.node-version);
- Python — [`.python-version`](.python-version);
- Rust — [`rust-toolchain.toml`](rust-toolchain.toml).

Установка зависимостей должна быть воспроизводимой:

```bash
cd kolibri-v2 && npm ci
cd ../kolibri-backend
python -m pip install --require-hashes -r requirements.lock
```

Не коммитьте `.env`, runtime artifacts, локальные БД, caches, build output или
provider responses.

## Правила изменения

- Один pull request решает одну связанную задачу.
- Не добавляйте mock success, декоративные кнопки или capability, которую
  backend не может реально вызвать.
- UI получает доступность инструментов из canonical capability registry.
- Денежные итоги рассчитывает deterministic Decimal engine, а не свободный
  текст модели.
- Любой artifact должен иметь bytes, MIME, size, SHA-256, scope и reopen path.
- Новые public routes обязаны проверять server-issued principal/scope.
- Provider failure не превращается в `completed` без подтверждённого fallback.
- Не меняйте production, DNS, firewall, credentials или release symlink из PR.

## Проверки

Минимум перед review:

```bash
cd kolibri-v2
npm run lint
npm run test
npm run build

cd ../kolibri-backend
python -m pytest app/tests/ -v

cd ..
python scripts/verify_toolchains.py
```

Для пользовательских изменений добавьте desktop/mobile browser E2E. Для
capability приложите evidence полного пути:

```text
invoke → provider/tool → result/bytes → persistence
→ renderer/download → reopen → integrity verdict
```

Heartbeat, импорт модуля, наличие env-переменной или текст модели не являются
execution proof.

## Pull request

PR должен содержать:

- проблему и ожидаемый пользовательский результат;
- изменённые контракты и migration/rollback notes;
- точные выполненные проверки;
- screenshots для визуальных изменений;
- известные ограничения без эвфемизмов;
- отсутствие secrets и лишних generated files.

Reviewer вправе запросить независимую проверку для auth, billing, release,
artifacts, estimates и factory lease logic.

## Commit messages

Используйте короткий imperative subject с областью, например:

```text
fix(shell): preserve project after reload
feat(estimates): persist source-backed price revision
docs: clarify capability proof contract
```

## Definition of done

Изменение готово, когда acceptance criteria воспроизводимы, негативные случаи
проверены, документация соответствует коду, а rollback понятен. Merge не равен
production release: production проходит отдельный подписанный release gate.
