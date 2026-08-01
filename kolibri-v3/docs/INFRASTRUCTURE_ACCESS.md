# Home and Primary access runbook

Last route pinning and live verification: 2026-08-01

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

## Direct public ingress invariant

`kolibriai.ru` is a Home-owned public ingress. Its canonical path is:

```text
kolibriai.ru / www.kolibriai.ru
  -> 178.207.11.90:80,443 (Home MikroTik PPPoE)
  -> 192.168.88.210:80,443 (Home / plastilin)
  -> Nginx HTTP/2 TLS edge
  -> 127.0.0.1:3103 (Kolibri V3 portable frontend)
```

Primary must not proxy, terminate TLS for, or host the public
`kolibriai.ru` application. It is permitted only as the declared bounded
administrative VPN fallback when the operator's current network cannot reach
Home directly.

## Provider/runtime capability invariant

The V3 backend owns the capability manifest at `GET /v1/capabilities` (the web
BFF exposes it at `/api/v3/capabilities`). It is the only source of truth for
the browser and native clients: a capability is advertised only when its
server-side service or connected runtime is ready. The manifest currently
covers live web search, weather, attachments, image generation, construction
estimate workspaces/exports and owner-only developer execution.

MiMo normal chat uses the long-lived `MimoClientRuntime` and its native
`web_search` tool. Time-sensitive prompts force a live search; stable prompts
may leave search optional. Owner developer mode uses one loopback MiMo server
for the lifetime of the backend and intentionally does not pass `--pure`, so
MiMo's web tools remain available while the runtime still enforces the stored
per-run access policy.

Production provider vault reads are an explicit transition only:
`KOLIBRI_V3_LOCAL_PROVIDER_VAULT_READ_ENABLED=true` permits decrypting an
already provisioned vault and master key, while key installation and Codex
login remain development-only. A missing or unsafe master key fails closed;
the public application never accepts provider secrets in request bodies.

### RouterOS Wi-Fi/mesh audit (2026-08-01)

The live read-only RouterOS audit checked the LAN bridge, wireless access and
connect lists, WDS/mesh menus, ARP table, mangle rules and active routes. The
result is not a client block:

- no `/interface/wireless/access-list` or `connect-list` entries;
- no `/interface/mesh` or WDS interfaces;
- `wlan1` (2.4 GHz) and `wlan2` (5 GHz) are both enabled, share SSID `server`,
  and are bridged into the LAN with `default-forwarding=true`;
- no firewall address-list or raw drop rule is present;
- the iPhone test in the supplied screenshot is on LTE, so the phone's Wi-Fi
  MAC cannot appear in this router's client table at all.
- Home has no global IPv6 address or IPv6 default route, and `kolibriai.ru`
  has no `AAAA` record; the public service is intentionally IPv4-only.

During the failed LTE attempt, Home packet capture and the public web
destination-NAT counter did not move. That proves the request did not reach
the Home WAN interface; changing a MikroTik port or mesh rule cannot repair a
carrier-side route. Compare the iPhone on Home Wi-Fi with Wi-Fi disabled on
the Android before changing the public edge.

The direct SSH management rule is public TCP `2222` to
`192.168.88.210:22`. Public TCP `22` is not the Home management endpoint.

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
ssh home       -> 178.207.11.90:2222 host=plastilin user=ladik uid=1000
ssh root@home  -> node=home-root host=plastilin user=root uid=0
ssh primary    -> node=primary host=kolibri user=root uid=0
Home mesh      -> host=plastilin user=ladik uid=1000
Primary mesh   -> host=kolibri user=root uid=0

https://kolibriai.ru/app    -> 178.207.11.90 HTTP/2 200
https://kolibriai.ru/livez  -> 178.207.11.90 HTTP/2 200
https://kolibriai.ru/readyz -> 178.207.11.90 HTTP/2 200
```
