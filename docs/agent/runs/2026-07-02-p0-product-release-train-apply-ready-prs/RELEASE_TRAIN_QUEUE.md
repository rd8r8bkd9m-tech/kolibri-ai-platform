# Release Train Queue

Snapshot: 2026-07-02 UTC.

Repository: `rd8r8bkd9m-tech/kolibri-ai-platform`

| PR | Title | Head SHA | Draft | Mergeable | Kolibri CI | Metadata applied | Release decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #113 | P0: repair factory-control runtime import path | `26fe979d33f37f352677cbdffdc8bca84742ab8b` | yes | yes | success, run `28561798865` | comment + `owner-review-requested` | owner review next |
| #112 | P0: repair runner timebox and max-inflight contract | `90c71600b3b99a142823a6aa5d524ff9165a5bfc` | yes | yes | success, run `28561794180` | comment + `owner-review-requested` | owner review next |
| #111 | P0: add queue lease debt audit and requeue policy | `f3a97927308c983e6343a5a2e8d0420031473ab6` | yes | yes | success, run `28561789265` | comment + `owner-review-requested` | owner review next |
| #110 | P0: repair primary node heartbeat read-only path | `9253e6b1255c40bdf99ffb6c930f8b0e445ad383` | yes | yes | success, run `28561783263` | comment + `owner-review-requested` | owner review next |
| #109 | P0: repair factory status proxy 504 canary | `b9f761b6bd6dce8d8375e4a163898283b5bb2fdb` | yes | yes | success, run `28561778515` | comment + `owner-review-requested` | owner review next |
| #108 | P0: repair fleet online freshness accelerator | `8ea1aa4e19c882c3a5893f6fa07c27fc2fdf7b00` | yes | yes | success, run `28561773184` | comment + `owner-review-requested` | owner review next |
| #107 | P0: add release queue accelerator | `762d1b9ea5d88328a693df6d2fa1212a01968fc6` | yes | yes | success, run `28561768604` | comment + `owner-review-requested` | owner review next |
| #106 | P0: repair runner contract steward fallback | `2dd774171f6d7bbd8ba2b36cd76c4fad733c8334` | yes | yes | success, run `28561763736` | comment + `owner-review-requested` | owner review next |
| #105 | P0: make Fabric route selection freshness-aware | `dd86dd8bfe13d4180cb2518573ef0fc5309eafec` | yes | yes | success, run `28561507486` | comment + `owner-review-requested` | owner review next |

Suggested owner review order:

1. #113, because it repairs the active Factory Control runtime import blocker.
2. #109, because it addresses the production factory status 504 canary.
3. #105 and #110, because they affect route and heartbeat freshness.
4. #112 and #106, because they affect runner contract/timebox behavior.
5. #111, because queue lease debt policy depends on stable runner/control semantics.
6. #108 and #107, because they are accelerator/steward changes that should follow the runtime and queue safety fixes.

Merge queue rule:

- Before any owner-approved mark-ready or merge, recheck the exact head SHA, mergeability, and Kolibri CI result. If any head changes, repeat the check request/comment/label pass for that new head.
