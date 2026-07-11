# Artifact runtime compatibility API

Status: implemented Python compatibility boundary, 2026-07-10.

This slice implements durable declarations for Canvas, Preview,
BrowserSession, Estimate, Document, Build, and Automation without claiming
that a renderer, browser, build runner, or automation scheduler has run.

## Truth model

- Canvas graph validation and deterministic estimate calculation are performed
  synchronously and may report `active` and `calculated` respectively.
- Preview, browser session, document, and build requests are persisted as
  `queued`. They remain queued until a separately authenticated runtime adapter
  produces evidence; the public compatibility handler has no success mutation.
- An enabled automation is `degraded` while the scheduler adapter is
  unverified. A disabled automation is `inactive`.
- Cancellation is an idempotent SQLite transaction containing the record state
  change, durable event, and pending outbox item.
- No compatibility handler invokes a shell, filesystem, browser, DNS resolver,
  URL, renderer, or build command.

## Routes

Each collection supports `POST`, `GET`, and `GET /{id}`. Every resource has
`GET /{id}/status`. Preview, browser session, document, and build also support
idempotent `POST /{id}/cancel`.

Validation routes are side-effect-free:

- `POST /v1/canvases/validate`
- `POST /v1/previews/validate`
- `POST /v1/browser-sessions/validate`
- `POST /v1/estimates/validate`
- `POST /v1/documents/validate`
- `POST /v1/builds/validate`
- `POST /v1/automations/validate`

Validation never creates a durable domain record and returns
`executed: false`.

## URL and browser boundary

Only `http` and `https` are accepted. URL userinfo, loopback, link-local,
private, reserved, ambiguous numeric, single-label, local/internal, and cloud
metadata targets are rejected before persistence.

Syntax validation is not treated as DNS proof. Every domain-bearing runtime
record requires the adapter to:

1. resolve immediately before navigation;
2. reject the entire result when any address is not globally routable;
3. pin the public address set for the navigation;
4. re-resolve before every redirect;
5. fail on address-set changes.

This contract prevents the API from making network calls and moves
DNS-rebinding enforcement to the component that actually owns the connection.

## Deterministic estimates

Inputs contain `quantity` as Decimal text and `unit_price_minor` as an integer.
Every line, overhead, and tax calculation uses Decimal with `ROUND_HALF_UP` and
returns only integer minor-unit totals. The output includes the formula version
and a deterministic SHA-256 fingerprint. LLM output is never accepted as a
monetary total.

## Remaining adapter work

The compatibility API deliberately does not provide a public route that can
mark queued work ready. Production completion requires authenticated Agent Host
adapters, immutable output artifacts, fenced attempts, and verifier evidence.
Those execution adapters are a separate rollout gate.
