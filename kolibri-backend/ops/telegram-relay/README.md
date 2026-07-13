# Telegram webhook relay on 78.17.4.108

This package prepares a stateless ingress for the one canonical Kolibri bot.
It proxies only `POST /api/v1/telegram/webhook` to Home over the existing mesh.
Every other path returns `404`; non-Telegram source networks and non-POST
methods are rejected. The relay has no Bot API token, webhook secret, queue,
provider, task authority, polling process, watchdog or GoMesh sender.

The allowlist is copied from Telegram's primary webhook documentation:

- `149.154.160.0/20`
- `91.108.4.0/22`

Telegram states that these ranges may change. Re-check
`https://core.telegram.org/bots/webhooks` before every release.

## Prepared deployment (not executed by this change)

1. From the signed membership manifest, resolve the current mesh addresses of
   `home` and the physical server whose public address is `78.17.4.108`. Do not
   infer either address from an old hostname or static Control Plane fallback.
2. Copy this non-secret directory to the relay. Ensure the relay already has a
   valid `kolibriai.ru` certificate and key; this change does not issue or copy
   private keys.
3. Render and run read-only TLS/nginx checks:

   ```bash
   sudo python3 telegram_relayctl.py prepare \
     --home-mesh-ip <CURRENT_HOME_MESH_IP> \
     --relay-mesh-ip <CURRENT_RELAY_MESH_IP> \
     --fullchain /etc/letsencrypt/live/kolibriai.ru/fullchain.pem \
     --private-key /etc/letsencrypt/live/kolibriai.ru/privkey.pem \
     --output /var/lib/kolibri/telegram-relay/candidate.conf \
     --live-checks
   ```

4. Add the emitted `relay_mesh_cidr_for_home` value to Home's protected
   `KOLIBRI_TELEGRAM_TRUSTED_PROXY_CIDRS`; set
   `KOLIBRI_TELEGRAM_REQUIRE_OFFICIAL_SOURCE=true`. Preserve a protected backup
   and restart the backend only through the signed release procedure.
5. After an explicit owner approval, install the relay candidate:

   ```bash
   sudo python3 telegram_relayctl.py install \
     --candidate /var/lib/kolibri/telegram-relay/candidate.conf \
     --evidence /var/lib/kolibri/telegram-relay/candidate.conf.evidence.json \
     --approval-id <OWNER_APPROVAL_ID>
   ```

6. Through the existing protected Telegram activation job, register
   `https://kolibriai.ru/api/v1/telegram/webhook` with
   `ip_address=78.17.4.108` and the protected secret token. Do not put the Bot
   API token or webhook secret on the command line or in this repository.
7. Send a real message from the owner chat. Accept the rollout only when:
   `getWebhookInfo` has no new error and its pending count drains;
   `/api/v1/telegram/info` reports a current persisted official-origin delivery;
   one response is produced; and no watchdog/GoMesh/legacy sender exists.

## Rollback

Every install returns an immutable backup path. Restore that exact backup:

```bash
sudo python3 telegram_relayctl.py rollback \
  --backup /var/lib/kolibri/release-backups/telegram-relay/<UTC_STAMP> \
  --approval-id <OWNER_APPROVAL_ID>
```

Rollback validates nginx before reloading it. It does not change DNS, the
Telegram webhook registration, Home state, or any provider credential.
