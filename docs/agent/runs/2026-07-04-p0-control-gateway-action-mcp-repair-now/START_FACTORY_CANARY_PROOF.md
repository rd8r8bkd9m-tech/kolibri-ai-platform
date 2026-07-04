# START_FACTORY_CANARY_PROOF

## Canary 1

`task_id`: `START_FACTORY_CANARY_1783168189032_a6a0c5`

`control_plane_used`: `http://10.99.0.1:9101`

`fallback_nodes`:

- `http://10.99.0.10:9101`: timed out.
- `http://10.99.0.2:9101`: timed out.

`node`: `home`

`runner`: none

`status`: blocked

`blocker`: `unsupported task kind: read_only_factory_canary`

`artifact_collectable`: no

`content_bearing`: no

`evidence`: `/tmp/kolibri-action-gateway-canary-start.json`, `/tmp/kolibri-action-gateway-canary-poll.json`

## Repair applied

Gateway canary envelope was changed to supported kind `owner_remote_task` with runner `codex`, while preserving read-only/no-push/no-secrets constraints.

## Canary 2

`task_id`: `START_FACTORY_CANARY_1783168447197_20d4e7`

`control_plane_used`: `http://10.99.0.1:9101`

`node`: not leased during polling window

`runner`: requested `codex`

`status`: running/queued

`artifact_path`: none yet

`artifact_collectable`: no

`content_bearing`: no

`blocker`: scheduler/agent lease backlog for supported `owner_remote_task` canary. The task stayed `queued` for 12 polls after submit.

`evidence`: `/tmp/kolibri-action-gateway-canary-start-2.json`, `/tmp/kolibri-action-gateway-canary-poll-2.json`

## Conclusion

Start Factory gateway path is proven through task creation and fallback Control Plane selection. It is not counted as completed because no collectable content-bearing artifact was produced.

Next task: `P0_REPAIR_AGENT_LEASE_FOR_START_FACTORY_CANARY_20260704`.
