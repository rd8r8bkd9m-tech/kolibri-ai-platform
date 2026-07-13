# Kolibri AI OS V2.1

A clean Home-first foundation for one continuous project conversation, an OpenAI-compatible `/v1` API, contextual verticals, materialized artifacts, and evidence-gated factory execution.

## Proven in this branch

- POST-first browser bootstrap without expected 401/403 noise;
- projects, history, soft delete, and restore;
- durable Responses with idempotency, resumable SSE, cancel, and restart reconciliation;
- one public model: `kolibri`;
- OpenAI-style bearer API keys, stored as SHA-256 hashes and revocable;
- real estimate items, sources, deterministic totals, immutable revisions, and exports;
- real PDF/XLSX/DOCX/JSON/Markdown bytes with MIME, size, and SHA-256;
- persistent task queue, lease, fencing, required-artifact gate, and verifier binding;
- safe node runtime without arbitrary shell execution;
- Morphing Conversation Shell with no permanent vertical menu;
- capability visibility only after route + executor + renderer + evidence + policy gates;
- Rust shadow contracts for response and task state.

## Local start

```bash
./scripts/dev.sh
```

Shell: `http://127.0.0.1:5191`
API: `http://127.0.0.1:8191`

## Validation

```bash
./scripts/validate.sh
./scripts/release-check.sh
```

The release check runs architecture validation, OpenAPI generation, backend and frontend tests, production build, browser E2E, real PDF verification, source security scan, CycloneDX SBOM generation, and an authenticated factory canary.

## OpenAI-compatible SDK

Create a `sk-kolibri-*` key through `/v1/api-keys`, then configure an OpenAI-compatible client with `base_url=https://kolibriai.ru/v1` and model `kolibri`. Raw keys are shown once; only SHA-256 hashes remain in storage.

See `docs/api/OPENAI_COMPATIBILITY.ru.md` and `packages/contracts/openai-compatibility.json`.

## Honest boundary

SQLite and Python remain the local clean V2 foundation and compatibility gateway. PostgreSQL, JetStream, replicated S3-compatible CAS, Rust authority, Home deployment, a physical 21/21 campaign, signed rollout, and the 24-hour soak remain mandatory production gates.
