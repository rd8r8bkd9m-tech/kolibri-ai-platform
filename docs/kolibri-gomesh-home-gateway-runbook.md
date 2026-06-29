# Kolibri GoMesh Home Gateway Runbook

## Current decision

MikroTik hAP ac2 must stay the LAN/DHCP/PPPoE router. It cannot safely run the
Kolibri GoMesh dataplane in RouterOS containers on this hardware: starting
containerized TUN or raw AF_PACKET dataplane caused RouterOS kernel reboots.

The working gateway split is:

- MikroTik: keeps PPPoE, Wi-Fi, DHCP, and normal LAN default routing.
- Home Linux host `plastilin`: runs the Kolibri GoMesh client dataplane.
- Main exit node `104.253.43.117`: runs a dedicated packet TUN exit and remains
  the fallback Home endpoint.
- Direct exit node `78.17.4.108`: runs a dedicated Kolibri packet TUN exit and
  is the selected Home endpoint after the LG TV canary.

This keeps the home internet usable while selected traffic is moved through
GoMesh incrementally.

Do not confuse two different direct modes:

- MacBook direct mode: the MacBook runs a Kolibri client directly to
  `78.17.4.108:29445`, so traffic does not pass through Home.
- Whole-LAN direct mode: MikroTik itself must run a tunnel to `78.17.4.108`.
  RouterOS cannot speak custom Kolibri GoMesh v0 directly, so this mode needs a
  MikroTik-native tunnel such as WireGuard/IPsec, or a RouterOS-native Kolibri
  client that does not exist in the current repo.

Do not set `78.17.4.108` as a plain MikroTik default gateway. It is not a local
L2 next-hop on `192.168.88.0/24`; without a tunnel, a default route to that
address would not be a valid LAN gateway.

## Deployed services

### Main exit

Service:

```sh
systemctl status kolibri-tunneld-home-exit.service
```

Listener:

```text
0.0.0.0:29445/tcp
0.0.0.0:29445/udp
```

Tunnel interface:

```text
kgmhomeexit0 = 10.254.10.1/24
```

Runtime setup:

- enables IPv4 forwarding;
- routes `192.168.88.0/24` back through `kgmhomeexit0`;
- masquerades `192.168.88.0/24` and `10.254.10.0/24` out `eth0`;
- allows related return traffic from `eth0` to `kgmhomeexit0`.

Setup scripts:

```text
/usr/local/sbin/kolibri-home-exit-setup
/usr/local/sbin/kolibri-home-exit-teardown
```

### Direct 78 exit

Service on `78.17.4.108`:

```sh
systemctl status kolibri-tunneld-home-exit-78.service
```

Listener:

```text
0.0.0.0:29445/tcp
0.0.0.0:29445/udp
```

Tunnel interface:

```text
kgmhomeexit78 = 10.254.10.1/24
```

Runtime setup:

- enables IPv4 forwarding;
- routes `192.168.88.0/24` back through `kgmhomeexit78`;
- masquerades `192.168.88.0/24` and `10.254.10.0/24` out `eth0`;
- allows related return traffic from `eth0` to `kgmhomeexit78`.

Setup scripts:

```text
/usr/local/sbin/kolibri-home-exit-78-setup
/usr/local/sbin/kolibri-home-exit-78-teardown
```

Current direct-78 state on 2026-06-29:

```text
kolibri-tunneld-home-exit-78.service = active
78.17.4.108:29445/tcp = open from Home
kgmhomeexit78 = 10.254.10.1/24
```

Live state on 2026-06-29 after the LG TV canary:

```text
PSK synced with Home client.
Home client endpoint = 78.17.4.108:29445.
Fallback endpoint = 104.253.43.117:29445.
Active exit countries in manifest at that checkpoint = FI, LV.
Home curl through kgmhome0 external IP = 78.17.4.108.
YouTube HTTPS through kgmhome0 returns HTTP/2 200.
```

### New standby exit

Service on `109.248.161.39` (`new`, mesh `10.99.0.6`):

```sh
systemctl status kolibri-tunneld-home-exit-new.service
```

Listener:

```text
0.0.0.0:29446/tcp
0.0.0.0:29446/udp
```

Tunnel interface:

```text
kgmhomenew = 10.254.10.1/24
```

Runtime setup:

- enables IPv4 forwarding;
- routes `192.168.88.0/24` back through `kgmhomenew`;
- masquerades `192.168.88.0/24` and `10.254.10.0/24` out `eth0`;
- allows related return traffic from `eth0` to `kgmhomenew`.

Setup artifacts:

```text
/usr/local/sbin/kolibri-home-exit-new-setup
/usr/local/sbin/kolibri-home-exit-new-teardown
/opt/kolibri/repo/infra/systemd/kolibri-tunneld-home-exit-new.service
/opt/kolibri/repo/scripts/kolibri_home_exit_new_setup.sh
/opt/kolibri/repo/scripts/kolibri_home_exit_new_teardown.sh
```

Current state on 2026-06-29:

```text
kolibri-tunneld-home-exit-new.service = active
109.248.161.39:29446/tcp = reachable from primary
kgmhomenew = 10.254.10.1/24
PSK matches the current Home/78 PSK without printing key material.
GeoIP conflict: ipwho.is reports FI/Helsinki, ipapi.co reports LV/Riga.
Role in manifest: standby-verified, not part of automatic primary/fallback.
```

Controlled Home test on 2026-06-29:

```text
Temporary endpoint: 109.248.161.39:29446
Health through kgmhome0: ok
External IP through kgmhome0: 109.248.161.39
YouTube through kgmhome0: HTTP 200 in about 750 ms
Xiaomi MiMo through kgmhome0: HTTP 200 in about 290 ms
Home restored afterwards to primary endpoint 78.17.4.108:29445.
kolibri-gomesh-home-healthcheck.timer restored to active.
```

### FR qjns slow standby exit

Service on `217.60.63.97` (`qjns`, mesh `10.99.0.4`):

```sh
systemctl status kolibri-tunneld-home-exit-qjns.service
```

Listener:

```text
0.0.0.0:29447/tcp
0.0.0.0:29447/udp
```

Tunnel interface:

```text
kgmhomeqjns = 10.254.10.1/24
```

Runtime setup:

- enables IPv4 forwarding;
- routes `192.168.88.0/24` back through `kgmhomeqjns`;
- masquerades `192.168.88.0/24` and `10.254.10.0/24` out `eth0`;
- allows related return traffic from `eth0` to `kgmhomeqjns`.

Setup artifacts:

```text
/usr/local/sbin/kolibri-home-exit-qjns-setup
/usr/local/sbin/kolibri-home-exit-qjns-teardown
/opt/kolibri/repo/infra/systemd/kolibri-tunneld-home-exit-qjns.service
/opt/kolibri/repo/scripts/kolibri_home_exit_qjns_setup.sh
/opt/kolibri/repo/scripts/kolibri_home_exit_qjns_teardown.sh
```

Bootstrap notes on 2026-06-29:

```text
Initial install failed because /dev/vda1 was full.
Safe cleanup removed 2468 stale /tmp/.fefd*.so temporary files with no open
/proc maps references, vacuumed journal to 64M, and cleaned apt cache/lists.
Free disk after cleanup: about 6.0G.
Free disk after service bootstrap: about 5.9G.
```

Current state on 2026-06-29:

```text
kolibri-tunneld-home-exit-qjns.service = active
217.60.63.97:29447/tcp = reachable from primary and Home
kgmhomeqjns = 10.254.10.1/24
GeoIP: ipwho.is reports FR/Paris; ipapi.co was rate-limited during this check.
Role in manifest: slow-standby-verified, not part of automatic failover.
```

Controlled Home test on 2026-06-29:

```text
Temporary endpoint: 217.60.63.97:29447
Health through kgmhome0: ok
External IP through kgmhome0: 217.60.63.97
YouTube through kgmhome0: HTTP 200 in about 12.0s
Xiaomi MiMo through kgmhome0: HTTP 200 in about 4.0s
Home restored afterwards to primary endpoint 78.17.4.108:29445.
kolibri-gomesh-home-healthcheck.timer restored to active.
```

Keep this exit as a country-specific standby until the selector can score
targets per service. It is valid for FR reachability, but it is too slow for
blind automatic failover.

Fast profile update on 2026-06-29:

```text
Home client carrier = auto.
Preferred carrier = UDP/QUIC packet pipe.
Fallback carrier = TCP packet pipe.
Carrier dial timeout = 2s, so blocked UDP falls back quickly.
TUN MTU = 1280.
TUN-to-pipe queue = 4096 packets.
```

