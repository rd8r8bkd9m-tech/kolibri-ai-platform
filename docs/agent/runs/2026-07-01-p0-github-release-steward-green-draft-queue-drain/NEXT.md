# Next

Submit the envelope:

```bash
ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_2026_07_01.json
```

Then monitor:

```bash
ops/kolibri-dispatch status P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_2026_07_01
```

If the task completes cleanly, the next owner decision should be a small merge batch, not a broad "merge everything" action.

Recommended initial release order to validate remotely:

1. PR #88 dispatcher ledger docs.
2. PR #92 fleet inventory docs.
3. PR #96 Agent Host read-only permission pack.
4. PR #97 Control Plane health freshness.
5. PR #85 API-first Fabric.
6. PR #91 MIMO runner contract after Agent Host merge/canary decision.
7. PR #89 Telegram only after single-receiver/cutover safety is clear.
8. PR #83 only if it is not superseded by #96 or needs a final rebase/split.
