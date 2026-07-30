# Authenticated generated-image artifact journey — 2026-07-30

Release task: R1-008, durable image artifact

## Result

`PROVEN` on the canonical local V3 HTTP and AG-UI boundary with a
deterministic provider fixture.

The mobile “Создать изображение” action now submits through the same
authenticated assistant-ui / AG-UI runtime as ordinary chat. The server first
asks for style, format and purpose, then invokes a provider-neutral
`image.generate` capability. A production configuration without a usable
image capability fails closed; it cannot persist or display a fabricated
success.

No production system, external image service or secret was contacted.

## Contract covered

The deterministic integration journey proves:

1. cookie authentication and same-origin CSRF protect the AG-UI mutation;
2. the starter action produces the canonical clarification without calling a
   provider;
3. the next description invokes exactly one injected provider-neutral image
   capability;
4. the provider bytes are signature-checked and bounded to 50 MiB before
   persistence;
5. bytes are stored in tenant-partitioned content-addressed storage, not in
   `chat_messages` JSON or a database BLOB;
6. immutable attachment metadata and the canonical artifact v1 manifest are
   committed with the terminal tool result;
7. the tool result exposes only identifiers, version, SHA-256, media metadata
   and the authenticated same-origin content path;
8. retrieval returns the exact bytes, media type, SHA-256 header and ETag;
9. the artifact manifest passes the generated `kolibri.artifact` contract;
10. content and manifest remain readable after a complete application
    lifespan restart;
11. a second tenant receives `404` for content, artifact manifest and thread
    history;
12. an absent provider and invalid provider bytes both end in `RUN_ERROR`,
    with no assistant success, attachment row or artifact row;
13. a Home execution plane without the image capability is rejected before a
    run is accepted.

The browser renderer accepts only the typed `GeneratedImage` projection,
requires matching attachment IDs and same-origin paths, and never renders a
provider URL or base64 payload.

## Durable model

- migration `040_bounded_attachments.sql` owns shared immutable attachment
  metadata and message references;
- migration `041_generated_image_artifacts.sql` owns immutable artifact
  versions and provenance;
- the CAS reference has the form
  `cas://sha256/{tenant-digest}/{content-digest}`;
- the chat projection uses
  `/api/product/v1/attachments/{attachmentId}/content`;
- the Next.js BFF forwards that path to the authenticated V3 attachment
  endpoint and exposes the tenant-scoped artifact manifest through
  `/api/product/v1/artifacts/{artifactId}/versions/{artifactVersion}`.

The image capability is registered inside `AgentRuntimeRegistry`; the direct
executor keeps its provider-neutral registry-only signature.

CAS writes intentionally precede the relational metadata transaction. A
cancel, signature rejection or database failure can therefore leave an
unreferenced immutable blob, but it cannot create a false chat success or
cross-tenant reference. Retention and hash-safe garbage collection remain a
separate production operations task.

## Verification

Focused journey:

```text
PYTHONPATH=backend backend/venv/bin/pytest -q \
  backend/tests/test_image_artifact_journey.py
4 passed
```

Related chat, recovery, weather, auth and configuration regressions:

```text
PYTHONPATH=backend backend/venv/bin/pytest -q \
  backend/tests/test_image_artifact_journey.py \
  backend/tests/test_weather_user_journey.py \
  backend/tests/test_chat_execution_adapter.py \
  backend/tests/test_run_recovery.py \
  backend/tests/test_product_chat_auth.py \
  backend/tests/test_config.py
18 passed
```

Complete backend:

```text
PYTHONPATH=backend backend/venv/bin/pytest -q backend/tests
244 passed
```

The `244 passed` integration rerun includes attachment migration 040, image
artifact migration 041 and storage-admin migration 042.

Web contract, type system and production build:

```text
node --test tests/generated-image-journey.test.mjs
1 passed

npm run typecheck -- --pretty false
passed

npm run build
compiled, typed and generated all routes successfully
```

Portable release migration gate:

```text
node --test \
  tests/generated-image-journey.test.mjs \
  tests/portable-release.test.mjs
13 passed
```

## Remaining external gate

The release candidate still needs an approved production image provider
implementation registered behind `image.generate`, followed by a physical
Safari/Android browser replay against that provider. Until it is configured,
the runtime deliberately returns `image_generation_unavailable`; there is no
fallback image and no fake artifact.
