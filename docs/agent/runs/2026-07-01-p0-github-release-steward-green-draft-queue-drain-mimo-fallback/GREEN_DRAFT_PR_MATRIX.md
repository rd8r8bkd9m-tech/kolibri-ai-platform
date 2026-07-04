# Green Draft PR Matrix

Snapshot source: fallback envelope `P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_MIMO_FALLBACK_2026_07_01`, created 2026-07-01T20:23:00Z, with checked-in run artifacts as supporting evidence.

Live recheck note: `gh` is not installed in this MIMO worker, so the envelope snapshot remains the exact GitHub evidence used by this pass.

| PR | Title | Head | Draft | Mergeable | CI | Classification | Steward decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #83 | `[p0] Harden Agent Host runner contract` | `3560af06` | yes | clean | success | Runtime contract hardening with likely overlap/order dependency against #96. Prior PR #83 result shows no implementation blocker, but snapshot head differs from the prior result artifact head, so use envelope head for queue decisions and require final owner/live recheck. | Hold behind #96 comparison; merge only if not superseded and after Agent Host canary plan is accepted. |
| #85 | `Finalize API-first full-control Fabric` | `30b7e5dc` | yes | clean | success | Fabric/API release candidate. PR85 gate artifacts classify it as `merge_ready_after_owner_review`; it remains draft. | Owner-review merge candidate after docs-only and runtime safety gates. |
| #88 | `docs: add factory dispatcher ledger` | `d4559722` | yes | clean | success, success | Docs-only dispatcher ledger candidate. Prior queue drain classified docs-only PR #88 as merge candidate after rebase/recheck. | Safest first batch candidate with #92, subject to final diff/secret scan. |
| #89 | `P0: Telegram Superfactory bot and Mini App command layer` | `e14aae21` | yes | clean | success | High-blast-radius Telegram runtime/UI layer. Supporting deleteWebhook safety gate reports focused tests passed, but prior queue drain classified the broader PR as split/cutover-gated. | Hold until single receiver/cutover gate and owner accepts live Telegram rollout risk. |
| #91 | `Fix MIMO runner output and auth classification` | `35054449` | yes | clean | success | MIMO runner/auth classification candidate. Important for factory reliability, but should follow Agent Host permission/read-only and freshness gates so canaries run on trustworthy runner semantics. | Stage after #96/#97 and after #85 if API surfaces are needed for runner canaries. |
| #92 | `Document fleet role and capability inventory` | `5a33c3fc` | yes | clean | success | Docs/inventory candidate. Prior PR queue drain requested deeper review after #91 owner decision, but fallback snapshot is clean/green and this is documentation-only by title/scope. | Include in first docs batch only after stale-claim review; otherwise hold behind #91 evidence refresh. |
| #96 | `[codex] Enforce read-only Agent Host permission packs` | `42625cad` | yes | clean | success | Runtime safety gate. PR96 release decision says `merge_ready_after_owner_review` with required permission-contract canary. | Early runtime-contract merge candidate after docs batch. |
| #97 | `[codex] Classify stale factory node heartbeats` | `f542c5c7` | yes | clean | success | Control Plane truthfulness/freshness gate. PR97 release decision says `merge_ready_after_owner_review` with required freshness canary. | Early runtime-contract merge candidate after #96 or alongside it if owner accepts paired canary. |

Overall classification:

- First owner-review candidates: #88, #92, #96, #97, #85.
- Hold for sequencing/cutover risk: #91, #89, #83.
- No PR is approved for automatic mutation by this artifact.
