# Home Codex CLI egress

This is a localhost-only, reversible egress path for the already authorized
Codex CLI session on Home. It uses the owner-approved Amnezia/mesh egress
without restarting or rewriting that VPN, the mesh, or the Mac route. The
SOCKS listener (`127.0.0.1:11080`) is transported to the relay selected from
current membership; 3proxy exposes a localhost HTTP CONNECT endpoint
(`127.0.0.1:11081`) because Codex CLI's `respect_system_proxy` feature consumes
HTTP proxy variables.

Runtime files:

- `/etc/kolibri/codex-cli/egress.env` — selected current mesh destination;
- `/etc/kolibri/codex-cli/proxy.env` — localhost proxy variables;
- `/etc/kolibri/codex-cli/3proxy-egress.cfg` — localhost-only 3proxy config;
- `/etc/systemd/system/kolibri-backend.service.d/20-codex-cli-proxy.conf` —
  passes proxy variables to the backend without copying browser credentials.

The backend invokes `/usr/local/bin/codex`; it does not use whichever older
binary happens to be first in Home user's `PATH`. No explicit model is pinned:
the authorized account default is used unless an operator sets
`CODEX_CLI_MODEL` (or the legacy `KOLIBRI_CODEX_MODEL`) after an entitlement
probe.

The same authenticated CLI route also owns bounded image attempts. It uses an
isolated temporary workspace, accepts only verified raster bytes, and defaults
to two concurrent 600-second attempts. OpenAI REST image routing stays off
unless an operator explicitly enables it with separate service credentials.

Before an owner-approved install, validate the source units:

```bash
systemd-analyze verify \
  kolibri-codex-egress.service \
  kolibri-codex-http-proxy.service
```

Verification must prove both facts independently:

1. `curl --proxy http://127.0.0.1:11081 https://api.ipify.org` returns the
   approved public egress;
2. `codex login status` succeeds without copying its auth file;
3. the following returns JSONL with the final value `123` through the already
   authorized Home session:

```bash
printf '%s\n' 'Ответь только числом: 56+67' | \
  /usr/local/bin/codex exec --json --ephemeral --sandbox read-only \
  --skip-git-repo-check --ignore-user-config \
  --enable respect_system_proxy -
```

The backend provider then needs a real `/v1/responses` probe. A proxy socket,
login status, or heartbeat alone is not proof that the user route works.

Rollback is bounded to the dedicated egress only:

```bash
systemctl disable --now kolibri-codex-http-proxy.service
systemctl disable --now kolibri-codex-egress.service
```

The rollback does not restart WireGuard, Amnezia, the mesh, or the Mac VPN.
Remove only the dedicated backend drop-in and restore the prior backend unit
after taking its checksum; do not use a broad `systemctl revert` that could
discard unrelated operator configuration.
