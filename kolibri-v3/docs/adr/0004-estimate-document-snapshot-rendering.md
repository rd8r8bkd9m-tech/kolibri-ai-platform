# ADR 0004: immutable estimate document snapshots

## Decision

Introduce tenant-scoped `estimate_document_issues` and
`estimate_document_artifacts` in migration 050. The only renderer input is a
canonical `EstimateDocumentSnapshot` built from one exact estimate version and
scoped project context. Rendered bytes are content-addressed in the existing
tenant-aware CAS.

## Rationale

Mutable project profiles, prices and templates must not silently change an
issued commercial document. Persisting the snapshot and final-byte hash gives
reproducibility, exact-version downloads, safe retries and an audit boundary
without making PDF the calculation authority.

## Consequences

- `official_ru_v1` is versioned in issue rows and cache selectors.
- Requisites are explicit tenant-owned data; invoices fail closed when fields
  are missing.
- Legacy estimate exports continue to work; `version` and `kind` select an
  already-created official artifact.
- KС-2, КС-3 and М-29 remain future extensions requiring execution evidence.
