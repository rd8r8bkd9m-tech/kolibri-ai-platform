# UIAP RAG Indexer Contract

Task: `P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01`

This is a docs-only contract for a future `uiap` RAG indexer. It does not
authorize or implement a live service, daemon, deploy change, firewall change,
nginx route or product endpoint.

## Source Of Truth

The indexer source of truth is GitHub repository content at an immutable commit
SHA. `uiap` local disk, generated artifacts, logs, virtual environments, caches
and runtime state are not source-of-truth inputs.

Minimal indexable corpus:

| Source class | Include | Exclude |
| --- | --- | --- |
| Markdown docs | `README.md`, `docs/**/*.md`, `scripts/**/README.md` | generated output, run logs, vendored dependencies |
| Skills metadata | `**/SKILL.md`, committed skill manifests | local plugin cache, secrets, private runtime state |
| Lightweight manifests | `.codex-plugin/plugin.json`, package manifests only when needed | lockfiles unless explicitly approved |

## Indexing Flow

1. Control Plane submits an index request with repository owner/name, commit
   SHA, allowed ref, source allowlist and requested collection alias.
2. `uiap` fetches GitHub content for exactly the requested commit SHA.
3. Fetcher validates that every candidate path is under the allowlist and below
   the approved size limit.
4. Parser normalizes Markdown headings, fenced code blocks, front matter and
   skill metadata into structured source records.
5. Chunker splits each record into stable chunks using heading-aware boundaries.
6. Embedder generates vectors with an approved embedding model version.
7. Writer stores chunks and metadata in a staging ChromaDB collection.
8. Validator checks counts, required metadata, duplicate chunk IDs and source
   commit consistency.
9. Promotion atomically switches the collection alias from previous active
   collection to the validated staging collection.
10. Control Plane receives a completion event with counts, source commit,
    collection name, staleness state and validation status.

## Idempotency

The index operation is idempotent for:

```text
(repo, commit_sha, corpus_profile, embedding_model, chunking_version)
```

Chunk IDs must be deterministic:

```text
sha256(repo_full_name + ":" + commit_sha + ":" + path + ":" + heading_path + ":" + chunk_ordinal + ":" + chunking_version)
```

Re-running the same request must produce the same chunk IDs and collection
metadata unless the embedding model or chunking contract changes.

## ChromaDB Strategy

Use immutable physical collections and a mutable Control Plane alias.

| Collection type | Naming contract | Purpose |
| --- | --- | --- |
| Staging | `uiap_docs_skills_staging_<short_sha>_<build_id>` | Receives a single index build |
| Active physical | `uiap_docs_skills_<short_sha>_<model_hash>_<chunking_version>` | Validated immutable collection |
| Alias | `uiap_docs_skills_active` | Control Plane points search traffic to current active collection |

Promotion is only a metadata/alias update after validation passes. Never mutate
an active physical collection in place.

## Chunking

Default chunking profile:

| Setting | Contract |
| --- | --- |
| Parser | CommonMark-compatible Markdown parser |
| Target size | 700 to 1,000 tokens |
| Maximum size | 1,200 tokens |
| Overlap | 80 to 120 tokens, only across same document section |
| Boundaries | Prefer H1/H2/H3 sections, list boundaries, then paragraph boundaries |
| Code blocks | Preserve fenced code blocks as atomic blocks when below maximum size |
| Skill metadata | Keep skill name, trigger/description, source path and referenced resources together |

Every chunk text should include a compact breadcrumb header:

```text
<repo> / <path>
<heading path>

<chunk body>
```

## Required Metadata

Every vector record must include:

| Field | Type | Description |
| --- | --- | --- |
| `chunk_id` | string | Deterministic ID defined by the indexing flow |
| `repo_full_name` | string | GitHub owner/repo |
| `commit_sha` | string | Exact source commit |
| `source_ref` | string | Requested branch/tag/ref at trigger time |
| `path` | string | Repository-relative source path |
| `source_type` | enum | `markdown_doc`, `skill_metadata`, or `manifest_metadata` |
| `title` | string | H1/title or inferred filename title |
| `heading_path` | string | `>`-delimited heading breadcrumb |
| `chunk_ordinal` | integer | Zero-based chunk number within source file |
| `chunking_version` | string | Semantic version of chunking rules |
| `embedding_model` | string | Approved embedding model identifier |
| `embedding_model_version` | string | Version or digest used for vectors |
| `content_sha256` | string | Hash of normalized chunk text |
| `indexed_at` | RFC3339 string | UTC index timestamp |
| `visibility` | enum | `control_plane_internal` until production gates approve otherwise |

Optional metadata:

| Field | Type | Description |
| --- | --- | --- |
| `skill_name` | string | Present for `skill_metadata` records |
| `skill_description` | string | Short skill description, if present |
| `front_matter` | object | Safe parsed front matter with secret-like fields removed |
| `language` | string | Best-effort document language |

