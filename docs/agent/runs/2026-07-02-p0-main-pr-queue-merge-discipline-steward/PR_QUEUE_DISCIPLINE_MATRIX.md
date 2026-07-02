# PR Queue Discipline Matrix

Current `main`: `f7ac32c70406432a52752ca45d87e35d9f1facd3`.

Metadata caveat: this server can read Git refs over SSH, but cannot read private GitHub PR metadata or checks through `gh`/REST. Classifications below are based on visible refs, branch diffs against current `main`, checked-in release artifacts, `git diff --check`, and narrow secret-pattern scans. A GitHub-authenticated owner/steward must recheck state, draft flag, CI, reviews, mergeability, and branch freshness immediately before any owner-approved action.

| PR | Head | Scope observed from `HEAD...pr` | Hygiene probe | Queue classification | Next action |
| --- | --- | --- | --- | --- | --- |
| #84 | `de109cac71c2` | 6 docs-only superfactory canvas files | `git diff --check` pass; secret scan no hits | `owner_recheck_low_risk_docs_candidate` | Owner-authenticated recheck, then owner may merge if still open, current, reviewed, and CI/mergeability are green. |
| #99 | `6b72e766e8e3` | 3 dispatcher docs updates | `git diff --check` pass; secret scan no hits | `owner_recheck_low_risk_docs_candidate` | Owner-authenticated recheck; likely safe docs ledger update if not superseded by this artifact. |
| #100 | `f154be86db8f` | 2 dispatcher docs updates plus 1 envelope | `git diff --check` pass; secret scan no hits | `owner_recheck_low_risk_docs_candidate` | Owner-authenticated recheck; low-risk dispatch artifact if still relevant. |
| #101 | `dc121993825c` | 23 docs/run artifact files | `git diff --check` fails on blank line at EOF | `repair_before_merge` | Remove EOF hygiene issues or explicitly accept them, then owner-authenticated metadata/CI recheck. |
| #102 | `6cd2ca5c00d2` | 10 docs/run artifact files | `git diff --check` fails on blank line at EOF | `repair_before_merge` | Remove EOF hygiene issues or explicitly accept them, then owner-authenticated metadata/CI recheck. |
| #104 | `183290355fde` | 12 docs/run artifact files | `git diff --check` fails on blank line at EOF | `repair_before_merge` | Remove EOF hygiene issues or explicitly accept them, then owner-authenticated metadata/CI recheck. |
| #88 | `6e63a15e8a44` | 252 docs-only dispatcher/history files | `git diff --check` fails in `docs/superfactory/Kolibri_All_Prompts.md` | `stale_or_repair_before_merge` | Recheck whether already superseded by later merged dispatcher docs; repair whitespace before any merge. |
| #87 | `f952fd3b7c2b` | 37 docs/business files plus `.agents/roles/...` | `git diff --check` fails on blank line at EOF | `deeper_review` | Business/customer-facing content and non-doc role file require owner review; not a blind docs merge. |
| #65 | `4b506e41f004` | 266 files, broad backend/frontend/infra/factory/code changes | `git diff --check` fails with trailing whitespace | `not_low_risk` | Split or perform full product review; not a queue-drain candidate. |
| #90 | `0fb48df86899` | backend auth code, backend tests, root and canonical artifacts | `git diff --check` fails on blank line at EOF; secret scan no hits | `blocked_runtime_auth_pr` | See `PR90_BLOCKER.md`; do not merge in docs batch. |
| #103 | `26fe979d33f3` | Factory Control code, systemd unit, script, test, docs | `git diff --check` fails on blank line at EOF | `runtime_repair_pr` | Requires focused runtime review and tests; not a docs/low-risk queue candidate. |

Owner-safe merge discipline:

- Do not merge, mark ready, approve, or close any PR from this worker.
- Treat #84, #99, and #100 as candidates only after authenticated GitHub recheck.
- Keep #90 out of any docs/low-risk batch.
- Treat GitHub metadata/CI as blocked on node `kolibri` until an authenticated host provides exact evidence.
