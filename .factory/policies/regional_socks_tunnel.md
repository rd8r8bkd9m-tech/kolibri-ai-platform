# Regional SOCKS Tunnel

Local SOCKS5 proxy:

```text
127.0.0.1:1088 -> hostvds-agent-06 / 45.39.33.252
```

LaunchAgent:

```text
com.kolibri.us-socks-tunnel
```

Use for development traffic that needs to originate from the VPS region.
Do not use it for account abuse, fraud, or bypassing service rules.

Verify:

```bash
launchctl print gui/$(id -u)/com.kolibri.us-socks-tunnel
lsof -nP -iTCP:1088 -sTCP:LISTEN
curl --socks5-hostname 127.0.0.1:1088 https://api.ipify.org
```

Browser proxy:

```text
SOCKS5 host: 127.0.0.1
SOCKS5 port: 1088
```

CLI:

```bash
curl --socks5-hostname 127.0.0.1:1088 https://api.ipify.org
```