## Staleness

A collection is stale when:
- active collection `commit_sha` differs from the latest approved GitHub source
  ref;
- `chunking_version` differs from the approved current version;
- `embedding_model_version` differs from the approved version;
- required source paths changed, were removed, or newly match the allowlist;
- validation policy version changed.

Status values:

| Status | Meaning |
| --- | --- |
| `fresh` | Active collection matches approved commit and policy versions |
| `stale_source` | GitHub source changed |
| `stale_policy` | Chunking, validation, or metadata policy changed |
| `stale_embedding` | Embedding model changed |
| `unindexed` | No active collection exists |
| `invalid` | Active collection failed validation or integrity checks |

## Future Control Plane Trigger

This endpoint is a future internal contract only:

```http
POST /v1/uiap/rag/index
Content-Type: application/json
Authorization: Bearer <control-plane-service-token>
```

Request body:

```json
{
  "request_id": "idx_2026_07_01_0001",
  "repo_full_name": "kolibri/kolibri-ai-platform",
  "source_ref": "main",
  "commit_sha": "0123456789abcdef0123456789abcdef01234567",
  "corpus_profile": "docs_skills_minimal_v1",
  "collection_alias": "uiap_docs_skills_active",
  "force_reindex": false,
  "requested_by": "control_plane",
  "reason": "source_commit_changed"
}
```

Validation:
- `commit_sha` must be a full 40-character Git SHA;
- `source_ref` must resolve to `commit_sha` in GitHub at request time;
- `corpus_profile` must be approved by Control Plane configuration;
- `collection_alias` must be an approved internal alias;
- `requested_by` must identify a trusted Control Plane principal.

Completion event:

```json
{
  "request_id": "idx_2026_07_01_0001",
  "job_id": "uiap-index-20260701-0001",
  "status": "promoted",
  "repo_full_name": "kolibri/kolibri-ai-platform",
  "commit_sha": "0123456789abcdef0123456789abcdef01234567",
  "collection_name": "uiap_docs_skills_0123456_modelhash_chunkv1",
  "collection_alias": "uiap_docs_skills_active",
  "source_file_count": 12,
  "chunk_count": 184,
  "quarantined_chunk_count": 0,
  "staleness": "fresh",
  "started_at": "2026-07-01T00:00:00Z",
  "finished_at": "2026-07-01T00:01:45Z"
}
```

Failure statuses include `rejected`, `failed_fetch`, `failed_parse`,
`failed_embed`, `failed_store`, `failed_validation` and `quarantined`.

## Future Internal Health And Search

The contracts below define future internal API shape only. This task does not
expose a production service, open a port, add a route, alter nginx, or change
deployment.

`GET /health` response shape:

```json
{
  "ok": true,
  "service": "uiap-rag-indexer",
  "mode": "internal_contract_only",
  "version": "0.0.0-contract",
  "collection_alias": "uiap_docs_skills_active",
  "collection_name": "uiap_docs_skills_0123456_modelhash_chunkv1",
  "repo_full_name": "kolibri/kolibri-ai-platform",
  "commit_sha": "0123456789abcdef0123456789abcdef01234567",
  "staleness": "fresh",
  "embedding_model": "approved-model-id",
  "embedding_model_version": "approved-model-version",
  "chunking_version": "docs_skills_chunking_v1",
  "source_file_count": 12,
  "chunk_count": 184,
  "last_indexed_at": "2026-07-01T00:01:45Z",
  "checks": {
    "chromadb": "ok",
    "active_collection": "ok",
    "secret_quarantine": "ok",
    "resource_budget": "ok"
  }
}
```

`POST /search` request shape:

```json
{
  "query": "How should UIAP index skills metadata?",
  "top_k": 5,
  "filters": {
    "source_type": ["markdown_doc", "skill_metadata"],
    "repo_full_name": "kolibri/kolibri-ai-platform"
  },
  "include_content": true,
  "request_id": "search_2026_07_01_0001"
}
```

Search must be Control Plane-internal until later approval explicitly changes
visibility.

## Failure Behavior

The indexer must fail closed:

| Failure | Required behavior |
| --- | --- |
| GitHub fetch denied, unavailable, or ref mismatch | Reject request and keep active collection unchanged |
| File outside allowlist | Reject file; if required corpus file, fail index |
| Secret-like detector match | Quarantine chunk, fail promotion, report redacted count |
| ChromaDB write failure | Delete incomplete staging collection if possible; keep active collection unchanged |
| Validation failure | Do not promote; report failed validation checks |

## Non-Goals

- No public `/search`.
- No production `/search` exposure.
- No background scheduler.
- No automatic indexing of unreviewed branches.
- No indexing runtime artifacts, private logs, local-only plugin cache, or
  secret-bearing state.