Manifest and status artifacts:

```text
repo manifest: /opt/kolibri/repo/ops/kolibri-gomesh-exits.json
repo checker:  /opt/kolibri/repo/scripts/kolibri_gomesh_status.py
repo scorer:   /opt/kolibri/repo/scripts/kolibri_gomesh_exit_score.py
repo selector: /opt/kolibri/repo/scripts/kolibri_gomesh_home_selector.py
repo snapshot: /opt/kolibri/repo/scripts/kolibri_gomesh_selector_snapshot.py
repo report:   /opt/kolibri/repo/scripts/kolibri_gomesh_selector_report.py
repo audit:    /opt/kolibri/repo/scripts/kolibri_gomesh_readiness_audit.py
repo audit snapshot: /opt/kolibri/repo/scripts/kolibri_gomesh_readiness_snapshot.py
repo apply preflight: /opt/kolibri/repo/scripts/kolibri_gomesh_apply_preflight.py
repo client verify: /opt/kolibri/repo/scripts/kolibri_gomesh_client_verify.py
repo objective audit: /opt/kolibri/repo/scripts/kolibri_gomesh_objective_audit.py
repo objective snapshot: /opt/kolibri/repo/scripts/kolibri_gomesh_objective_snapshot.py
repo operator report: /opt/kolibri/repo/scripts/kolibri_gomesh_operator_report.py
repo RouterOS live audit: /opt/kolibri/repo/scripts/kolibri_gomesh_routeros_live_audit.py
repo RouterOS live dump kit: /opt/kolibri/repo/scripts/kolibri_gomesh_routeros_live_dump_kit.py
repo RouterOS API bootstrap: /opt/kolibri/repo/scripts/kolibri_gomesh_routeros_api_bootstrap.py
repo RouterOS API one-shot server: /opt/kolibri/repo/scripts/kolibri_gomesh_routeros_api_oneshot_server.py
repo RouterOS API bundle verify: /opt/kolibri/repo/scripts/kolibri_gomesh_routeros_api_bundle_verify.py
repo RouterOS verification package: /opt/kolibri/repo/scripts/kolibri_gomesh_routeros_verification_package.py
repo supervised rollout packet: /opt/kolibri/repo/scripts/kolibri_gomesh_supervised_rollout_packet.py
Home manifest: /etc/kolibri-gomesh/exits.json
Home checker:  /usr/local/sbin/kolibri-gomesh-status
Home site probe: /usr/local/sbin/kolibri-gomesh-probe-site
Home scorer:    /usr/local/sbin/kolibri-gomesh-exit-score
Home selector:  /usr/local/sbin/kolibri-gomesh-home-selector
Home snapshot:  /usr/local/sbin/kolibri-gomesh-selector-snapshot
Home report:    /usr/local/sbin/kolibri-gomesh-selector-report
Home audit:     /usr/local/sbin/kolibri-gomesh-readiness-audit
Home audit snapshot: /usr/local/sbin/kolibri-gomesh-readiness-snapshot
Home apply preflight: /usr/local/sbin/kolibri-gomesh-apply-preflight
Home client verify: /usr/local/sbin/kolibri-gomesh-client-verify
Home objective audit: /usr/local/sbin/kolibri-gomesh-objective-audit
Home objective snapshot: /usr/local/sbin/kolibri-gomesh-objective-snapshot
Home objective history: /var/log/kolibri-gomesh/objective-audit-history.jsonl
Home operator report: /usr/local/sbin/kolibri-gomesh-operator-report
Home RouterOS live audit: /usr/local/sbin/kolibri-gomesh-routeros-live-audit
Home RouterOS live dump kit: /usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit
Home RouterOS API bootstrap: /usr/local/sbin/kolibri-gomesh-routeros-api-bootstrap
Home RouterOS API one-shot server: /usr/local/sbin/kolibri-gomesh-routeros-api-oneshot-server
Home RouterOS API bundle verify: /usr/local/sbin/kolibri-gomesh-routeros-api-bundle-verify
```

Use the objective audit when deciding whether the full goal can be called done:

```sh
/usr/local/sbin/kolibri-gomesh-objective-audit --pretty
```

It is read-only. It should report `objective_complete=false` until a supervised
client expansion or whole-LAN window has been applied on MikroTik and verified
from real clients. A healthy pre-rollout state should still report
`ready_for_supervised_next_group=true`.

The objective snapshot timer keeps this evidence warm:

```sh
systemctl status kolibri-gomesh-objective-snapshot.timer
tail -n 3 /var/log/kolibri-gomesh/objective-audit-history.jsonl | jq .
```

The timer is also read-only. It runs every 30 minutes and keeps the last 336
samples, about one week of history.

Use the operator report for the current handoff state and the next safe action:

```sh
/usr/local/sbin/kolibri-gomesh-operator-report --pretty
```

It is read-only and does not print RouterOS passwords, PSKs, or private keys.

When the same report is run from a non-Home node, such as the direct exit
server `78.17.4.108`, it must not treat missing Home-only services as a live
failure. The report auto-detects the local role and marks Home/MikroTik runtime
checks as `unverified` until the report is run on Home or a RouterOS dump is
provided:

```sh
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_operator_report.py \
  --manifest /opt/kolibri/repo/ops/kolibri-gomesh-exits.json \
  --pretty
```

Historical non-Home report behavior before Home collector/API evidence was
available on 2026-06-29 from `78.17.4.108`:

```text
node_context.role = non-home
documented_architecture = passed
controlled_country_exits = passed
active exit endpoints healthy = 4
countries = FI, FR, LV
mikrotik_central_gateway_profile = passed from staged profile evidence
home_dataplane_gateway = unverified from this node
mikrotik_live_state = unverified from this node
service_access_policy = unverified from this node
canary_clients_routed = unverified from this node
completion_percent_estimate = 35
live_changes_made_by_report = false
```

Interpretation: the direct exit and documentation gates are healthy, but the
objective cannot be called complete until Home and MikroTik live state are
verified from Home or from a current WinBox dump.

Current non-Home report behavior after importing the read-only RouterOS API
user and wiring the latest Home collector/RouterOS verification package into
the report:

```text
node_context.role = non-home
completion_percent_estimate = 88
home_dataplane_gateway = passed from Home collector summary
mikrotik_live_state = passed from read-only RouterOS API summary
service_access_policy = passed from Home readiness summary
canary_clients_routed = passed from Home canary route summary
rollout_gate = staged
whole_lan_or_all_home_clients = incomplete
manual_live_dump_required = false
live_changes_made_by_report = false
```

Interpretation: the live RouterOS gate is closed. The normal next action is not
a WinBox dump; it is choosing the next named client group or approving a
supervised whole-LAN window, then applying and verifying the generated plan with
the rollout lock present only during that window.

The report also contains a `verification_handoff` object. Treat it as the
canonical next-step packet when working from a non-Home node:

```text
verification_handoff.home.run_read_only_commands
verification_handoff.routeros_api_path.commands_on_home
verification_handoff.routeros_manual_dump_path.winbox_read_only_commands
verification_handoff.routeros_manual_dump_path.commands_on_home_after_winbox
verification_handoff.rollout_guardrails
```

All commands in that object are read-only until the operator explicitly imports
the generated RouterOS API user script or applies a separate rollout plan.
`verification_handoff.rollout_guardrails` must stay true before any client group
or whole-LAN change:

```text
do not create /etc/kolibri-gomesh/allow-lan-rollout until Home runtime and
RouterOS live audit are green
do not create /etc/kolibri-gomesh/allow-selector-apply during client routing
rollout
keep MikroTik PPPoE/default internet path unchanged until one supervised client
group is verified
```

If the Home `kolibri-mesh-agent` is reachable, the same evidence can be
collected without SSH:

```sh
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_home_mesh_exec_collect.py --pretty
```

The collector reads `KOLIBRI_MESH_EXEC_TOKEN` from
`/etc/kolibri/mesh-agent.env`, calls Home `http://10.99.0.1:8081/api/exec`,
and runs only a fixed allowlist of read-only commands:

```text
/usr/local/sbin/kolibri-gomesh-status --runtime --pretty
/usr/local/sbin/kolibri-gomesh-readiness-audit --pretty
/usr/local/sbin/kolibri-gomesh-objective-audit --pretty
/usr/local/sbin/kolibri-gomesh-routeros-live-audit --pretty
/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit status --pretty
```

