# Release Train Order

Initial command-node hypothesis for remote validation:

1. PR #88: dispatcher ledger docs.
2. PR #92: fleet role/capability inventory docs.
3. PR #96: Agent Host read-only permission packs.
4. PR #97: Control Plane node-health freshness.
5. PR #85: API-first Fabric.
6. PR #91: MIMO runner output/auth contract.
7. PR #89: Telegram Superfactory bot and Mini App.
8. PR #83: Agent Host runner contract hardening, only after checking whether it is superseded or conflicts with #96.

Reasoning:

- Docs-only PRs should land first if they are focused and current.
- Runner permission/freshness contracts should land before broad agent expansion.
- Fabric API should land before any-node/full-control operational rollout.
- MIMO and Telegram depend on the runner/API contracts being trustworthy.

This file is not a merge approval. It is a release-steward hypothesis that must be verified remotely.
