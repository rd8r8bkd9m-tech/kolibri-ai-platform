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

The Mac remains optional. Home and the Ubuntu factory must continue when the
owner logs out or the Mac is offline.

## Installed layout

The installer writes only current-user locations:

```text
~/Library/LaunchAgents/ru.kolibriai.mac-codex-provider.plist
~/Library/Application Support/Kolibri/mac-codex-provider/
  config/runner-access.json
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