It writes full command envelopes to
`/opt/kolibri/repo/.run/gomesh-home-live-*/` and prints a compact summary. It
does not create rollout locks, does not call selector apply, and does not
change MikroTik or Home routing.

`kolibri-gomesh-operator-report` is installed on Home as the local handoff
report, but it can take longer than the mesh-agent exec timeout because it
chains several audits. Keep it out of the default mesh-exec collection. Use
`--include-operator` only when a longer mesh-agent timeout is available or when
testing that optional path:

```sh
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_home_mesh_exec_collect.py --include-operator --pretty
```

Verified Home mesh-exec collection on 2026-06-29:

```text
Home node = plastilin via 10.99.0.1:8081/api/exec
kolibri-gomesh-status --runtime = ok
Home client service = active
Home health timer = active
Home external IP through kgmhome0 = 78.17.4.108
YouTube through kgmhome0 = 200
Xiaomi MiMo through kgmhome0 = 200
Yandex Music through kgmhome0 = 200
LG TV canary route = kgmhome0 table 1099
GalaxyGalina canary route = kgmhome0 table 1099
readiness current_canary_state_ok = true
readiness automatic_apply_ready = true
objective ready_for_supervised_next_group = true
RouterOS management ports visible from Home = 22, 80, 443, 8291, 8728
RouterOS API login = true through kolibri-ro
RouterOS live config verified = true
```

Interpretation: Home dataplane, service policy, and current canaries are proven.
RouterOS live state is now proven through the read-only `kolibri-ro` API user;
manual WinBox dump remains a fallback, not the normal path.

After wiring the collector summary into the objective audit, the primary node
can use the fresh Home evidence without re-running Home-only checks locally:

```sh
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_objective_audit.py \
  --manifest /opt/kolibri/repo/ops/kolibri-gomesh-exits.json \
  --pretty
```

Verified primary-node audit on 2026-06-29:

```text
completion_percent_estimate = 88
documented_architecture = passed
controlled_country_exits = passed
home_dataplane_gateway = passed
mikrotik_central_gateway_profile = passed
service_access_policy = passed
canary_clients_routed = passed
rollout_gate = staged
mikrotik_live_state = passed
whole_lan_or_all_home_clients = incomplete
remaining_requirements no longer include RouterOS dump/API bootstrap when
mikrotik_live_state = passed
```

Do not interpret `rollout_gate=staged` as permission to enable LAN rollout.
It means the current canaries and Home dataplane are ready for the next
supervised step. The remaining required proof is client expansion or whole-LAN
verification from real clients; do not mark the objective complete while
`whole_lan_or_all_home_clients=incomplete`.

Use client verify before and after adding a specific client to a supervised
rollout:

```sh
/usr/local/sbin/kolibri-gomesh-client-verify --client lg-webos-tv,192.168.88.15,LGwebOSTV --pretty
/usr/local/sbin/kolibri-gomesh-client-verify --client tv2,192.168.88.25,BedroomTV --pretty
```

For a current active canary, `ok_currently_routed=true` means the manifest and
Home dataplane agree. For a new custom client,
`ok_for_supervised_apply=true` means Home is ready, but the client still needs
the MikroTik rule and DNS redirect from the generated rollout plan before it
actually uses the mesh.

Use RouterOS live audit to close the gap between a staged profile and actual
router state:

```sh
/usr/local/sbin/kolibri-gomesh-routeros-live-audit --pretty
```

If a read-only RouterOS API user is available, the same audit can read live
state automatically. Keep the password outside the repo and manifest:

```sh
/usr/local/sbin/kolibri-gomesh-routeros-api-bootstrap --pretty
/usr/local/sbin/kolibri-gomesh-routeros-api-bundle-verify --pretty
# paste /etc/kolibri-gomesh/routeros-api/create-kolibri-routeros-api-user.rsc
# into WinBox Terminal; the file is 0600 because it contains the generated password
/usr/local/sbin/kolibri-gomesh-routeros-live-audit --pretty
```

After bootstrap, the live audit automatically looks for
`/etc/kolibri-gomesh/routeros-api.password` and uses API user `kolibri-ro`.
The bundle verifier confirms file modes, expected `read,api` policy, and that
the password file matches the RouterOS create script without printing the
password.

Verified live-audit gate on 2026-06-29 after adding the bundle verifier:

```text
RouterOS management ports open = 22, 80, 443, 8291, 8728
ssh_batch_ok = false
api_login_ok = true
api_user = kolibri-ro
api_bootstrap_bundle_ready = true
bundle password_printed = false
bundle password_matches_create_command = true
bundle file modes = 0600
manual_live_dump_required = false
live_config_verified = true
```

Interpretation: RouterOS accepts the read-only API audit user. Keep using
`kolibri-ro` for verification; do not use the admin password for routine
read-only checks.

Repeat the full RouterOS verification package from the primary server:

```sh
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_routeros_verification_package.py --pretty
```

Latest verified package on 2026-06-29T08:33:38Z:

```text
evidence_dir = /opt/kolibri/repo/.run/gomesh-routeros-verification-package-20260629T083252Z
routeros_live.ok = true
api_login_ok = true
live_config_verified = true
current_endpoint = 78.17.4.108:29445
current_health = ok
oneshot_create_dry.serving_started = false
oneshot create URL and fetch command are redacted from summary by default
dump commands file exists = true
stable-canaries plan: apply_steps=1, verify_steps=5, rollback_steps=1
LAN plan: apply_steps=1, verify_steps=5, rollback_steps=2
rollout lock present = false
selector history samples = 61
selector would_switch_count = 0
whole_lan_allowed = false
```

Build a read-only supervised rollout packet before any live client expansion:

```sh
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_supervised_rollout_packet.py --scope stable-canaries --pretty
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_supervised_rollout_packet.py --scope lan --pretty
```

The packet is an operator checklist, not an executor. It talks to Home through
the mesh-agent, verifies RouterOS live state, checks `kolibriai.ru`, includes
the generated apply/rollback commands, and writes both JSON and Markdown:

```text
/opt/kolibri/repo/.run/gomesh-supervised-rollout-packet-*/packet.json
/opt/kolibri/repo/.run/gomesh-supervised-rollout-packet-*/packet.md
/opt/kolibri/repo/.run/gomesh-supervised-rollout-packet-latest.json
/opt/kolibri/repo/.run/gomesh-supervised-rollout-packet-latest.md
```

Latest packets generated on 2026-06-29T08:55Z:

```text
stable-canaries evidence_dir = /opt/kolibri/repo/.run/gomesh-supervised-rollout-packet-20260629T085535Z
LAN evidence_dir = /opt/kolibri/repo/.run/gomesh-supervised-rollout-packet-20260629T085534Z
live_changes_made_by_packet = false
ready_for_supervised_window_packet = true
RouterOS live config verified = true
selector history = 65 samples over 310.87 minutes, 0 would_switch decisions
current endpoint = 78.17.4.108:29445
current health = ok
domain check = ok
```

The post-apply RouterOS live audit is scope-aware:

```sh
/usr/local/sbin/kolibri-gomesh-routeros-live-audit --expected-scope stable-canaries --pretty
/usr/local/sbin/kolibri-gomesh-routeros-live-audit --expected-scope lan --pretty
```

Current pre-rollout guard result: `stable-canaries` passes, while
`--expected-scope lan --fail-if-unverified` exits non-zero because LAN routing
and LAN DNS redirects are still disabled. That is the expected safe state until
the supervised LAN window is actually opened and applied.

After any live apply, run the post-rollout verifier from the primary server:

```sh
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_post_rollout_verify.py --scope stable-canaries --pretty
python3 /opt/kolibri/repo/scripts/kolibri_gomesh_post_rollout_verify.py --scope lan --pretty
```

Current pre-rollout verifier behavior:

```text
stable-canaries evidence_dir = /opt/kolibri/repo/.run/gomesh-post-rollout-verify-20260629T085425Z
stable-canaries verdict = PASS
LAN evidence_dir = /opt/kolibri/repo/.run/gomesh-post-rollout-verify-20260629T085426Z
LAN verdict = ROLLBACK_REQUIRED
LAN blocker = RouterOS live state does not match expected scope
LAN scope mismatch = LAN route and LAN DNS redirects are observed disabled
```

This is intentional before LAN apply. During the supervised LAN window the LAN
verifier must return `PASS`; if it returns `ROLLBACK_REQUIRED`, run the packet's
rollback commands before continuing.

