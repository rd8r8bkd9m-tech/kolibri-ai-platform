# P0 HostVDS Agent 10 Direct Readiness

Task id: `P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02`

Timestamp: `2026-07-02T02:58:38Z`

## Node Identity

- Control Plane lease/worktree path: `/var/lib/kolibri-agent/logical-workers/mesh-agent-10/worktrees/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02-attempt-1/repo`
- Mesh alias evidence: workspace path is under `logical-workers/mesh-agent-10`
- Static hostname: `kolibri`
- Kernel: `Linux kolibri 6.8.0-36-generic #36-Ubuntu SMP PREEMPT_DYNAMIC Mon Jun 10 10:49:14 UTC 2024 x86_64`
- Execution user: `root`

## Git Status

- Repository root: `/var/lib/kolibri-agent/logical-workers/mesh-agent-10/worktrees/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02-attempt-1/repo`
- Branch: `agent/P0_HOSTVDS_AGENT_10_DIRECT_READINESS_CHILD_2026_07_02/read-only`
- HEAD: `f7ac32c`
- Initial working tree status before artifact creation: clean
- Product code modified: no
- Expected final working tree delta: docs-only artifacts under this run directory

## GitHub Auth

- `gh auth status`: blocked because `gh` is not installed (`/bin/bash: gh: command not found`)
- Classification: GitHub CLI unavailable; auth state cannot be validated from this node.
- Secret handling: no token values were queried or printed.

## Disk

`df -hT / /var /tmp .` reported the same backing filesystem for all checked paths:

| Filesystem | Type | Size | Used | Avail | Use% | Mount |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `/dev/vda1` | `ext4` | `99G` | `45G` | `49G` | `48%` | `/` |

Disk headroom is acceptable for normal readiness work.

## Runner Capability And Status

Installed capabilities observed:

- `git`: `2.43.0`
- `docker`: `29.1.3`, linux `x86_64`, `8` CPUs, `12540956672` bytes memory
- `node`: `v18.19.1`
- `npm`: `9.2.0`
- `python3`: `3.12.3`
- `go`: `go1.22.2 linux/amd64`
- `cargo`: `1.96.1`
- `systemd`: `255`
- `pnpm`: missing
- `gh`: missing

Runner status checks:

- No `actions.runner*`, `github*runner*`, or `*runner*` systemd service units were listed.
- No `Runner.Listener`, `Runner.Worker`, `actions.runner`, or `runsvc.sh` process was found.
- No usual runner installation marker (`runsvc.sh`, `Runner.Listener`, `.runner`) was found under `/opt`, `/srv`, or `/var/lib` at max depth 4.

Classification: runner is not registered or not installed/running on this node.

## Blockers

1. GitHub CLI is missing, so GitHub auth cannot be classified as authenticated.
2. GitHub Actions runner is missing or inactive: no service, process, or local installation marker was detected.
3. Hostname is `kolibri` while the Control Plane alias is `mesh-agent-10`; this is acceptable only if the Control Plane intentionally maps the alias to this host.

## Exact Repair Task

On the live `mesh-agent-10` / `hostvds-agent-10` node, install `gh`, authenticate it with the intended non-interactive GitHub credential without printing token values, install/register the GitHub Actions runner for the expected repository or organization, enable and start the runner service, then rerun this readiness probe and confirm:

- `gh auth status` succeeds without token output.
- The runner service is active.
- A `Runner.Listener` process is present.
- The working tree still has no product-code changes.

## Artifacts

- `RESULT.md`: human-readable readiness report.
- `readiness.json`: machine-readable readiness summary.

