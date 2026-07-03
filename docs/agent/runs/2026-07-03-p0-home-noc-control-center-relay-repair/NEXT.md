# Next

Next exact action:

Open a PR from the repair branch and review the NOC Home surface against live `/api/factory/status` data on a Control Plane node.

Recommended checks:

1. Run the frontend with Node `20.19+`.
2. Verify the Home route opens directly to `Control Center`.
3. Confirm the live Control Plane response includes topology and owner attention fields.
4. Confirm search pagination works with live node names, providers, clusters, cells, and agents.
5. Confirm Telegram HA remains read-only and no Bot API mutation is introduced.

Blockers:

- None in source implementation.
- Local worker default Node `v18.19.1` cannot run Vite 8; use Node `20.19+` for frontend build/dev.