If copying the private `.rsc` file to the WinBox workstation is inconvenient,
start a short-lived one-shot server on Home and paste the generated RouterOS
`/tool/fetch ...; /import ...` command into WinBox Terminal immediately:

```sh
/usr/local/sbin/kolibri-gomesh-routeros-api-oneshot-server --mode create --ttl-seconds 300 --pretty
```

This helper serves only the generated RouterOS command bundle under a random
bearer path and exits after one download or TTL expiry. Do not leave it running
outside the supervised WinBox step. It does not change RouterOS by itself; the
only live change happens when the operator imports the fetched script in WinBox.

Verified one-shot helper dry-run on 2026-06-29:

```text
Home path = /usr/local/sbin/kolibri-gomesh-routeros-api-oneshot-server
mode = create
bind = 192.168.88.210
port = 18081
ttl_seconds = 300
serving_started = false
live_changes_made_by_helper = false
```

When the audit user is no longer needed, paste:

```text
/etc/kolibri-gomesh/routeros-api/remove-kolibri-routeros-api-user.rsc
```

If SSH key auth is not available, run this in WinBox/Terminal and save the text
as a dump, then audit the dump on Home:

```sh
/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit prepare --pretty
/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit status --pretty
/usr/local/sbin/kolibri-gomesh-routeros-live-dump-kit verify --dump /etc/kolibri-gomesh/routeros-live-dump/latest-routeros-live-dump.txt --pretty
```

The prepare command writes the read-only command list to
`/etc/kolibri-gomesh/routeros-live-dump/winbox-dump-commands.txt`. Paste those
commands into WinBox Terminal, save the combined output into
`/etc/kolibri-gomesh/routeros-live-dump/latest-routeros-live-dump.txt`, and run
the verify command. This path avoids creating a RouterOS API user.

```routeros
/system/script/run kolibri-home-gw-status
/routing/table/print detail where name="kolibri-home-gw"
/ip/route/print detail where comment~"Kolibri Home gateway" or routing-table="kolibri-home-gw"
/routing/rule/print detail where comment~"Kolibri Home gateway"
/ip/firewall/nat/print detail where comment~"Kolibri DNS redirect"
/system/script/print detail where name~"kolibri-home-gw"
/system/scheduler/print detail where name~"kolibri-home-gw"
/ip/dns/print
```

```sh
/usr/local/sbin/kolibri-gomesh-routeros-live-audit --dump /path/to/routeros-status.txt --pretty
```

The manifest contains no PSK material. It records active packet exits:

```text
fi-78-direct: 78.17.4.108:29445, country FI, role primary
lv-104-main:  104.253.43.117:29445, country LV, role fallback
fi-lv-109-new-standby: 109.248.161.39:29446, role standby-verified
fr-217-qjns-slow-standby: 217.60.63.97:29447, country FR, role slow-standby-verified
```

It also records candidate regions from the server inventory that still require a
packet-exit install before they can be used for country routing: LV/Riga,
FR/Paris, US/Kansas City, and HK/Hong Kong.

Candidate readiness check on 2026-06-29:

```text
new / 10.99.0.6: promoted to active standby after controlled Home test.
9fts / 10.99.0.5: binary, PSK, and TUN are ready; not promoted because GeoIP is FI.
uiap / 10.99.0.3: mesh exec works, but kolibri-tunneld binary and matching PSK are missing.
qjns / 10.99.0.4: promoted to FR slow standby after cleanup, bootstrap, and controlled Home test.
FR/US/HK public SSH candidates timed out from primary during this check.
```

### Yandex-style resilience model

Yandex Music working consistently is a useful control sample. Public Yandex
Cloud CDN material points to an edge-first architecture: distributed points of
presence, origin groups with backup origins, origin shielding, large object
slicing, stale/cached responses, compression, and peering-close delivery.

Do not treat this as a single trick to copy into MikroTik rules. Translate it
into GoMesh behavior:

- score exits per target service, not only by `generate_204`;
- keep fast nearby exits as defaults for media traffic;
- keep slow country exits as service-specific standby until measured useful;
- prefer UDP/QUIC when available, but keep bounded TCP fallback;
- record recent failures and avoid flapping between endpoints;
- probe DNS, TCP connect, HTTPS status, total time, carrier fallback, and
  external IP before moving clients.

Current target checks:

```text
youtube: https://www.youtube.com
  service_class = blocked-media-canary
  route_preference = mesh_when_client_or_direct_fails
xiaomi-mimo-platform: https://platform.xiaomimimo.com/
  service_class = mimo-platform-canary
  route_preference = mesh_when_direct_fails
yandex-music-control: https://music.yandex.ru/
  service_class = local-cdn-control
  route_preference = direct_when_available
```

Observed Home probe on 2026-06-29:

```text
Yandex Music: direct 200 in ~0.58s, mesh 200 in ~0.67s, recommendation keep_direct_for_control_target
Xiaomi MiMo: direct TLS timeout in ~8.00s, mesh 200 in ~0.30s, recommendation use_mesh_for_this_target
```

Yandex Music is therefore a control target, not a blanket reason to route all
clients through a remote exit. If Yandex works directly while a target such as
MiMo fails directly and works through `kgmhome0`, the correct fix is
service/client policy routing, not whole-LAN tunnel rollout.

Promotion rule:

```text
Do not promote active_slow_standby exits into automatic failover until
service-level scoring proves that the standby is better for the requested
target than the primary and fallback.
```

Read-only scoring:

```sh
/usr/local/sbin/kolibri-gomesh-exit-score --pretty
```

The scorer does not switch the Home endpoint and does not read PSK material. It
uses packet endpoint TCP checks, manifest role/status guardrails, current Home
endpoint detection, recorded controlled Home tests, and live target checks for
the current endpoint through `kgmhome0`. Use `--skip-live-current` for a
manifest-only dry run. Automatic failover recommendations exclude exits marked
`not_in_automatic_failover` and exits with `slow` in the role/status. Use
`--include-standby` only for planning manual or service-specific tests.

Service route policy audit:

```sh
/usr/local/sbin/kolibri-gomesh-service-route-audit --pretty
```

This audit runs the direct-vs-mesh probes for all manifest target checks and
verifies the declared `route_preference` for each target. It is stricter than a
plain `200 OK` check:

```text
yandex-music-control must remain a direct control target when direct works.
xiaomi-mimo-platform must be mesh-ready when direct TLS fails.
youtube must stay mesh-ready for affected clients even if direct works from Home.
```

Verified service route policy on 2026-06-29:

```text
service_route_policy_ok = true
yandex-music-control: keep_direct, direct 200, mesh 200
youtube: route_affected_clients_via_mesh, direct 200, mesh 200
xiaomi-mimo-platform: route_via_mesh, direct 000 timeout, mesh 200
```

Dry-run endpoint selection:

```sh
/usr/local/sbin/kolibri-gomesh-home-selector --pretty
```

The selector consumes scorer output and the current Home failover status. By
default it does not change the endpoint. It keeps the current endpoint when
health is `ok`, even if another eligible endpoint is slightly ahead, unless
`--allow-healthy-switch` is given and the score margin passes the threshold.
Unknown Home status produces `status_unknown_no_switch`.

Apply mode exists but must stay manual:

```sh
/usr/local/sbin/kolibri-gomesh-home-selector --apply --pretty
```

Apply mode is intentionally limited to manifest `primary` and `fallback` roles
through `/usr/local/sbin/kolibri-gomesh-home-failover`. It cannot switch to
`standby-verified` or `slow-standby-verified` exits. Do not wire apply mode into
the timer until repeated dry-runs prove stable behavior.

Apply mode is also locked by file. This file must be absent by default:

```text
/etc/kolibri-gomesh/allow-selector-apply
```

If the file is absent, `/usr/local/sbin/kolibri-gomesh-home-selector --apply`
must refuse to call the failover helper and return a non-zero result. Create
this file only for a supervised manual switch window, then remove it again.

Verified apply lock on 2026-06-29:

```text
lock file = absent
command = /usr/local/sbin/kolibri-gomesh-home-selector --apply --pretty
selector exit code = 1
apply_result.ok = false
applied = false
reason = apply lock file is absent; refusing endpoint switch
endpoint before = 78.17.4.108:29445
endpoint after = 78.17.4.108:29445
health after = ok
```

Apply preflight:

```sh
/usr/local/sbin/kolibri-gomesh-apply-preflight --pretty
```

This command is read-only. It runs readiness audit and selector dry-run, checks
the apply lock file, and returns `apply_allowed=false` with blockers until every
condition is satisfied. Do not create `/etc/kolibri-gomesh/allow-selector-apply`
unless this preflight first passes during a supervised switch window.

