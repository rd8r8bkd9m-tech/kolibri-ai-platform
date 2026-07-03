# Next

- Open a clean follow-up PR from `codex/p0-fabric-route-target-lookup-exhaustive-repair-20260703t120400z` against the PR #159 base or rebase onto `main` after PR #159 merges.
- After deployment, rerun live canaries:
  - `POST /v1/fabric/route target_node=9fts required_capability=runner:mimo`
  - `POST /v1/fabric/route target_node=server-kfrm required_capability=runner:codex`
  - `POST /v1/fabric/route target_node=new required_capability=runner:mimo`
- Confirm live `new` returns `status=ok`, `route.target_node=new`, and a bounded fallback list.
