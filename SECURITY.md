# Security Policy

## Supported versions

Security fixes применяются к текущей production release и активной ветке
подготовки следующего релиза. Точный production `release_id` возвращается в
HTTP headers и health response; имя ветки или README не подтверждают активный
релиз.

## Reporting a vulnerability

Не публикуйте уязвимость, exploit, credential или персональные данные в GitHub
Issues, Discussions, pull request или чат поддержки.

Используйте **GitHub Private Vulnerability Reporting** в разделе
`Security → Advisories → Report a vulnerability` этого репозитория. Если эта
функция недоступна, откройте обычный issue **без технических деталей** с
просьбой предоставить закрытый канал. Команда не просит присылать секреты.

В приватном отчёте укажите:

- затронутую поверхность и production `release_id`;
- минимальные шаги воспроизведения;
- ожидаемое и фактическое поведение;
- оценку влияния и условия эксплуатации;
- только обезличенные request/response fragments;
- безопасный способ связаться для уточнений.

Не прикладывайте provider keys, session cookies, owner tokens, Telegram tokens,
полные database dumps или пользовательские документы.

## Response process

После получения отчёта команда:

1. подтверждает приватное получение;
2. классифицирует impact и affected releases;
3. создаёт изолированное исправление и regression test;
4. выполняет secret scan, security checks и signed release gate;
5. выпускает исправление с rollback и, когда безопасно, advisory.

Конкретные сроки зависят от воспроизводимости и impact; автоматическое обещание
SLA этим документом не даётся.

## Security boundaries

- Public browser session отделена от owner/control identity.
- Project, file, estimate, document and artifact access требует server-issued
  scope; неизвестный или чужой объект скрывается.
- API keys показываются один раз и хранятся hash-only.
- Capability считается доступной только после policy, credential, route,
  renderer и invocation proof текущего релиза.
- Production deploy, DNS/firewall, credentials, destructive operations and
  model promotion требуют отдельного owner approval.
- Private chain-of-thought, secrets, PII и license-negative traces не входят в
  learning datasets.

## Safe research

Не выполняйте denial of service, social engineering, credential harvesting,
physical attacks, destructive tests или доступ к чужим данным. Используйте
собственный test tenant и минимальный безопасный proof of concept.