Verified apply preflight on 2026-06-29:

```text
apply_allowed = false
current_canary_state_ok = true
automatic_apply_ready = true
whole_lan_rollout_ready = false
lock file present = false
current endpoint = 78.17.4.108:29445
current health = ok
selector decision = keep_current, would_switch=false
blockers = apply lock file is absent
```

Rollout preflight:

```sh
/usr/local/sbin/kolibri-gomesh-rollout-preflight --pretty
```

This command is read-only. It is separate from selector apply mode and is used
before expanding MikroTik policy routing from the current LG/Galaxy canaries to
another client group or to the whole LAN. It checks:

```text
current canary state is ok
service route policy is ok
selector dry-run history is stable
current endpoint is the primary 78.17.4.108:29445
at least two canaries are active
selector apply lock is absent
rollout lock /etc/kolibri-gomesh/allow-lan-rollout is present
RouterOS staged profile matches the manifest
```

Default behavior must remain blocked:

```text
observationally_ready=true after selector history reaches the sample/window gate
next_group_allowed=false until the rollout lock exists
whole_lan_allowed=false; whole-LAN needs a separate manual MikroTik change window
```

Do not create `/etc/kolibri-gomesh/allow-lan-rollout` during observation. Create
it only inside a supervised rollout window, run this preflight again, and remove
the lock immediately after the routing change or rollback.

Use the TTL-managed rollout window helper instead of creating the lock file by
hand:

```sh
/usr/local/sbin/kolibri-gomesh-rollout-window status --pretty
/usr/local/sbin/kolibri-gomesh-rollout-window open --scope next-group --ttl-minutes 15 --reason "supervised next group" --pretty
/usr/local/sbin/kolibri-gomesh-rollout-window close --reason "apply verified or rolled back" --pretty
```

The helper manages only `/etc/kolibri-gomesh/allow-lan-rollout`; it does not
change MikroTik routes. By default it refuses to open the window unless rollout
preflight is observationally ready and RouterOS live config has been verified.
The cleanup timer removes expired managed locks:

```sh
systemctl status kolibri-gomesh-rollout-window-cleanup.timer
/usr/local/sbin/kolibri-gomesh-rollout-window cleanup --pretty
```

Verified rollout window guard on 2026-06-29:

```text
cleanup timer = active
open --scope next-group --ttl-minutes 15 refused without changing routes
open blocker = RouterOS live config is not verified
real rollout lock present after refusal = false
preflight during refusal = observationally_ready=true, current endpoint 78.17.4.108:29445, health ok
```

Current state after enabling the read-only RouterOS API audit user:

```text
RouterOS live config verified = true
rollout lock present = false
selector apply lock present = false
ready_for_supervised_next_group = true
ready_for_whole_lan = false
```

Opening a rollout window is now an operator decision for a named next client
group or whole-LAN change window; do not open it automatically from monitoring.

Verified rollout preflight on 2026-06-29:

```text
current endpoint = 78.17.4.108:29445
current health = ok
active canaries = 2
service_route_policy_ok = true
routeros_profile_audit_ok = true
selector history = 31 samples over 140.37 minutes, 0 would_switch decisions
observationally_ready = true
observation blockers = none
rollout lock present = false
selector apply lock present = false
next_group_allowed = false
whole_lan_allowed = false
```

This means the current LG/Galaxy canary observation is stable enough to plan a
supervised next-client-group rollout. It does not permit automatic rollout:
`next_group_allowed` remains false until `/etc/kolibri-gomesh/allow-lan-rollout`
exists inside a supervised window, and `whole_lan_allowed` remains false by
design.

Rollout change plan:

```sh
/usr/local/sbin/kolibri-gomesh-rollout-plan --scope stable-canaries --pretty
/usr/local/sbin/kolibri-gomesh-rollout-plan --scope custom --client tv2,192.168.88.25,BedroomTV --pretty
/usr/local/sbin/kolibri-gomesh-rollout-plan --scope lan --pretty
```

This command is read-only. It generates operator commands, verification steps,
and rollback steps. It does not run RouterOS commands and does not create
`/etc/kolibri-gomesh/allow-lan-rollout`.

Use `--scope custom` for the next supervised client group only after choosing
explicit client IPs from MikroTik DHCP leases. Do not use `--scope
disabled-canaries` to re-enable MacBook unless the user explicitly asks; MacBook
was returned to normal routing by request. `--scope lan` is a whole-LAN plan, not
permission to run it.

Verified rollout plan generation on Home on 2026-06-29:

```text
stable-canaries plan = ok
custom example plan = ok
current endpoint = 78.17.4.108:29445
current health = ok
rollout lock present = false
selector apply lock present = false
```

Dry-run history:

```sh
/usr/local/sbin/kolibri-gomesh-selector-snapshot
systemctl status kolibri-gomesh-selector-snapshot.timer
tail -n 5 /var/log/kolibri-gomesh/selector-history.jsonl
```

The snapshot script appends selector output to:

```text
/var/log/kolibri-gomesh/selector-history.jsonl
```

It stores only selector/scorer decisions, endpoint IDs, target status, scores,
and timing. It does not read PSK material and does not call `--apply`. The timer
runs every five minutes and keeps the latest 576 JSONL records by default.

History readiness report:

```sh
/usr/local/sbin/kolibri-gomesh-selector-report --pretty
```

Default readiness gate:

```text
min samples = 12
min window = 60 minutes
max would_switch decisions = 0
expected endpoint = 78.17.4.108:29445
latest health must be ok
latest decision must be keep_current
```

This report is intentionally conservative. `ready_for_apply_consideration=false`
means apply-mode must stay disabled; it does not mean the current tunnel is
broken.

Readiness audit:

```sh
/usr/local/sbin/kolibri-gomesh-readiness-audit --pretty
```

The audit aggregates runtime status, target checks, service route policy,
canary route checks, selector history readiness, failover status, apply lock
state, and the selector snapshot timer. It is read-only and must be used before
any change from canary routing to a larger rollout.

Interpretation:

```text
current_canary_state_ok=true means the current LG TV/Galaxy canary path is healthy.
automatic_apply_ready=true means selector history and current canary state are ready for a supervised endpoint-switch window.
whole_lan_rollout_ready=false means the MikroTik whole-LAN rule must remain disabled.
apply_lock.present=false means selector apply-mode is still physically locked.
rollout_lock.present=false means no MikroTik expansion window is currently open.
safety_warnings=[] means no supervised-switch lock file was accidentally left behind.
service_route_policy.ok=true means direct-vs-mesh decisions match the manifest.
```

Verified readiness audit on 2026-06-29:

```text
current_canary_state_ok = true
current endpoint = 78.17.4.108:29445
current health = ok
active exits = 4
countries = FI, FR, LV
target checks = ok: YouTube 200, Xiaomi MiMo 200, Yandex Music 200
canary routes = ok: LGwebOSTV and GalaxyGalina through kgmhome0/table 1099
selector snapshot timer = active
selector history = 65 samples over 310.87 minutes, 0 would_switch decisions
service route policy = ok
service route actions = route_affected_clients_via_mesh: 1, route_via_mesh: 1, keep_direct: 1
apply lock present = false
rollout lock present = false
safety warnings = none
automatic_apply_ready = true
automatic blockers = none
whole_lan_rollout_ready = false
whole-LAN blockers = whole-LAN disabled by design, MacBook canary disabled by user request, rollout lock absent, separate supervised MikroTik window required
```

Readiness audit history:

```sh
/usr/local/sbin/kolibri-gomesh-readiness-snapshot
systemctl status kolibri-gomesh-readiness-snapshot.timer
tail -n 5 /var/log/kolibri-gomesh/readiness-audit-history.jsonl
```

The readiness snapshot runs the full read-only audit every fifteen minutes and
stores the latest 672 JSONL records. This history is heavier than selector
history because it runs runtime target checks, so it should remain less
frequent. It still does not call apply mode and does not change routing.

Disable readiness audit history:

```sh
systemctl disable --now kolibri-gomesh-readiness-snapshot.timer
```

Verified readiness audit history on 2026-06-29:

```text
kolibri-gomesh-readiness-snapshot.timer = active
history path = /var/log/kolibri-gomesh/readiness-audit-history.jsonl
records observed = 4
latest current_canary_state_ok = true
latest endpoint = 78.17.4.108:29445
latest health = ok
latest service_route_policy_ok = true
latest service_route_actions = route_affected_clients_via_mesh: 1, route_via_mesh: 1, keep_direct: 1
latest automatic_apply_ready = false
latest whole_lan_rollout_ready = false
next scheduled run = 2026-06-29T04:25:44Z
```

