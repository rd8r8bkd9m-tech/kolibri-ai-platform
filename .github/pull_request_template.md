## Что изменено

<!-- Одна связанная проблема и пользовательский результат. -->

## Контракт и границы

<!-- API/schema/state/auth/artifact/release changes. Укажите, что не входит в scope. -->

## Проверки

<!-- Только реально выполненные команды и E2E. Не пишите PASS без evidence. -->

- [ ] Frontend lint/test/build либо объяснено, почему не применимо
- [ ] Backend tests либо объяснено, почему не применимо
- [ ] Desktop/mobile browser E2E для UI change
- [ ] Negative/auth/isolation cases для public data change
- [ ] Full artifact lifecycle для capability change

## Evidence

<!-- Screenshots, sanitized logs, artifact SHA-256, request/release IDs. Без секретов. -->

## Риск и rollback

<!-- Migration, compatibility, canary and exact rollback path. -->

## Truth and safety checklist

- [ ] Нет mock, placeholder, decorative dead control или fake success
- [ ] Capability UI следует backend registry
- [ ] Нет credentials, cookies, `.env`, PII или runtime artifacts
- [ ] Production/DNS/firewall/credentials не менялись из этого PR
- [ ] Документация соответствует фактическому поведению
- [ ] Известные ограничения перечислены явно
