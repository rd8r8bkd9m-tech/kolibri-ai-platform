# Green Draft PR Matrix

Snapshot source: command-node GitHub API, captured 2026-07-01 around 20:10 UTC.

| PR | Title | Head | Draft | Mergeable | CI | Current classification |
| --- | --- | --- | --- | --- | --- | --- |
| #83 | `[p0] Harden Agent Host runner contract` | `3560af06` | yes | yes, clean | success | needs remote steward check for superseded/overlap vs #96 before owner merge |
| #85 | `Finalize API-first full-control Fabric` | `30b7e5dc` | yes | yes, clean | success | merge_ready_after_owner_review per PR85 final release gate |
| #88 | `docs: add factory dispatcher ledger` | `d4559722` | yes | yes, clean | success | likely docs-only owner batch candidate |
| #89 | `P0: Telegram Superfactory bot and Mini App command layer` | `e14aae21` | yes | yes, clean | success | needs runtime receiver/cutover gate before merge |
| #91 | `Fix MIMO runner output and auth classification` | `35054449` | yes | yes, clean | success | likely after Agent Host runner contract merge/canary |
| #92 | `Document fleet role and capability inventory` | `5a33c3fc` | yes | yes, clean | success | likely docs-only owner batch candidate |
| #96 | `[codex] Enforce read-only Agent Host permission packs` | `42625cad` | yes | yes, clean | success | likely early runtime-contract candidate with post-merge canary |
| #97 | `[codex] Classify stale factory node heartbeats` | `f542c5c7` | yes | yes, clean | success | likely early Control Plane candidate with freshness canary |

The remote steward must recheck these values before making a final release recommendation.
