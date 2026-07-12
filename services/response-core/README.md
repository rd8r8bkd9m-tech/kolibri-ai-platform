# Kolibri response core

Internal, loopback-only Rust adapter for the first durable Responses slice. It
persists public sessions, responses, events, cancellation idempotency and the
transactional outbox exclusively in PostgreSQL. It does not execute providers,
own task scheduling, expose public credentials, or bind externally.

The process requires `DATABASE_URL`. Migrations run only when
`KOLIBRI_RESPONSE_CORE_RUN_MIGRATIONS=1` is set. The listener defaults to
`127.0.0.1:9202`; a non-loopback bind is rejected.

Internal RPC routes correspond one-for-one with
`backend.kolibri_edge.core.CoreClient`:

- `POST /internal/v1/public-sessions`
- `POST /internal/v1/public-sessions/resolve`
- `POST /internal/v1/responses`
- `POST /internal/v1/responses/get`
- `POST /internal/v1/responses/events`
- `POST /internal/v1/responses/cancel`

The raw public-session credential appears only in the issue response. The
database stores its SHA-256 hash and exact normalized Origin.
