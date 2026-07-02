# Next

Recommended follow-up tasks:

1. Wire the owner dashboard/factory status UI to `GET /v1/fleet/guardian` so
   owners see working servers, stale cards, active repairs, and fallback routes.
2. Add queue dispatch integration that can enqueue the generated
   `fleet_online_repair` envelopes with deduplication by `idempotency_key`.
3. Extend live node heartbeats to include explicit Agent Host, GitHub auth,
   runner auth, disk, memory, and MIMO capacity probe fields so `partial` and
   `full` classifications can become stricter.
4. Run a live read-only canary against the deployed Control Plane after this
   code is deployed.

Residual risk:

- The new guardian snapshot uses the evidence currently present in Control
  Plane node cards. It does not perform live network, VPN, service, or credential
  repair by itself.

