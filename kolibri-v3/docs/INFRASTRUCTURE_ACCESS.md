# Home and Primary access runbook

Last route pinning: 2026-07-31

This is the canonical operator entry point for the two physical V3 runtime
nodes. An agent must read this file before declaring either node unavailable.
Do not infer connectivity from historical SSH config backups or old task
reports.

## Confirmed identities

| Logical node | OS hostname | Preferred local command | Effective identity |
|---|---|---|---|
| Home | `plastilin` | `ssh home` | `ladik@178.207.11.90:2222` |
| Home VPN fallback | `plastilin` | `ssh home-vpn` | `ladik@10.99.0.1:22` through Primary |
| Primary | `kolibri` | `ssh primary` | `root@78.17.4.108:22` |

`ssh kolibri-primary-codex` is an equivalent Primary alias.

The current local SSH include is
`~/.ssh/config.d/kolibri-current.conf`. Resolve an alias before use:

```bash
ssh -G home |
  awk '$1 == "hostname" || $1 == "user" || $1 == "port" ||
       $1 == "identityfile" || $1 == "proxyjump" { print }'

ssh -G primary |
  awk '$1 == "hostname" || $1 == "user" || $1 == "port" ||
       $1 == "identityfile" || $1 == "proxyjump" { print }'
```

The direct Home alias uses the operator key at
`~/Desktop/Kolibri SSH Key/id_ed25519`. Primary uses
`~/.ssh/id_ed25519`. Do not search for another Home key before resolving these
two declared aliases.

## Confirmed mesh/VPN fallbacks

The declared mesh fallback is:

```bash
ssh home-vpn
ssh -i ~/.ssh/id_ed25519 root@10.99.0.10
```

They resolve to the same physical hosts:

- `10.99.0.1` → Home / `plastilin`;
- `10.99.0.10` → Primary / `kolibri`.

`ssh home` is always attempted first when the Mac is outside the Home LAN.
Only a bounded WAN timeout permits `ssh home-vpn`; agents must not enumerate
old addresses, keys, or legacy aliases.

## Required connection sequence

Use non-interactive, bounded probes:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 home \
  'hostname; id -un; uptime'

ssh -o BatchMode=yes -o ConnectTimeout=10 primary \
  'hostname; id -un; uptime'
```

If an alias probe fails:

1. inspect it with `ssh -G`;
2. run the single declared fallback `ssh home-vpn`;
3. distinguish timeout, host-key failure and authentication failure;
4. record the exact failed route and timestamp.

Only after both the preferred and mesh paths fail may an agent report the
physical node as unreachable.

## Authority and safety

- `ssh home` is the normal operator/read-only identity.
- Privileged Home work requires an explicitly authorized `ssh root@home`
  session; do not assume `sudo` works for `ladik`.
- Primary is intentionally root-bound through its canonical alias.
- Before deleting data, prove the exact path is cache, temporary output,
  inactive release material or another reproducible artifact.
- Never remove the active release, database files, Docker volumes, credentials,
  provider state or current symlink as part of general cleanup.
- Capture disk/memory/service state before and after every mutation.

## Home storage layout

Live inventory on 2026-07-30 confirmed that Home has one physical
232.9 GiB NVMe device, not two independently mounted data disks:

```text
/dev/nvme0n1p1   1.0 GiB   vfat   /boot/efi
/dev/nvme0n1p2   2.0 GiB   ext4   /boot
/dev/nvme0n1p3 229.8 GiB   LVM2   ubuntu-vg
```

The volume group contains a 210 GiB root logical volume and 19.83 GiB of
unallocated LVM extents. That free extent pool is the apparent second part of
the disk: it is valid capacity, but it is not a filesystem and therefore does
not appear in `df`. Do not format it or create a competing mount casually.
Extending the root logical volume is a separate storage mutation and requires
an explicit maintenance decision.

The cleanup proof and current capacity are recorded in
`release/r1-2026-08-06/evidence/home-primary-storage-recovery-2026-07-30.md`.

## Last live proof

```text
ssh home       -> node=home host=plastilin user=ladik uid=1000
ssh root@home  -> node=home-root host=plastilin user=root uid=0
ssh primary    -> node=primary host=kolibri user=root uid=0
Home mesh      -> host=plastilin user=ladik uid=1000
Primary mesh   -> host=kolibri user=root uid=0
```