Verified report on 2026-06-29:

```text
sample_count = 3
window_minutes = 5.02
selector_ok_count = 3
would_switch_count = 0
current endpoint = 78.17.4.108:29445 for all samples
current health = ok for all samples
decision action = keep_current for all samples
scorer recommended exit = fi-78-direct for all samples
ready_for_apply_consideration = false
blockers = only 3 samples; need at least 12, history window 5.02 minutes; need at least 60
```

Disable selector observation:

```sh
systemctl disable --now kolibri-gomesh-selector-snapshot.timer
```

Verified selector observation on 2026-06-29:

```text
kolibri-gomesh-selector-snapshot.timer = active
history path = /var/log/kolibri-gomesh/selector-history.jsonl
latest decision = keep_current
latest decision_would_switch = false
scorer recommended exit = fi-78-direct
endpoint before snapshot = 78.17.4.108:29445
endpoint after snapshot = 78.17.4.108:29445
health after snapshot = ok
```

### Home gateway

Service:

```sh
systemctl status kolibri-gomesh-home-client.service
```

Current fast profile:

```text
ExecStart=/opt/kolibri-vpn/bin/kolibri-tunnelctl tun-client \
  --server 78.17.4.108:29445 \
  --carrier auto \
  --tun-name kgmhome0 \
  --tun-cidr 10.254.10.2/24 \
  --tun-mtu 1280 \
  --timeout 2s \
  --reconnect-delay 2s \
  --queue-size 4096
```

Reason:

```text
The previous Home service used `--carrier tcp --timeout 10s`. That is robust,
but it creates a slower TCP-over-TCP path for forwarded LAN traffic. The current
profile behaves like an obfuscated Amnezia-style tunnel at the carrier boundary,
but prefers UDP/QUIC for lower latency and keeps TCP as bounded fallback.
```

Tunnel interface:

```text
kgmhome0 = 10.254.10.2/24
```

Runtime setup:

- enables IPv4 forwarding;
- disables reverse path filtering for the forwarding path;
- creates policy table `1099`;
- sends only packets received from LAN interface `enp3s0` with source
  `192.168.88.0/24` through `kgmhome0`;
- allows forwarding from `enp3s0` to `kgmhome0` and related return traffic
  from `kgmhome0` to `enp3s0`;
- clamps TCP MSS from LAN clients toward `kgmhome0` so clients do not assume
  the normal Ethernet MTU while the GoMesh TUN path is `1280`;
- leaves Home's own default route unchanged.

Policy rule:

```text
priority 1099: from 192.168.88.0/24 iif enp3s0 lookup 1099
```

Table `1099`:

```text
default dev kgmhome0
78.17.4.108/32 via 192.168.88.1 dev enp3s0
192.168.88.0/24 dev enp3s0
```

Setup scripts:

```text
/usr/local/sbin/kolibri-home-gateway-setup
/usr/local/sbin/kolibri-home-gateway-teardown
```

Healthcheck:

```text
/usr/local/sbin/kolibri-gomesh-home-failover
/usr/local/sbin/kolibri-gomesh-home-healthcheck
kolibri-gomesh-home-healthcheck.timer
```

Repo restore artifacts:

```text
/opt/kolibri/repo/scripts/kolibri_gomesh_home_failover.sh
/opt/kolibri/repo/scripts/kolibri_gomesh_home_healthcheck.sh
/opt/kolibri/repo/infra/systemd/kolibri-gomesh-home-healthcheck.service
/opt/kolibri/repo/infra/systemd/kolibri-gomesh-home-healthcheck.timer
```

The timer runs every minute. It verifies that
`kolibri-gomesh-home-client.service` is active and that HTTPS egress through
`kgmhome0` can reach `https://www.gstatic.com/generate_204`. On failure it
restarts the Home client service and switches between these endpoints:

```text
primary:  78.17.4.108:29445
fallback: 104.253.43.117:29445
```

Manual endpoint control on Home:

```sh
/usr/local/sbin/kolibri-gomesh-home-failover status
/usr/local/sbin/kolibri-gomesh-home-failover set-primary
/usr/local/sbin/kolibri-gomesh-home-failover set-fallback
/usr/local/sbin/kolibri-gomesh-home-failover check
```

The check intentionally does not rely on ICMP to `10.254.10.1`: the 78 exit
passes HTTPS traffic but does not answer that TUN ICMP health probe.

Verified failover test on 2026-06-29 after the fast `--carrier auto` profile:

```text
before:       endpoint=78.17.4.108:29445, health=ok, external IP=78.17.4.108
set-fallback: endpoint=104.253.43.117:29445, health=ok, external IP=104.253.43.117
fallback:     YouTube HTTP 200 in about 1496 ms, Xiaomi MiMo HTTP 200 in about 447 ms
set-primary:  endpoint=78.17.4.108:29445, health=ok, external IP=78.17.4.108
primary:      YouTube HTTP 200 in about 483 ms, Xiaomi MiMo HTTP 200 in about 301 ms
```

### MikroTik prepared profile

MikroTik has prepared per-client canary profiles:

```text
routing table: kolibri-home-gw
default route: 0.0.0.0/0 via 192.168.88.210 in table kolibri-home-gw
MacBook rule: 192.168.88.12/32 -> kolibri-home-gw, disabled
LG TV rule: 192.168.88.15/32 -> kolibri-home-gw, enabled
GalaxyGalina rule: 192.168.88.17/32 -> kolibri-home-gw, enabled
LAN rollout rule: 192.168.88.0/24 -> kolibri-home-gw, disabled
```

Live state on 2026-06-29 after the MacBook rollback: the MacBook rule is
disabled and the MacBook is back on the normal MikroTik main route. The LG TV
and GalaxyGalina canary rules are still enabled. The whole-LAN rule is still
disabled. Disable an affected canary immediately with the matching rollback
script if the user reports a client-visible regression.

Current DHCP identity:

```text
MacBook current = 192.168.88.12, MAC 3E:33:CA:A9:59:66
Home gateway    = 192.168.88.210, MAC 04:92:26:D5:85:DD
LGwebOSTV       = 192.168.88.15
GalaxyGalina    = 192.168.88.17
```

Current canary state on 2026-06-29:

```text
MacBook rule: 192.168.88.12/32 -> kolibri-home-gw, disabled
MacBook DNS redirect: TCP/UDP 53 from 192.168.88.12 -> MikroTik DNS, disabled
LGwebOSTV rule: 192.168.88.15/32 -> kolibri-home-gw, enabled
LGwebOSTV DNS redirect: TCP/UDP 53 from 192.168.88.15 -> MikroTik DNS, enabled
GalaxyGalina rule: 192.168.88.17/32 -> kolibri-home-gw, enabled
GalaxyGalina DNS redirect: TCP/UDP 53 from 192.168.88.17 -> MikroTik DNS, enabled
Historical observation before rollback: MacBook TCP/443 traffic to Google/Yandex through kgmhomeexit78.
Observed on 78 exit: TV TCP/443 traffic to Google/YouTube through kgmhomeexit78.
```

Prepared RouterOS scripts:

```routeros
/system/script/run kolibri-home-gw-enable-macbook
/system/script/run kolibri-home-gw-disable-macbook
/system/script/run kolibri-home-gw-enable-tv
/system/script/run kolibri-home-gw-disable-tv
/system/script/run kolibri-home-gw-enable-galaxy
/system/script/run kolibri-home-gw-disable-galaxy
/system/script/run kolibri-home-gw-enable-stable-canaries
/system/script/run kolibri-home-gw-enable-lan
/system/script/run kolibri-home-gw-disable-lan
/system/script/run kolibri-home-gw-disable-all
/system/script/run kolibri-home-gw-status
/system/script/run kolibri-home-gw-guard-macbook
```

The enable scripts enable the matching routing rule and DNS redirect. The
disable scripts disable both. The normal `main` routing table remains unchanged.
`kolibri-home-gw-disable-all` is the emergency client-side rollback: it disables
all Kolibri client routing rules and all Kolibri DNS redirect rules without
removing the prepared routes or scripts.

Repo restore artifact:

```text
/opt/kolibri/repo/infra/routeros/kolibri-home-gw-scripts.rsc
```

