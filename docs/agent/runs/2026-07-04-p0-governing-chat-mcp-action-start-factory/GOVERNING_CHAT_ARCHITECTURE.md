# Governing Chat Architecture

Components:

- Owner chat: sends high-level commands and approvals.
- ChatGPT Action gateway: validates auth, normalizes owner commands, blocks dangerous actions, proxies safe requests.
- Factory Control Plane: owns queue, node registry, leases and artifacts.
- Agent Host: leases tasks, executes bounded runners, reports heartbeat/status.
- Artifact collector: returns collectable run paths and summaries.

Non-goals:

- Gateway does not replace Control Plane.
- Gateway does not mutate services or firewall directly.
- Gateway does not expose tokens or private credentials.
