# Home and Primary storage recovery

Captured: 2026-07-30 14:11 MSK

## Outcome

| Node | Root before | Root after | Final utilization |
|---|---:|---:|---:|
| Home (`plastilin`) | 15 GiB available | 48 GiB available | 77% |
| Primary (`kolibri`) | 23 GiB available | 25 GiB available | 74% |

Home recovered approximately 33 GiB of filesystem capacity. Primary recovered
approximately 2 GiB. The live containers remained running throughout the
cleanup:

```text
Home:    tplink-policy-dns, awg-proxy-egress
Primary: amnezia-awg2
```

No release, database, Docker volume, credential, current symlink or durable
agent state was removed.

## Home disk topology

Home has one Samsung NVMe device:

```text
nvme0n1                   232.9G disk
├─nvme0n1p1                 1.0G vfat        /boot/efi
├─nvme0n1p2                 2.0G ext4        /boot
└─nvme0n1p3               229.8G LVM2_member ubuntu-vg
  └─ubuntu--vg-ubuntu--lv 210.0G ext4        /
```

The LVM inventory is:

```text
PV /dev/nvme0n1p3: 229.83 GiB total, 19.83 GiB free
VG ubuntu-vg:       229.83 GiB total, 19.83 GiB free
LV ubuntu-lv:       210.00 GiB, mounted at /
```

The reported second part is therefore 19.83 GiB of free extents inside
`ubuntu-vg`, not a second mounted filesystem. It contains no files to clean.
It was deliberately left unallocated. An online root extension is possible,
but was not performed because changing the volume layout is a separate
maintenance decision.

Mounted-filesystem state after the first cache/log pass:

```text
/           207G total, 161G used, 37G available, 82%
/boot       2.0G total, 208M used, 1.6G available, 12%
/boot/efi   1.1G total, 6.2M used, 1.1G available, 1%
```

## Cleanup performed

Home:

- pruned 17.04 GiB of reproducible Docker build cache;
- reduced system journal storage from approximately 4 GiB to 933.5 MiB;
- cleaned apt, npm, pip and uv caches for the applicable operator accounts;
- pruned dangling Docker image layers, reclaiming 925.6 MiB;
- truncated only JSON logs over 50 MiB belonging to 11 stopped containers,
  reclaiming 3.23 GB while preserving the containers and their mounts.
- removed 191 retired agent working copies after proving that every worktree
  had a matching retained artifact result, no file was newer than 2026-07-04,
  and no process had an open path below the worktree root;
- removed reproducible test/evaluation temporary copies, deployment staging
  output and old release-test cache.

Primary:

- reduced journal storage to 482.9 MiB;
- cleaned apt, npm, pip and uv caches;
- pruned dangling Docker image layers, reclaiming 264.4 MiB;
- truncated a 624.7 MB JSON log belonging to the stopped
  `kolibrifin-dev-api` container.

Truncating the stopped-container and journal history is irreversible, but it
does not alter application data or container filesystems. Package and build
caches are reproducible.

The second cleanup pass reclaimed exactly 11,289,092,096 filesystem bytes.
Its manifest is retained on Home at:

```text
/home/ladik/.kolibri-agent/cleanup-manifest-20260730T1424MSK.tsv
```

All 200 agent result directories under `.kolibri-agent/artifacts` remain
available. The retired working copies themselves and reproducible temporary
trees are not recoverable from the filesystem; their result artifacts,
canonical sources and lockfiles are the recovery sources.

## Preserved and deferred

- Home `/opt/kolibri-v3`, `/opt/kolibri-ai`, active release symlinks and release
  history were preserved.
- Primary `/var/lib/kolibri-agent` state/worktrees were preserved.
- Docker volumes and stopped container definitions were preserved.
- Real project candidates such as `dev-c*`, FormulaLM, the network vault,
  canonical source trees and Rust gateway were preserved pending a two-phase
  inventory/quarantine workflow.
- Remaining Docker image reclaim estimates were not treated as safe deletion
  targets because tagged images may be rollback dependencies.
- Docker default log rotation still requires a controlled daemon configuration
  change and maintenance window; no Docker daemon was restarted during this
  recovery.
- The 19.83 GiB Home LVM reserve was not assigned to root.

## Final resource sample

```text
Home memory:     15 GiB total, 11 GiB available, 61 MiB swap used
Primary memory:  11 GiB total, 7.9 GiB available, 511 MiB swap used
Home Docker:     build cache 0 B
Primary Docker:  build cache 0 B
Home root:       207 GiB total, 150 GiB used, 48 GiB available, 77%
```
