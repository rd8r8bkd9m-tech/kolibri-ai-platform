# Kolibri AI OS V2.1

Clean Home-first foundation: один проектный диалог, OpenAI-compatible `/v1`, контекстные вертикали, materialized artifacts и доказательная фабрика.

## Что реально работает в этой ветке

- POST-first bootstrap без 401/403 шума;
- проекты, история, soft delete и restore;
- durable Responses с idempotency, SSE resume и cancel;
- публичная модель `kolibri`;
- настоящая вертикаль смет: items, источники, deterministic totals, revisions;
- реальные PDF/XLSX/DOCX/JSON/Markdown с MIME, size и SHA-256;
- persistent task queue, lease, fencing, artifact gate и verifier binding;
- безопасный node runtime без arbitrary shell;
- Morphing Conversation Shell без постоянного меню вертикалей;
- capability visibility только при route + executor + renderer + evidence + policy;
- Rust shadow contracts для response/task state.

## Локальный запуск

```bash
./scripts/dev.sh
```

Shell: `http://127.0.0.1:5191`
API: `http://127.0.0.1:8191`

## Полная локальная проверка

```bash
./scripts/validate.sh
```

## Factory canary

В одном терминале запустите API, затем:

```bash
KOLIBRI_NODE_JOIN_TOKEN=canary-secret ./scripts/factory-canary.sh
```

## Честная граница

SQLite и Python в этой ветке — локальный clean V2 foundation и compatibility gateway. PostgreSQL, JetStream, SeaweedFS, Rust authority, Home rollout, 21/21 campaign и 24-hour soak остаются отдельными production gates.

## Release evidence

Полный локальный контрольный цикл:

```bash
./scripts/release-check.sh
```

Он проверяет архитектурный закон, OpenAPI, backend, frontend, production build,
browser E2E, реальные PDF-байты, безопасность исходников, CycloneDX SBOM и
аутентифицированный factory canary.

## OpenAI-compatible SDK

Developer/owner создаёт `sk-kolibri-*` key через `/v1/api-keys`. После этого OpenAI-compatible SDK использует:

```python
from openai import OpenAI
client = OpenAI(api_key="<KOLIBRI_API_KEY>", base_url="https://kolibriai.ru/v1")
response = client.responses.create(model="kolibri", input="Привет")
```

Raw key показывается один раз; в хранилище остаётся SHA-256. Подробнее: `docs/api/OPENAI_COMPATIBILITY.ru.md`.

## Controlled Docker deployment

```bash
cp .env.example .env
# замените все placeholder-секреты
docker compose up --build -d
```

Shell: `http://localhost:8080`.

Это single-server release candidate. PostgreSQL/JetStream/SeaweedFS, Home
rollout, физический 3-node canary, кампания 21/21 и 24-часовой soak остаются
обязательными production gates.
