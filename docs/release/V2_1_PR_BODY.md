# feat(v2.1): rebuild Kolibri AI OS on clean Home-first foundation

## Summary

This pull request replaces the legacy Vista/Fone application line with the clean Kolibri AI OS V2.1 foundation defined by the Home-first plan.

- one Home Control Plane identity;
- Morphing Conversation Shell;
- OpenAI-compatible `/v1` and public model `kolibri`;
- durable Responses, projects, history, SSE resume, cancel, and restart reconciliation;
- source-backed estimates with deterministic totals and immutable revisions;
- materialized PDF/XLSX/DOCX/JSON/Markdown artifacts with MIME, size, and SHA-256;
- persistent tasks, leases, fencing, required artifacts, and verifier binding;
- Rust shadow state contracts;
- FormulaLM sanitized trace boundary;
- no legacy runtime fallback, demo success, or permanent vertical menu.

## OpenAI compatibility

- Bearer `sk-kolibri-*` API keys;
- raw key shown once, SHA-256 stored at rest;
- create/list/revoke lifecycle;
- authenticated Models, Responses, Chat Completions, and Realtime;
- server-side fail-closed provider gateway;
- upstream provider credentials and project scope are never taken from the browser/client;
- integration tests cover method/query/body, SSE, and upstream request IDs.

## Validation

Local release check at commit `49848aad7ad173cb2cfe89d65a097d4314178e0c`:

- architecture gate: passed;
- backend/API/security tests: 15 passed;
- frontend component tests: 2 passed;
- TypeScript + production Vite build: passed;
- browser product E2E: 14 checks passed;
- browser console/page errors: 0;
- real PDF bytes and SHA-256: passed;
- authenticated factory canary: passed;
- source security scan: 0 findings;
- CycloneDX SBOM: generated;
- working tree after commit: clean.

## Known production gates

This is a single-server release candidate, not the signed distributed production release. Still required:

- Rust workspace CI and parity evidence;
- Docker build on a clean runner;
- PostgreSQL / JetStream / replicated CAS cutover;
- physical three-node canary with worker-loss recovery;
- fresh 21/21 verified capability campaign;
- signed rollout and rollback evidence;
- 24-hour soak.

## Rollback

The previous donor commit remains reachable as `23c693373270fc87a71a2b252ad1c35e252f417c`. No production switch is performed by this pull request.
