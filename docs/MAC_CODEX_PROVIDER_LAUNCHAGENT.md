# Mac Codex provider LaunchAgent

Status: reviewed implementation contract; not installation or production
evidence.

`ru.kolibriai.mac-codex-provider` turns the proven one-off Mac Agent Host into
a current-user LaunchAgent. It remains an execution provider for the Home
factory; clients still use the OpenAI-compatible Kolibri API and never address
the Mac or Codex directly.

## Authority and identity

- The plist contains no Control Plane URL or physical server name.
- Agent Host resolves Home from the existing replicated mesh manifest named by
  `KOLIBRI_MESH_MEMBERSHIP_MANIFEST`.
- The installer references that live manifest in place; it does not take a
  static snapshot or create a second membership authority.
- The LaunchAgent runs as the logged-in macOS owner with the owner's actual
  `HOME`. Codex therefore uses the already-authorized current-user session.
- No Codex authentication file, API key, access token, cookie, or credential
  is copied into the runtime, plist, logs, manifest, or artifacts.
- The dedicated runner policy enables local browser/device Codex and disables
  Mimo. A binary or legacy capability cannot override `disabled`.
- Read-only provider tasks start Codex with its native `--search` capability.
  Internet access is therefore provider-managed and auditable while the local
  filesystem sandbox remains read-only.
- Normal Agent Hosts leave periodic Codex probing disabled. This managed Mac
  LaunchAgent opts in with `KOLIBRI_CODEX_READINESS_REFRESH_SECONDS=240`.
  Refresh runs only while no task is active, uses the current-user session in
  place, and immediately withdraws `runner:codex` when the bounded probe fails.

The Mac remains optional. Home and the Ubuntu factory must continue when the
owner logs out or the Mac is offline.

## Installed layout

The installer writes only current-user locations:

```text
~/Library/LaunchAgents/ru.kolibriai.mac-codex-provider.plist
~/Library/Application Support/Kolibri/mac-codex-provider/
  config/runner-access.json
  config/external-provider-actor.credential  # current-user 0600; raw value exists only here
  runtime/releases/<source-sha256>/
  logs/agent-host.log
  logs/launchd-bootstrap.log
~/.kolibri-agent/worktrees/
~/.kolibri-agent/artifacts/
```

Runtime releases are content-addressed and marked as managed. The uninstall
tool refuses to recursively remove an unmarked directory. Configuration,
tasks, artifacts, logs, the mesh manifest, and the Codex session are preserved
by default.

## Safe review and installation

The external audit actor uses a scoped, node-bound HMAC credential. Home stores
only its SHA-256 verifier and non-secret `credential_id`/`epoch` metadata in a
root-owned `0600` file. The raw bearer is transmitted only on authenticated
requests over the trusted transport; it is never printed, returned by an API,
or persisted at Home.

Initial enablement is an intentionally drained, controlled sequence:

1. drain the existing audit actor on the current Home Control Plane and prove
   Redis PONG with zero active, expired, and stuck leases;
2. deploy the new Home Control Plane with auth unconfigured (the actor fails closed);
3. validate, then apply the credential installer; it preserves the drain, writes
   the Mac raw record and Home verifier, and restarts only Home Control Plane;
4. install/load the signing-capable Mac runtime;
5. verify the exact server marker and fresh readiness, then explicitly undrain;
6. run one fenced provider canary and accept success only from its terminal
   task result with matching node, agent, runner, attempt, and evidence.

Resolve Home dynamically and perform the pre-deploy gate:

```bash
HOME_CONTROL_URL="$(python3 ops/control_plane_endpoint.py --print-url \
  --manifest "$KOLIBRI_MESH_MEMBERSHIP_MANIFEST")"
curl -fsS -H 'Content-Type: application/json' -d '{"drain":true}' \
  "$HOME_CONTROL_URL/v1/nodes/mac-codex-provider/drain"
curl -fsS "$HOME_CONTROL_URL/v1/tasks/queue/diagnostics" | jq -e \
  '.redis == "PONG" and .lease_index_total == 0 and .expired_leases == 0 and .stuck_heartbeat_tasks == 0'
```

```bash
python3 scripts/macos/install-external-provider-actor-credential.py \
  --mesh-manifest "$KOLIBRI_MESH_MEMBERSHIP_MANIFEST"

python3 scripts/macos/install-external-provider-actor-credential.py \
  --mesh-manifest "$KOLIBRI_MESH_MEMBERSHIP_MANIFEST" --apply
```