The restore artifact is a full staged RouterOS profile. It recreates the
`kolibri-home-gw` routing table, Home gateway routes, pinned DNS upstreams,
per-client routing rules, DNS redirect rules, helper scripts, and the guard
scheduler. The default import state intentionally keeps MacBook and whole-LAN
rollout disabled while leaving LG TV and GalaxyGalina canaries enabled.

Live RouterOS helper verification on 2026-06-29:

```text
kolibri-home-gw-enable-stable-canaries installed, run-count=0
kolibri-home-gw-disable-all installed, run-count=0
No route, NAT, or rollout state changed while installing these helpers.
```

TV canary rollback:

```routeros
/system/script/run kolibri-home-gw-disable-tv
```

TV canary re-enable:

```routeros
/system/script/run kolibri-home-gw-enable-tv
```

GalaxyGalina canary rollback:

```routeros
/system/script/run kolibri-home-gw-disable-galaxy
```

GalaxyGalina canary re-enable:

```routeros
/system/script/run kolibri-home-gw-enable-galaxy
```

LAN rollout rollback:

```routeros
/system/script/run kolibri-home-gw-disable-lan
```

Guard verification on 2026-06-29:

```text
Guard script name: kolibri-home-gw-guard-macbook
Scheduler interval: 30s
Health probe: ping 192.168.88.210 count=2
Probe result during verification: 2/2 replies, avg about 426us
No canary was disabled while Home was reachable.
If Home is unreachable, the guard disables MacBook, LG TV, GalaxyGalina, LAN
rollout, and all matching Kolibri DNS redirect rules.
```

Guard route:

```text
10.254.10.1/32 via 192.168.88.210, comment="Kolibri Home gateway health peer"
```

Guard scheduler:

```text
kolibri-home-gw-guard-macbook, interval=30s
```

Despite the historical name, the guard now protects all MikroTik client
canaries. It checks Home reachability at `192.168.88.210`; if Home is not
reachable, it must disable the MacBook, LG TV, GalaxyGalina, and LAN rollout
rules, disable all matching Kolibri DNS redirect rules, and write a RouterOS
warning log entry.

The guard does not test `10.254.10.1` anymore because the selected 78 exit does
not answer that ICMP probe. Tunnel egress health and endpoint failover are
handled on Home by `/usr/local/sbin/kolibri-gomesh-home-failover`.

### MikroTik DNS

Current DNS decision on 2026-06-29:

```text
MikroTik DHCP still gives LAN clients DNS server 192.168.88.1.
MikroTik upstream DNS is pinned to 1.1.1.1 and 8.8.8.8.
Provider dynamic DNS remains visible but is not the preferred resolver.
```

Reason:

```text
LGwebOSTV showed YouTube error -137 for host www.youtube.com.
MikroTik `/resolve www.youtube.com` failed with `dns server failure` while using
provider dynamic DNS 89.232.109.74 and 217.23.177.252.
Direct tests through 1.1.1.1 and 8.8.8.8 resolved YouTube correctly.
After `/ip/dns/set servers=1.1.1.1,8.8.8.8 allow-remote-requests=yes` and cache
flush, MikroTik resolved www.youtube.com and Home queries to @192.168.88.1
returned YouTube A records.
```

Validation commands:

```routeros
/ip/dns/print
:put "yt_ip=$[:resolve www.youtube.com]"
/ip/dns/cache/print where name~"youtube|google"
```

Rollback to provider DNS:

```routeros
/ip/dns/set servers=""
/ip/dns/cache/flush
```

Do this rollback only if the static DNS causes a visible regression; the
provider dynamic DNS was the direct cause of the TV YouTube name-resolution
failure.

## Validation

Main listener:

```sh
ss -lntup | grep 29445
systemctl is-active kolibri-tunneld-home-exit.service
```

Home tunnel:

```sh
systemctl is-active kolibri-gomesh-home-client.service
/usr/local/sbin/kolibri-gomesh-home-failover status
/usr/local/sbin/kolibri-gomesh-home-healthcheck
/usr/local/sbin/kolibri-gomesh-status --runtime --pretty
/usr/local/sbin/kolibri-gomesh-probe-site --pretty https://www.youtube.com https://platform.xiaomimimo.com/
curl -4 --interface kgmhome0 --max-time 12 https://ifconfig.me
curl -4 -I -L --interface kgmhome0 --max-time 12 https://www.youtube.com
ip -s link show kgmhome0
iptables -S FORWARD | grep 'Kolibri Home gateway'
iptables -t mangle -S FORWARD | grep 'Kolibri Home gateway'
```

Expected result from the verified run:

```text
endpoint=78.17.4.108:29445
health=ok
kolibri-gomesh-status: ok=true, countries=["FI","FR","LV"]
service_profile: --carrier auto, --timeout 2s, --queue-size 4096
External IP through kgmhome0: 78.17.4.108
YouTube through kgmhome0: HTTP/2 200
```

Latest runtime check on 2026-06-29T02:41:57Z:

```text
Home endpoint: 78.17.4.108:29445, health=ok
Home external IP through kgmhome0: 78.17.4.108
YouTube through kgmhome0: HTTP 200 in about 532 ms
Xiaomi MiMo through kgmhome0: HTTP 200 in about 302 ms
LGwebOSTV route: 192.168.88.15 -> kgmhome0 table 1099
GalaxyGalina route: 192.168.88.17 -> kgmhome0 table 1099
```

Xiaomi MiMo platform check on 2026-06-29:

```text
Domain: platform.xiaomimimo.com
DNS: platform.xiaomimimo.com -> mimo-pri-azams.alb.xiaomi.com
A records: 20.47.115.50, 20.157.221.14
Direct Home PPPoE path: curl HTTPS timed out during SSL connection.
Kolibri Home path with --interface kgmhome0: HTTP/2 200 in about 280-315 ms.
FI exit 78.17.4.108 direct check: HTTP/2 200 and TLS certificate OK.
Conclusion: the domain does not need a new service-specific route; it needs
clients to use the existing obfuscated Kolibri path instead of direct PPPoE.
```

`kolibri-gomesh-probe-site` comparison after the fast profile update:

```text
Home process: kolibri-tunnelctl tun-client --carrier auto --timeout 2s --queue-size 4096.
kgmhome0 state: UP/LOWER_UP, mtu 1280, RX/TX packets increasing, no link errors.
YouTube direct: HTTP 200, about 0.42s.
YouTube through kgmhome0: HTTP 200, about 0.53s.
Xiaomi MiMo direct: SSL connection timeout after about 8s.
Xiaomi MiMo through kgmhome0: HTTP 200, about 0.28s.
```

MikroTik canary route test:

```routeros
/ip/route/remove [find comment="Kolibri GoMesh canary via Home"]
/ip/route/add dst-address=1.1.1.1/32 gateway=192.168.88.210 comment="Kolibri GoMesh canary via Home"
/ping 1.1.1.1 src-address=192.168.88.1 count=4
/ip/route/remove [find comment="Kolibri GoMesh canary via Home"]
```

Expected result from the verified run:

```text
4 sent, 4 received, 0% loss, average about 46 ms
```

Home `kgmhome0` RX/TX counters should increase during the canary test.

MacBook client canary validation:

```text
MacBook canary enabled after adding Home FORWARD rules.
MikroTik guard kept the canary rule enabled after a 30-second guard interval.
Home `kgmhome0` counters increased from small test counts to active traffic.
tcpdump saw bidirectional TCP/443 headers for 192.168.88.12 with 1228-byte
payload segments returning from `kgmhome0`.
```

First failure cause:

```text
The first MacBook YouTube canary did not work because Home had FORWARD policy
DROP and no explicit `enp3s0 <-> kgmhome0` forwarding rules. Home itself could
open YouTube over `kgmhome0`, but forwarded MacBook traffic could be dropped.
The fix is the two Home FORWARD rules plus the TCP MSS clamp documented above.
```

Historical health peer from MikroTik before switching Home to 78:

```text
10.254.10.1 via 192.168.88.210: 3/3 ICMP replies, about 35 ms
```

After switching Home to 78, use the HTTPS healthcheck above instead of this
ICMP check.

## Safe rollout options

### MikroTik container smoke-test

MikroTik hAP ac2 has the `container` package installed and an ext4 USB disk
mounted as `usb1-part1`.

Verified on 2026-06-29:

```text
RouterOS: 7.20.2 stable
Board: hAP ac2, ARM, 128 MiB RAM
USB: usb1-part1, ext4, about 7.4 GiB free
Container image: registry-1.docker.io/library/busybox:latest
Container arch: linux/arm/v7
Container comment: Kolibri container smoke
Container state: running
Container IP: 172.30.78.2/24
Router bridge IP: 172.30.78.1/24
Ping 172.30.78.2 from RouterOS: 3/3 replies, about 0.5 ms
```

