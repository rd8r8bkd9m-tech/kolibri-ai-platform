# UIAP RAG Resource And Security Gates

Task: `P0_UIAP_MINIMAL_RAG_INDEXER_CONTRACT_2026_07_01`

No live `uiap` RAG service may be enabled until every gate below is approved by
Control Plane owners. This docs-only task does not approve the gates.

## Readiness Basis

This contract is based on the completed remote readiness probe
`P0_UIAP_RAG_SKILLS_REGISTRY_READINESS_2026_07_01` as a readiness signal, not
as authorization to expose production traffic.

Observed `uiap` limits from that probe:
- CPU-only node;
- 2 CPU cores;
- about 3.8 GB RAM total;
- about 21 GB free disk;
- suitable for light embeddings/RAG only.

Repository-local alignment:
- `README.md` identifies `uiap` as a RAG Engine host;
- `README.md` identifies ChromaDB and sentence-transformers as the intended RAG
  stack;
- existing backend pipeline code references a `uiap` RAG search dependency, but
  this task intentionally does not change product code.

## Security Gates

| Gate | Required approval evidence |
| --- | --- |
| Internal-only network path | Service reachable only from approved Control Plane mesh identity |
| Strong service identity | Token or mTLS identity issued and rotated by approved secret management |
| GitHub source allowlist | Approved repository, ref, corpus profile and path allowlist |
| Secret scanning | Detector blocks promotion of secret-like content and reports only redacted counts |
| Response redaction | `/health`, `/search` and job events omit secrets, env vars, private paths and stack traces |
| Authorization model | Control Plane caller roles mapped to index, health and search privileges |
| Audit logging | Request IDs, commit SHA, collection name, caller identity and decision logged without sensitive payloads |
| Production exposure review | Explicit approval before opening any port, route, DNS, nginx or public access |

## Resource Gates

| Gate | Required approval evidence |
| --- | --- |
| CPU and memory budget | Maximum concurrent indexing jobs, parser memory limit, embedding batch size |
| ChromaDB storage budget | Max collection size, retention count, cleanup policy for staging collections |
| GitHub fetch budget | Rate limit handling, retry policy, archive size limit |
| Embedding budget | Model selection, device placement, max tokens per job, timeout |
| Query budget | `top_k` cap, query length cap, timeout, rate limit |
| Backpressure | Control Plane queue limit and rejection behavior documented |
| Observability | Health metrics, index duration, chunk count, failure count and staleness metrics |
| Rollback | Alias rollback to previous active collection tested |

## Production Enablement Checklist

Before any live service is enabled:

- Security owners approve internal identity and authorization model.
- Resource owners approve memory, CPU, disk and embedding budgets for `uiap`.
- Control Plane owners approve trigger and completion event schemas.
- Network owners approve internal-only route configuration.
- Operators approve ChromaDB backup, retention and rollback procedures.
- Test owners approve contract tests for `/health`, `/search`, staleness
  detection and failed promotion.
- Product owners approve the initial corpus profile and visibility level.

## Explicitly Blocked Until Approved

- Public internet access to `/search`.
- Indexing from unpinned branches without commit SHA verification.
- Indexing local runtime artifacts or logs.
- Returning raw stack traces or filesystem paths.
- Mutating active ChromaDB collections in place.
- Running automatic scheduled reindex jobs.
- Heavy embedding/model workloads on `uiap`.
- Large batch indexing that exceeds the approved CPU/RAM budget.

## Acceptance Map

| Acceptance criterion | Evidence |
| --- | --- |
| Defines minimal docs/skills indexing flow from GitHub source of truth | `UIAP_RAG_INDEXER_CONTRACT.md` |
| Defines ChromaDB collection strategy | `UIAP_RAG_INDEXER_CONTRACT.md` |
| Defines chunking and metadata fields | `UIAP_RAG_INDEXER_CONTRACT.md` |
| Defines staleness detection | `UIAP_RAG_INDEXER_CONTRACT.md` |
| Defines Control Plane trigger contract | `UIAP_RAG_INDEXER_CONTRACT.md` |
| Defines `/health` and `/search` contract | `UIAP_RAG_INDEXER_CONTRACT.md` |
| Avoids production service exposure | this file and `UIAP_RAG_INDEXER_CONTRACT.md` |
| Lists resource and security gates | this file |
| Does not modify product code | docs-only relay |
| Does not print secrets | placeholders and redaction requirements only |

## Follow-Up Tasks

1. Add contract tests for future `/health` and `/search` handlers before
   implementing a service.
2. Define the approved embedding model and version pin.
3. Define the initial `docs_skills_minimal_v1` corpus profile in Control Plane
   configuration.
4. Select and document the secret-like content detector.
5. Add an operator runbook for ChromaDB backup, staging cleanup and alias
   rollback.
6. Add a non-production smoke fixture only after Control Plane owners approve
   the trigger schema.