The first command is dry-run only. Initial apply reports
`credential_installed_actor_drained`; that is staged state, not readiness.
The LaunchAgent installer below requires this credential file to exist.

Rotation accepts only a safe existing Mac record and exactly the next epoch.
It drains first, requires Redis PONG with zero active/expired/stuck leases,
reconciles the exact old Home metadata, switches both sides, reloads the one
LaunchAgent label, and verifies the new server marker. It never undrains:

```bash
python3 scripts/macos/install-external-provider-actor-credential.py \
  --mesh-manifest "$KOLIBRI_MESH_MEMBERSHIP_MANIFEST" \
  --rotate --epoch NEXT_EPOCH --credential-id NEXT_CREDENTIAL_ID \
  --reload-launch-agent --apply
```

An operator must verify the exact marker and fresh readiness before explicit
undrain:

```bash
curl -fsS "$HOME_CONTROL_URL/v1/nodes/mac-codex-provider?scope=all" | jq -e \
  '.external_provider_auth.actor_scope == "external_provider_actor" and .external_provider_auth.bound_node_id == .node_id and .freshness == "fresh" and .runner_readiness.codex.status == "available" and .runner_readiness.codex.login_status == "authenticated" and .runner_readiness.codex.probe.status == "passed"'
curl -fsS -H 'Content-Type: application/json' -d '{"drain":false}' \
  "$HOME_CONTROL_URL/v1/nodes/mac-codex-provider/drain"
```

`auth_configured`, a heartbeat, or an advertised capability alone is never
success evidence. The canary must use the exact read-only Home provider
envelope and pass lease fencing/result-binding checks. Any failed or uncertain
rotation remains drained; after Home has switched epochs, recovery continues
with the new credential and never silently downgrades. No overlapping old/new
credential acceptance window exists.

Use the actual replicated manifest path already maintained on the Mac:

```bash
python3 scripts/macos/install-mac-codex-provider.py \
  --mesh-manifest "$KOLIBRI_MESH_MEMBERSHIP_MANIFEST"
```

The default is validation-only. It checks the manifest, dynamic Home
resolution, non-secret runner policy, current-user `codex login status`,
runtime sources, and rendered plist without changing the machine.

Install without starting:

```bash
python3 scripts/macos/install-mac-codex-provider.py \
  --mesh-manifest "$KOLIBRI_MESH_MEMBERSHIP_MANIFEST" \
  --apply
```

Before loading, stop the temporary manually-started provider so the same node
identity cannot lease twice. The installer intentionally does not search for
or kill unrelated processes. Then load the reviewed LaunchAgent:

```bash
python3 scripts/macos/install-mac-codex-provider.py \
  --mesh-manifest "$KOLIBRI_MESH_MEMBERSHIP_MANIFEST" \
  --apply --load
```

`--load` performs a label-scoped `bootout`, `bootstrap`, and `kickstart`. If
bootstrap fails, the prior managed plist is restored. No `sudo`, system daemon,
VPN route, WireGuard key, firewall, DNS, or server state is changed.

## Health evidence

Static validation derives Home from the installed manifest and never reads
provider credentials:

```bash
python3 scripts/macos/health-mac-codex-provider.py --validate-only
```

The live gate additionally requires:

- the exact LaunchAgent label loaded in the current user's GUI domain;
- the dynamically resolved Home API reachable;
- the `mac-codex-provider` card present;
- Codex available on pinned `gpt-5.5` with a passed readiness probe;
- the readiness attestation no older than 300 seconds (240-second interval
  plus a 60-second health grace);
- `runner:codex` advertised;
- Mimo disabled and not advertised;
- private log modes.

```bash
python3 scripts/macos/health-mac-codex-provider.py
```

The health JSON contains booleans and non-secret paths only. It does not return
raw launchd output, provider output, prompts, environment contents, or auth
status text.

## Logging and restart policy

Launchd uses `RunAtLoad`, a failed-exit `KeepAlive`, a restart throttle, and a
private `0077` umask. The launcher merges child stdout/stderr, redacts complete
lines containing credential markers, truncates oversized lines, rotates the
sanitized log at a bounded size, and writes files with mode `0600`.

## Uninstall

Review only:

```bash
python3 scripts/macos/uninstall-mac-codex-provider.py
```

Unload and remove only the managed plist:

```bash
python3 scripts/macos/uninstall-mac-codex-provider.py --apply
```

Optionally remove content-addressed managed runtime copies:

```bash
python3 scripts/macos/uninstall-mac-codex-provider.py --apply --remove-runtime
```

There is deliberately no purge-auth or purge-data option.
