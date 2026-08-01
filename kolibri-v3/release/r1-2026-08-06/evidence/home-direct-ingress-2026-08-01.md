# Home direct ingress recovery — 2026-08-01

## Scope

Restore and prove the owner-approved direct Home path for Kolibri V3 without
using Primary as a public reverse proxy or runtime host.

## Result

- `kolibriai.ru` and `www.kolibriai.ru` resolve to Home public IPv4
  `178.207.11.90` through the authoritative, Google, Cloudflare, and Yandex
  resolvers.
- MikroTik public TCP `80,443` is destination-NATed to Home
  `192.168.88.210`.
- The active Home Nginx edge terminates the existing Let's Encrypt certificate,
  serves TLS 1.2/1.3 with HTTP/2, and proxies only to the canonical V3 frontend
  on `127.0.0.1:3103`.
- MikroTik public TCP `2222` is destination-NATed to Home
  `192.168.88.210:22`. The stale public TCP `22` mapping was replaced and TCP
  `22` is no longer exposed.
- Primary was used only as an external diagnostic vantage point and bounded
  administrative VPN jump while the direct rule was repaired. It is not in the
  application request path.

## Recovery evidence

The live RouterOS snapshot found one exact SSH rule before the change:

```text
comment=Kolibri-SSH
chain=dstnat action=dst-nat protocol=tcp
dst-address=178.207.11.90 dst-port=22
to-addresses=192.168.88.210 to-ports=22
```

Before changing it, RouterOS created both a binary backup and a sanitized
export:

```text
kolibri-before-ssh2222-20260801T160305Z.backup
kolibri-before-ssh2222-20260801T160305Z.rsc
```

The bounded rollback state is root-only on Home:

```text
/var/backups/kolibri-v3/routeros/ssh2222-last-change.json
```

The previous active Nginx site is stored outside `sites-enabled` so it cannot
create a duplicate virtual host:

```text
/var/backups/kolibri-v3/nginx/kolibri.backup-before-direct-home-http2-20260801T1555Z
```

## Verification

```text
direct ssh home:
  host=plastilin user=ladik endpoint=178.207.11.90:2222

external TCP:
  178.207.11.90:2222 open
  178.207.11.90:22 closed_or_filtered

HTTPS from operator network:
  /       HTTP/2 307 -> /app
  /app    HTTP/2 200
  /livez  HTTP/2 200
  /readyz HTTP/2 200

HTTPS from independent external vantage point:
  remote=178.207.11.90 HTTP/2 200
  connect=0.124s TLS=0.187s TTFB=0.247s total=0.292s

Nginx:
  nginx -t successful
  systemctl is-active nginx -> active
```

## iPhone/LTE and RouterOS mesh check

The additional live read-only audit checked RouterOS wireless/mesh state and
client filtering. There are no wireless access-list or connect-list rules, no
mesh/WDS interfaces, no firewall address-list entries and no raw drop rules.
Both enabled radios (`wlan1` 2.4 GHz and `wlan2` 5 GHz) are bridged to the
same LAN and allow client forwarding. The screenshot shows LTE rather than
Home Wi-Fi, so an iPhone MAC address is not a RouterOS client in that test.
The router has only IPv6 link-local addresses (no global IPv6 route), and the
domain has no `AAAA` record, so a carrier IPv6/DNS64 path is an external
compatibility variable rather than a MikroTik client block.

While the iPhone was failing over LTE, Home `tcpdump` saw no TCP/443 packet and
the MikroTik `kolibriai web 80-443 to Home` counter had zero delta. A different
phone reaching the site therefore does not implicate an iPhone block; it
indicates a difference in carrier/Wi-Fi path. The next controlled comparison
is iPhone on Home Wi-Fi, then Android on LTE with Wi-Fi disabled.

## Recovery re-check

After the operator reported that the iPhone route recovered, the public path
was rechecked from the operator network, Primary and Home itself:

```text
DNS (1.1.1.1 / 8.8.8.8 / 77.88.8.8): 178.207.11.90
operator: /app 200, /livez 200, /readyz 200 (HTTP/2)
Primary:  /app 200, /livez 200, /readyz 200 (HTTP/2)
Home:    /app 200, /livez 200, /readyz 200 (HTTP/2)
MikroTik web dst-nat packets: 225879 -> 225930 during the re-check
```

The direct Home route is healthy again. No firewall, mesh or NAT rule was
changed during this verification.

## Declarative prevention

The canonical portable release installer now renders HTTP/2, TLS 1.2/1.3,
session reuse, disabled TLS session tickets, and a persistent upstream
connection header. The corresponding release-observability contract test is
green. A later V3 deployment therefore preserves the corrected edge instead
of reverting it to the previous HTTP/1.1-only template.
