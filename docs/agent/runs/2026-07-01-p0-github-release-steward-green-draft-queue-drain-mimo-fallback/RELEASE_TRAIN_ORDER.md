# Release Train Order

Recommended safe order:

1. PR #88: dispatcher ledger docs.
2. PR #92: fleet role/capability inventory docs, after stale-claim review.
3. PR #96: Agent Host read-only permission packs.
4. PR #97: Control Plane node-health freshness.
5. PR #85: API-first Fabric.
6. PR #91: MIMO runner output/auth classification.
7. PR #89: Telegram Superfactory bot and Mini App.
8. PR #83: Agent Host runner contract hardening, only after explicit #96 overlap/supersession review.

Reasoning:

- Documentation-only PRs should land first because they have the lowest runtime blast radius and unblock shared release context.
- Agent Host permission enforcement and Control Plane freshness should land before broader automation expansion, because they improve the safety and truthfulness of subsequent canaries.
- Fabric/API work should land before MIMO and Telegram flows that rely on stable control surfaces.
- MIMO auth/output classification should precede high-risk Telegram cutover work so auth failures remain classified without leaking secrets.
- PR #83 must not be merged blindly after #96 because both touch Agent Host runner safety semantics; owner should decide whether #83 remains additive, needs rebase, or is superseded.

Batch proposal:

- Batch 1: #88 and #92, if final docs diff and secret scan are clean.
- Batch 2: #96 and #97, if owner accepts runtime canary obligations.
- Batch 3: #85.
- Batch 4: #91.
- Batch 5: #89, only after receiver/cutover safety gates.
- Batch 6: #83, only if still needed after #96.

This order is a steward recommendation, not a merge approval.
