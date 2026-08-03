# Estimate document lifecycle

Kolibri V3 treats an official document as a release of one exact
`EstimateVersion`, not as a mutable export cache.

```text
EstimateVersion + ProjectContext + PriceEvidence + CommercialTerms
        ↓ validated Decimal snapshot
EstimateDocumentSnapshot (immutable source hash)
        ↓ official_ru_v1
PDF / DOCX / XLSX / ZIP + manifest (tenant-scoped CAS)
```

`estimate_document_issues` stores the issue number, lifecycle status,
renderer version, source hash and canonical snapshot. `estimate_document_artifacts`
stores final-byte hashes and opaque CAS references. Profile/project edits never
rewrite an existing issue. Repeating an idempotent request or downloading an
issue returns the same persisted bytes.

## Status policy

- `needs_input`, `calculating` and `failed` do not produce an official release.
- `draft` may produce a clearly marked `PRELIMINARY` package.
- `ready` may produce an `issued` package.
- A stale or preliminary price blocks `mode=issue` until evidence is refreshed.
- A universal generated estimate cannot become `ready` when its project
  technology-card reference, operation lineage, required quantity basis or
  evidence for `source_backed` / `verified` rows is missing.
- An invoice is rendered only when real contractor requisites, a customer and a
  payment basis are present.

The browser calls `POST /api/v3/projects/{projectId}/estimate/document-pack`
with CSRF and `Idempotency-Key`; the backend resolves tenant, user, exact
version, parties and totals. Downloads are served through the authenticated
artifact endpoint and the legacy `estimate/export/{format}` endpoint remains
compatible, with optional `version` and `kind` selectors.

Large estimates are read in bounded pages by web/mobile, but renderers resolve
the complete saved `EstimateVersion` on the backend. Chat contains only a
compact project/document/version reference; neither pagination nor tool-argument
limits may truncate an official snapshot. See
[`ESTIMATE_GENERATION_ORCHESTRATION.md`](ESTIMATE_GENERATION_ORCHESTRATION.md).

The renderer uses repository Noto Sans assets and the canonical Koli mascot.
It does not fetch URLs or accept template paths from a model. The PDF is A4
portrait with a restrained dark-green/teal print layout; hashes remain in
metadata/headers/manifest, never in the visible footer.
