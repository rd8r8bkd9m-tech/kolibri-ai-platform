# Actions

- Cloned the configured repository into the empty task worktree.
- Created this run ledger before implementation changes.
- Fetched PR #159 as `origin/pr/159` and based this follow-up branch on it to preserve the health vocabulary repair.
- Added `registered_node(node_id)` for exact Redis node-record lookup.
- Updated `/v1/fleet/route`, `/v1/fabric/route`, and `/v1/fabric/relay` to pass the exact target record into route resolution when `target_node` is present.
- Updated `fabric_route()` so explicit target resolution prefers the authoritative target record and is not constrained by the registered/fallback candidate sample.
- Added bounded fallback sampling through `FABRIC_ROUTE_FALLBACK_LIMIT`, defaulting to 26.
- Added a regression for `target_node="new"` with `runner:mimo` where `new` is absent from the 40-node sampled fallback list but present in the authoritative target record.
