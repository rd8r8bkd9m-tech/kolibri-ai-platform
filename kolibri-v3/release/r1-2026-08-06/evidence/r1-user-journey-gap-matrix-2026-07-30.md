# R1 user-journey gap matrix — 2026-07-30

Status vocabulary:

- `PROVEN` — current public boundary and required result are covered together.
- `PARTIAL` — component tests exist, but the release journey is not proven.
- `MISSING` — the required production behavior does not exist.
- `BLOCKED` — implementation exists, but the named external gate is absent.

This is a gap register, not release evidence.

| Step | Required journey | Status | Current evidence | Exact next gate |
|---:|---|---|---|---|
| 1 | Register and obtain browser session | PROVEN | identity API tests; cookie + same-origin contract | repeat in full post-migration suite |
| 2 | Native login/refresh/logout | PROVEN | mobile auth tests; hash-only refresh family | repeat bearer matrix after auth integration |
| 3 | Send, resume and cancel one AG-UI run | ACTIVE | durable events/cancel exist; bearer resume integration is landing | full cookie+bearer send/resume/cancel regression |
| 4 | Ask a simple warm-model question | PARTIAL | local real response and runtime tests exist | save run-ID-correlated ack/event/text/completion timing |
| 5 | Ask Moscow weather and receive dated sourced UI | PROVEN | authenticated cookie+CSRF AG-UI E2E, dated/sourced tool payload, durable trace and tenant isolation; see `local-weather-agui-journey-2026-07-30.md` | repeat against the approved live provider on the immutable candidate |
| 6 | Generate and persist an image artifact | PROVEN | provider-neutral `image.generate`, tenant-scoped CAS bytes, immutable artifact manifest, authenticated retrieval and restart recovery pass locally; see `local-generated-image-artifact-journey-2026-07-30.md` | bind the approved live image provider and repeat on the immutable Safari/Android candidate |
| 7 | Attach files, including failure/retry states | PROVEN | authenticated bounded upload, MIME/signature/oversize rejection, retry idempotency, tenant/user isolation, durable message refs and native retrieval pass locally; see `local-bounded-attachment-journey-2026-07-30.md` | repeat in the complete immutable-candidate journey and add audited orphan-CAS retention/GC |
| 8 | Create an estimate from chat | PROVEN | authenticated bearer AG-UI E2E auto-creates the project/thread, persists estimate version 1 and binds `originRunId`; see `local-public-estimate-agui-journey-2026-07-30.md` | repeat on the immutable candidate and include it in the complete browser journey |
| 9 | Open and edit the estimate | PROVEN | versioned GET/PATCH tests and real web/native clients | repeat inside the complete journey |
| 10 | Resolve a stale-version conflict without losing draft | PARTIAL | backend 409 and native optimistic-conflict tests pass | browser interaction proof preserving local draft and showing diff |
| 11 | Export one version to PDF/XLSX/DOCX | PROVEN | all three formats are generated and inspected from one version | repeat hashes/totals in complete journey |
| 12 | Return editor → chat with draft and scroll preserved | PARTIAL | workspace navigation/state contracts exist | browser interaction replay on the current build |

## P0 order after core runtime/auth gates

1. Public AG-UI estimate creation journey.
2. Weather E2E with run timings and source/date truth.
3. Provider-neutral durable image artifact.
4. Bounded attachment upload and failure states.
5. Browser estimate conflict and editor-return interaction replay.
6. One complete production-build smoke using only public boundaries.

## Non-negotiable rules

- No step may require direct database edits in release evidence.
- A visible primary control cannot remain decorative.
- Unsupported functionality is removed or explicitly unavailable; it is never
  represented by a successful-looking fake response.
- PDF, XLSX and DOCX must reference the same estimate version and totals.
- Image and attachment bytes are stored outside chat JSON; chat retains only
  bounded artifact metadata and server-issued identifiers.
- Browser cookies/CSRF and native bearer authentication remain separate
  transports over the same tenant/user authority.