Container support objects:

```routeros
/container/config/print
/interface/bridge/print detail where name=kolibri-containers
/interface/veth/print detail where name=veth-kolibri-test
/ip/address/print detail where comment="Kolibri container smoke gateway"
/ip/firewall/nat/print detail where comment="Kolibri container smoke NAT"
```

Rollback for the smoke container:

```routeros
/container/stop [find comment="Kolibri container smoke"]
/container/remove [find comment="Kolibri container smoke"]
/interface/bridge/port/remove [find comment="Kolibri container smoke port"]
/interface/veth/remove [find name="veth-kolibri-test"]
/ip/address/remove [find comment="Kolibri container smoke gateway"]
/ip/firewall/nat/remove [find comment="Kolibri container smoke NAT"]
/interface/bridge/remove [find name="kolibri-containers"]
```

Current boundary: this proves RouterOS containers can run from the USB disk. It
does not yet prove the GoMesh packet dataplane is safe inside a RouterOS
container. Do not route LAN traffic through a container until a dedicated ARMv7
Kolibri image passes a no-LAN canary and a rollback is prepared.

### Direct MacBook canary to 78

Preferred for a single MacBook when speed matters:

```text
MacBook Kolibri client -> 78.17.4.108:29445 -> kgmhomeexit78 -> internet
```

This bypasses MikroTik policy routing through Home. It does not automatically
cover TV, iPhone, or other LAN clients; each device needs its own Kolibri client
or the LAN needs a central MikroTik-native tunnel.

Validation:

```text
1. Confirm `78.17.4.108:29445` is reachable.
2. Start the MacBook Kolibri client against `78.17.4.108:29445`.
3. Confirm external IP and YouTube from the MacBook.
4. Direct-client mode bypasses the MikroTik/Home gateway. Before using it,
   disable the MikroTik MacBook gateway canary with
   `/system/script/run kolibri-home-gw-disable-macbook`; re-enable it afterwards
   with `/system/script/run kolibri-home-gw-enable-macbook` if returning to the
   central gateway path.
```

### Direct whole-LAN canary to 78

Preferred for "all devices at once" only after a MikroTik-native tunnel exists:

```text
clients -> MikroTik -> MikroTik-native tunnel -> 78.17.4.108 -> internet
```

The current repo does not include a RouterOS-native Kolibri GoMesh v0 client.
Use this path only with a supported RouterOS tunnel such as WireGuard/IPsec, or
after a RouterOS-native Kolibri client exists. Keep the Home gateway as fallback
until this direct tunnel is proven.

### Single destination canary

Use a single `/32` route on MikroTik, as shown above. This is the safest test
because rollback is a single route removal.

### Single client canary

The current prepared MacBook canary can be enabled with:

```routeros
/system/script/run kolibri-home-gw-enable-macbook
/routing/rule/print detail where comment="Kolibri Home gateway MacBook"
```

Rollback:

```routeros
/system/script/run kolibri-home-gw-disable-macbook
/routing/rule/print detail where comment="Kolibri Home gateway MacBook"
```

Expected rule state after rollback:

```text
disabled=yes, src-address=192.168.88.12/32, table=kolibri-home-gw
```

Historical controlled MacBook canary before rollback:

```text
MacBook rule was enabled after Home and exit checks passed.
MacBook DNS redirect was enabled for TCP/UDP 53.
kolibri-home-gw-guard-macbook kept it enabled while Home was reachable.
Home and 78 exit saw bidirectional TCP/443 traffic for 192.168.88.12.
```

Historical post-firewall-fix MacBook canary before rollback:

```text
MacBook rule was enabled.
Home FORWARD rules and MSS clamp present.
Guard kept the rule enabled after one interval.
Home saw bidirectional TCP/443 traffic for the MacBook.
```

### Whole LAN rollout

Do this only after a single-client canary is stable.

Prepared but disabled on MikroTik:

```text
routing rule: Kolibri Home gateway LAN rollout, 192.168.88.0/24 -> kolibri-home-gw, disabled
DNS UDP rule: Kolibri DNS redirect LAN UDP, disabled
DNS TCP rule: Kolibri DNS redirect LAN TCP, disabled
```

Prepared RouterOS scripts:

```routeros
/system/script/run kolibri-home-gw-status
/system/script/run kolibri-home-gw-enable-lan
/system/script/run kolibri-home-gw-disable-lan
```

The current state is safe: `kolibri-home-gw-enable-lan` has not been run. The
LG TV and GalaxyGalina canaries are the only enabled client routes.

Use the prepared script for the actual rollout:

```routeros
/system/script/run kolibri-home-gw-enable-lan
```

Immediate rollback:

```routeros
/system/script/run kolibri-home-gw-disable-lan
```

Historical manual equivalent:

```routeros
/routing/table/add name=kolibri-home-gw fib
/ip/route/add dst-address=0.0.0.0/0 gateway=192.168.88.210 routing-table=kolibri-home-gw comment="Kolibri Home gateway default"
/routing/rule/add src-address=192.168.88.0/24 action=lookup-only-in-table table=kolibri-home-gw comment="Kolibri Home gateway LAN"
```

Rollback:

```routeros
/routing/rule/remove [find comment="Kolibri Home gateway LAN"]
/ip/route/remove [find comment="Kolibri Home gateway default"]
/routing/table/remove [find name=kolibri-home-gw]
```

## Public web port-forward coexistence

`kolibriai.ru` currently resolves to the MikroTik public IP `178.207.11.90`.
The public web app is served by Home nginx at `192.168.88.210`, which proxies
the frontend to `78.17.4.108:5174` and the backend API locally on Home.

RouterOS live rules added on 2026-06-29:

```text
dstnat tcp 178.207.11.90:80  -> 192.168.88.210:80   comment="Kolibri public web HTTP -> Home nginx"
dstnat tcp 178.207.11.90:443 -> 192.168.88.210:443  comment="Kolibri public web HTTPS -> Home nginx"
srcnat masquerade 192.168.88.0/24 -> 192.168.88.210 tcp 80,443 comment="Kolibri public web hairpin -> Home nginx"
forward accept dstnat tcp 192.168.88.210:80,443 comment="Kolibri public web allow dstnat -> Home nginx"
```

Home GoMesh policy routing marks normal external traffic through
`KOLIBRI_HOME_EXIT`. Public web replies must not be marked into GoMesh, or
external HTTPS clients will hang. This is persisted in
`/usr/local/sbin/kolibri-home-gateway-setup` and removed by
`/usr/local/sbin/kolibri-home-gateway-teardown`:

```sh
iptables -t mangle -C KOLIBRI_HOME_EXIT -p tcp -m multiport --sports 80,443 \
  -m comment --comment 'Kolibri-public-web-return-direct-via-MikroTik' -j RETURN
```

Validated on 2026-06-29:

```text
https://kolibriai.ru/ = 200
https://kolibriai.ru/api/health = {"status":"ok", ...}
TLS CN = kolibriai.ru, issuer = Let's Encrypt E8
```

Rollback only the public web port-forward:

```routeros
/ip/firewall/nat/remove [find comment~"Kolibri public web"]
/ip/firewall/filter/remove [find comment~"Kolibri public web"]
```

## Hard rollback

Home:

```sh
systemctl disable --now kolibri-gomesh-home-healthcheck.timer
systemctl disable --now kolibri-gomesh-home-client.service
/usr/local/sbin/kolibri-home-gateway-teardown
```

Main:

```sh
systemctl disable --now kolibri-tunneld-home-exit.service
/usr/local/sbin/kolibri-home-exit-teardown
```

MikroTik:

```routeros
/system/script/run kolibri-home-gw-disable-all
/ip/route/remove [find comment~"Kolibri GoMesh"]
/routing/rule/remove [find comment~"Kolibri Home gateway"]
/ip/route/remove [find comment~"Kolibri Home gateway"]
/routing/table/remove [find name=kolibri-home-gw]
```

## Notes

- Do not run GoMesh dataplane in RouterOS containers on hAP ac2.
- Do not change MikroTik DHCP default gateway until single-client canary has
  passed.
- Do not print or copy PSK material into logs or docs.
- MikroTik DNS is pinned to `1.1.1.1,8.8.8.8`; keep that unless a visible
  regression is found. The provider dynamic DNS caused the LG TV YouTube
  `-137` name-resolution failure.
