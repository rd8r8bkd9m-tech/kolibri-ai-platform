# Next

Task: `P0_FLEET_ROLE_CAPABILITY_INVENTORY_2026_07_01`

Recommended next tasks:

1. Owner decision on PR #91, then post-merge MIMO runner canary if approved.
2. Repair qjns GitHub/MIMO credentials through an owner-approved credential
   restoration path.
3. Run main runner auth smoke before assigning main push/review work.
4. Repair home/home-live heartbeat freshness before owner-facing Telegram or
   standby-control work.
5. Add Control Plane stale card retention/TTL cleanup for mesh shadow and
   metadata cards.
6. Add queue retention/cancel policy for obsolete probe tasks after owner
   approval.
7. Codify the target pools from this inventory into scheduler policy so agents
   stop selecting stale cards.
