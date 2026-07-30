# Kolibri V3 Product Kernel

Status: implementation contract for the new V3 backend.

This runtime is intentionally isolated from `kolibri-backend`. The old service
is not an upstream, a fallback, or a source of session, chat, project, provider,
or profile state.

## User flow

1. A user registers or signs in through the same-origin V3 web application.
2. The backend issues an opaque, revocable, HttpOnly session cookie.
3. The user chooses `auto`, `mimo-code`, or `codex-cli` in the personal account.
4. The assistant-ui composer sends an official AG-UI run.
5. On the first accepted user message, one database transaction creates:
   - a project;
   - a construction object, even when the prompt does not name one;
   - the primary chat thread;
   - empty document slots for source data, estimate, proposal, and contract;
   - the user message and durable run record.
6. The server resolves the permitted provider, streams only public answer
   events, and commits the assistant message.
7. Reloading the application restores the thread list, messages, profile, and
   selected provider from backend state.

## Logical boundaries

```text
Browser
  assistant-ui primitives + AG-UI runtime
        |
        | same-origin /api/v3/*
        v
Next BFF
  cookie relay, bounded payloads, no credentials in client state
        |
        v
Kolibri V3 backend
  Identity + Product/Data + provider policy
        |
        v
Logical Home Control Plane
        |
        v
Provider Execution Authority on physical Primary
  MiMo Code Token Plan + official Codex CLI login
```

The provider runtime is not part of the Product/Home process. It returns only
typed results and sanitized connection evidence over a server-authenticated
contract.

## Public API v1

Identity and profile:

- `POST /v1/auth/register`
- `POST /v1/auth/login`
- `POST /v1/auth/logout`
- `GET /v1/session`
- `GET /v1/profile`
- `PATCH /v1/profile`
- `PUT /v1/profile/agent-profile`

Provider administration is exposed only through the same-origin, fail-closed
superadmin BFF:

- `GET /api/superadmin/provider-connections`
- `POST /api/superadmin/provider-connections/{provider_id}/enrollments`

Enrollment has an empty request body. Browser code never accepts or forwards a
provider credential; secret material and the actual authorization runtime stay
inside Provider Execution Authority. The BFF verifies subject, tenant, current
owner role, expiry and revocation against the V3 backend on every request.
Provider mutations additionally require the session-bound CSRF proof. If that
proof or the authority service is unavailable, the route fails closed.

Chat:

- `GET /v1/chat/threads`
- `POST /v1/chat/threads`
- `GET /v1/chat/threads/{thread_id}/messages`
- `POST /v1/chat/ag-ui`

All mutation requests require an authenticated cookie session, an allowed
origin, and an idempotency key where the operation can be retried.
Provider mutations additionally require the `owner` role.

## AG-UI contract

Accepted input is a bounded official AG-UI run containing `threadId`, `runId`,
`messages`, `state`, `tools`, `context`, and `forwardedProps`. In v1, `state`
must be `null`, while `tools` and `context` must be empty arrays. Browser code
cannot contribute authority-bearing state or system context. Unknown top-level
fields, non-text first-slice message parts, stale tenant-bound identifiers, and
unknown provider profiles fail closed.

The public stream can contain:

- `RUN_STARTED`
- `TEXT_MESSAGE_START`
- `TEXT_MESSAGE_CONTENT`
- `TEXT_MESSAGE_END`
- `RUN_FINISHED`
- `RUN_ERROR`

Reasoning payloads, provider tokens, Codex auth files, raw commands, local
paths, stderr, and provider-internal model identifiers are never sent to the
browser.

## Provider policy

- `auto` selects only a connected and successfully probed provider.
- `mimo-code` is executed only by Provider Execution Authority; its Token Plan
  credential never crosses into the browser or Product/Home.
- `codex-cli` uses the official login owned by Provider Execution Authority;
  it is never installed or authorized on Product/Home by this application.
- An unavailable requested provider produces a typed error. There is no echo,
  fake assistant response, or silent provider fallback.

## Initial document slots

The first message creates empty, versioned slots rather than invented document
content:

- `source-data`
- `estimate`
- `commercial-proposal`
- `contract`

The model may later draft content, but publication, signature, payment, and
marketplace ordering remain separately authorized actions.
