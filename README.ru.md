# Vista OS 11.1 Product Release

Vista OS — единая AI-операционная рабочая среда. У пользователя одна точка входа, один shell и один диалоговый control surface. Функции появляются только по роли, подписке и текущему намерению пользователя.

Первая продуктовая вертикаль полностью проходит реальный путь:

```text
бриф объекта
→ смета и позиции работ
→ серверный расчёт
→ версия сметы
→ verifier-gated factory task
→ PDF / XLSX / DOCX / JSON / Markdown
→ SHA-256
→ защищённая клиентская ссылка
→ скачивание и отзыв ссылки
```

## Что действительно работает

- FastAPI Core API без production demo fallback;
- SQLite WAL persistence и изоляция пользовательских сессий;
- подписанные HMAC session tokens;
- реальный CRUD смет и серверный пересчёт;
- PDF/XLSX/DOCX/JSON/Markdown generation;
- client artifact vault, SHA-256 и публичные ссылки;
- восстановление активного приложения, чата и объекта после reload;
- роли `client`, `client_pro`, `operator`, `server_admin`, `developer`, `owner`;
- OpenAI-compatible transparent `/v1/*` и Realtime gateway;
- node registry, persistent task queue, lease, worker, artifact, verifier;
- PWA, Docker production shell и Tauri 2 desktop shell;
- 1000 машинных ролей агентов.

## Локальный запуск

Требования: Python 3.12+, Node.js 22+.

```bash
./scripts/dev-fone.sh
```

Открыть `http://127.0.0.1:5173`.

## Полная проверка

```bash
./scripts/validate-fone.sh
./scripts/release-check.sh
```

`release-check.sh` проверяет настоящий HTTP-сценарий, реальные документы, tenant isolation, восстановление workspace, public download/revoke, factory canary и backup/restore.

Browser E2E, Tauri native check и Docker build являются обязательными отдельными jobs в GitHub Actions.

## Production Docker

```bash
cp .env.example .env
openssl rand -hex 32 # сгенерировать каждый секрет отдельно
nano .env
docker compose up --build -d
```

Frontend: `http://SERVER:8080`  
Backend напрямую доступен только на loopback `127.0.0.1:8000`; внешний доступ идёт через Nginx `/api` и `/v1`.

## Worker-нода

```bash
sudo ./scripts/install-node.sh \
  --node-id server-002 \
  --control-url https://vista.example.com \
  --join-token "$VISTA_NODE_JOIN_TOKEN" \
  --signing-secret "$VISTA_NODE_SIGNING_SECRET" \
  --workers 2 \
  --capabilities health.probe,estimate.artifacts
```

## Честная граница

Локальный authenticated factory canary проходит. Утверждение о 24/7 распределённой фабрике требует canary на реальных control-server + worker-01 + worker-02 и наблюдения за lease recovery/alerts.

## Документы релиза

- [Отчёт о сборке](docs/release/VISTA_OS_11_1_BUILD_REPORT.md)
- [Production deployment](docs/deploy/PRODUCTION_DEPLOYMENT.ru.md)
- [Архитектура](docs/architecture/VISTA_OS_11_ARCHITECTURE.md)
