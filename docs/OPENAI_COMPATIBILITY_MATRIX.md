# Kolibri OpenAI compatibility matrix

Status: explicit subset, verified against OpenAI OpenAPI `2.3.0` on
2026-07-11. This document does not claim full OpenAI API compatibility.

The machine-readable authority is
`GET /v1/kolibri/openai-compatibility`. Its `available` and `conformance`
fields distinguish implemented operations, Kolibri extensions, and explicit
unavailable boundaries. There is no wildcard `/v1/{path}` proxy, no
organization proxy, and no admin proxy.

| Path | Method | Kolibri status | Boundary |
| --- | --- | --- | --- |
| `/v1/models` | `GET` | supported subset | Returns only the policy-routed `kolibri` model. |
| `/v1/models/{model}` | `GET` | supported subset | Only `kolibri` can be retrieved. |
| `/v1/chat/completions` | `POST` | supported subset | JSON and SSE; server policy owns provider selection. |
| `/v1/responses` | `POST` | supported subset | JSON/SSE, scoped tools, owner bearer or isolated public session. |
| `/v1/responses` | `GET` | Kolibri extension | OpenAI OpenAPI does not define response listing at this path. |
| `/v1/responses/{id}` | `GET` | supported subset | Owner/session-scoped retrieval. |
| `/v1/responses/{id}/cancel` | `POST` | supported subset | Never invents background work; terminal records remain terminal. |
| `/v1/responses/{id}/input_items` | `GET` | supported subset | Recorded inputs only; `limit`, `order`, and `after` pagination. |
| `/v1/realtime` | WebSocket | unavailable | Explicit error followed by close code `1013`; no session event is emitted. |

## Responses input items

The endpoint follows the official list envelope:

- `object: "list"`;
- `data`, `first_id`, `last_id`, and `has_more`;
- `limit` from 1 through 100, default 20;
- `order=asc|desc`, default `desc`;
- `after=<item_id>` cursor pagination.

Input item IDs are stable for a stored response. Public-session input is kept
separately from provider context so previous turns and provider-only
instructions cannot appear as the current response's input items. Optional
`include` fields are never synthesized when Kolibri did not record them.

Durable owner response creation returns HTTP `201`; isolated public-session
creation returns HTTP `200`. Unlisted OpenAI methods and operations are
unavailable and return `404`; discovery never implies support for every method
sharing a listed path.

## Realtime boundary

OpenAI Realtime is a long-lived session protocol over WebRTC, WebSocket, or
SIP. Kolibri currently has no compatible session backend, audio transport, or
Realtime event engine. Therefore:

- an HTTP probe of `GET /v1/realtime` returns `501` with
  `code=realtime_unavailable`;
- a WebSocket connection receives one `error` event and closes with `1013`;
- no `session.created`, transcript, audio, response, or tool event is
  fabricated;
- related REST paths such as `/v1/realtime/sessions` remain absent (`404`).

## Official references

- [Responses input items — list](https://developers.openai.com/api/reference/resources/responses/subresources/input_items/methods/list)
- [Realtime and audio](https://developers.openai.com/api/docs/guides/realtime)
- [OpenAI API overview](https://developers.openai.com/api/reference/overview)
