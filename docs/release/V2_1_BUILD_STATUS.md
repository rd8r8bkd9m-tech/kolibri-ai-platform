# Kolibri AI OS V2.1 build status

This branch is a clean implementation foundation, not a signed production release.

Local release evidence must include:

- architecture gate;
- backend/API tests;
- frontend component tests;
- production Vite build;
- browser E2E screenshots;
- factory canary;
- materialized PDF/XLSX/DOCX bytes and hashes;
- Rust shadow tests in CI.

Still required for production: PostgreSQL/JetStream/CAS cutover, Home deployment, real worker-loss recovery, 21/21 capability campaign, signed rollout and 24-hour soak.

## Последнее подтверждённое усиление

- OpenAI-compatible API key lifecycle: create/list/revoke, raw key shown once, SHA-256 at rest;
- Bearer authentication for Models, Responses, Realtime and provider gateway;
- provider gateway requires developer/owner and uses only server-side project/organization scope;
- streaming/query/body/provider request ID transport covered by integration tests;
- full local release-check green.
