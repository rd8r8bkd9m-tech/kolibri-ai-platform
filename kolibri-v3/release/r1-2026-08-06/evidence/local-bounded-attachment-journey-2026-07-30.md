# Local bounded attachment journey — 2026-07-30

Status: **PROVEN locally for the R1 attachment scope**.

This evidence covers the public Product Chat attachment boundary. It does not
claim production deployment evidence.

## Proven public journey

`backend/tests/test_attachment_journey.py::
test_public_attachment_journey_uses_only_authenticated_http_boundaries`
performs the release path without direct database writes:

1. registers a browser user and obtains the opaque session plus CSRF cookie;
2. creates a durable chat/project through `POST /v1/chat/ag-ui`;
3. discovers the server-issued project scope through `GET /v1/chat/threads`;
4. reads the backend attachment capability for that exact project/thread;
5. uploads raw bytes with browser cookie, same-origin and CSRF authority;
6. sends the server-issued attachment URL in an AG-UI user message;
7. recovers the immutable attachment ref from durable chat history;
8. reads the same bytes with a native bearer token for the same user;
9. proves anonymous access is rejected after logout;
10. proves another tenant receives `404` for the same content identifier.

The deterministic test intentionally has no model provider connected for the
attachment turn. The accepted message remains durable and the run returns a
real `RUN_ERROR`; it never fabricates a successful processing result.

## Boundary and storage contract

- Browser mutation: opaque cookie + explicit allowlisted `Origin` + bound
  double-submit CSRF token.
- Native mutation: validated mobile bearer token; browser CSRF is not reused.
- Authorization scope: tenant, user, project and canonical thread are checked
  before and again at metadata commit. Retrieval requires the exact tenant and
  user.
- R1 upload limit: 10 MiB per file, below the 50 MiB product contract ceiling.
- Message limit: at most 10 unique attachment refs.
- MIME allowlist: PDF, DOCX, XLSX, bounded text/data formats and selected image
  formats. SVG is not accepted. Structured binary formats receive signature
  checks.
- Upload body: streamed to a private temporary file while SHA-256 and byte
  count are computed. Chat JSON never receives file bytes or base64.
- Durable content: tenant-partitioned content-addressed filesystem storage with
  opaque `cas://sha256/...` references, private modes, no caller paths,
  symlink rejection, collision verification and retrieval-time size/hash
  verification.
- Retry: the attachment ID is also the idempotency key. An exact retry returns
  the original metadata; changed bytes or metadata return `409`.
- Message persistence: `chat_message_attachment_refs` stores immutable
  artifact ID/version, SHA-256, filename, MIME and size snapshots. History
  projects these records as canonical AG-UI URL parts.
- UI: the assistant-ui adapter is installed only after the authenticated
  backend confirms capability for the current persisted project/thread. A
  failed upload never becomes a complete composer attachment.
- BFF: same-origin Next routes stream request and response bodies and forward
  only the bounded auth/attachment headers.

## Negative and recovery gates

The focused suite proves:

- missing/stale browser CSRF is rejected;
- unsupported SVG and spoofed PNG are rejected;
- declared and streamed oversize bodies are rejected and temporary files are
  removed;
- same-key changed-content retries return `409`;
- same-tenant other-user and cross-tenant reads return `404`;
- storage bytes changed without changing file size are detected and return
  `410`;
- exact chat retries keep one durable message attachment ref;
- generated-image artifacts continue to use the same verified CAS/content
  route.

## Local gate results

```text
PYTHONPATH=backend backend/venv/bin/python -m pytest -q \
  backend/tests/test_attachment_journey.py
4 passed

PYTHONPATH=backend backend/venv/bin/python -m pytest -q \
  backend/tests/test_attachment_journey.py \
  backend/tests/test_image_artifact_journey.py
8 passed

npm run typecheck
passed

node --test \
  tests/product-chat-attachments.test.mjs \
  tests/generated-image-journey.test.mjs
3 passed

npm test
107 passed
```

After the schema-version recovery assertion was updated and migration 042 was
made replay-safe, the integrated backend suite passed at `244 passed`.

## Remaining operational work

Unreferenced CAS objects can remain after a post-stream validation or
idempotency rejection, and composer removal intentionally does not delete
immutable server metadata. Production retention/garbage collection must use a
separate audited server-owned maintenance job; it is not delegated to the
browser.
