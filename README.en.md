# Vista OS 11.1 Product Release

Vista OS is a single-window AI operating workspace. It exposes one entry point, one shell and one conversational control surface. Apps are rendered only when the current role, plan and intent allow them.

The first product vertical is implemented end to end:

```text
project brief
→ editable construction estimate
→ server-side totals
→ estimate version
→ verifier-gated factory task
→ PDF / XLSX / DOCX / JSON / Markdown
→ SHA-256 evidence
→ secure client share
→ download and revocation
```

## Implemented product capabilities

- strict FastAPI Core API with no production demo fallback;
- SQLite WAL persistence and tenant/session isolation;
- signed HMAC session tokens;
- real estimate CRUD and server-side calculations;
- real PDF/XLSX/DOCX/JSON/Markdown files;
- client artifact vault, hashes and expiring share links;
- workspace/chat/active-project restoration after reload;
- capability-rendered roles;
- transparent OpenAI-compatible `/v1/*` and Realtime gateway;
- node registry, queue, leases, worker execution, artifacts and verifier;
- installable PWA, hardened Docker deployment and Tauri 2 shell;
- 1000 machine-readable agent roles.

## Local start

```bash
./scripts/dev-fone.sh
```

## Validation

```bash
./scripts/validate-fone.sh
./scripts/release-check.sh
```

## Production Docker

```bash
cp .env.example .env
# Replace all secrets and origins
docker compose up --build -d
```

The local authenticated factory canary is proven. A public 24/7 distributed-fleet claim still requires a real three-server canary and operational observation.

## Release documents

- [Build report](docs/release/VISTA_OS_11_1_BUILD_REPORT.md)
- [Architecture](docs/architecture/VISTA_OS_11_ARCHITECTURE.md)
