# Telegram channel activation

Telegram is a channel adapter for the same `kolibri` Responses execution and
durable project/message repository used by the Web Shell. It is not a second
assistant, polling worker, watchdog, GoMesh reporter, or independent task
authority.

The backend is fail-closed by default. A receiver is only configured when all
of the following are present in the protected Home-only activation file:

- explicit owner approval;
- a Telegram-compatible random webhook secret of at least 32 characters;
- an explicit owner chat allowlist;
- the public HTTPS base URL used to deliver verified artifacts;
- the webhook enable flag.

The Bot API token is never loaded by the public ASGI receiver and must not be
copied into the repository or general worker nodes. Only the canonical
Home Telegram worker reads it from the protected root-owned
`/etc/kolibri/telegram.env` file. An owner-controlled activation job uses the
same protected token to register the exact
`https://kolibriai.ru/api/v1/telegram/webhook` URL with the same secret, checks
`getWebhookInfo`, and records sanitized evidence. Before processing any update,
the canonical worker runs `getMe` and persists only the bot ID, username,
verification status and timestamp. A username other than exactly
`@kolibriai_bot` blocks execution without printing the token or credential URL.
Until that external check succeeds, `/api/v1/telegram/info` reports
`configured_unverified`, never `live`.

Readiness never trusts a static environment flag. The receiver derives the
original client address through an explicit trusted-proxy chain, accepts live
evidence only from Telegram's current official webhook networks, and stores a
minimal singleton evidence row in the application database. The row contains
only the update ID, response method, official network and timestamp; it does
not store a token, secret header, user text or exact source address. Evidence
expires, so a broken route returns to `configured_unverified` instead of
remaining permanently green.

When the stateless public relay is used, install its exact mesh address as a
narrow `/32` in `KOLIBRI_TELEGRAM_TRUSTED_PROXY_CIDRS`. The relay overwrites
`X-Forwarded-For` with Telegram's socket address. Home nginx appends the relay
mesh address, and the backend walks that chain from right to left. Broad proxy
trust ranges are rejected.

The backend service reads only `/etc/kolibri/telegram-webhook.env`. If the file
is absent, the explicit unit defaults keep Telegram disabled. The separate
`kolibri-telegram-worker.service` additionally reads the protected Bot API
token file. Both files must be root-owned and mode `0600`; neither belongs in
the backend process environment.

The webhook returns after authentication and a committed `telegram_updates`
row. Provider execution and Bot API output never run inside the webhook
request. Durable `update_id` uniqueness rejects conflicting replays and makes
exact re-delivery a no-op. The worker sends one visible acknowledgement,
executes the same canonical Responses contract as Web, and changes that
message to the terminal text (or sends a verified image artifact). Project and
message IDs are retained so the reply can link to the same project in Shell.

Required release checks:

1. the same update ID executes the provider once and creates one assistant
   placeholder;
2. text is returned without provider stderr, local paths, or HTML parsing;
3. an image response uses `sendPhoto` only with a verified artifact URL, size,
   MIME type, and SHA-256;
4. an unapproved chat is rejected before provider execution;
5. watchdog, GoMesh, legacy sender, polling, and duplicate gateway processes
   remain absent from the Home runtime inventory.
6. `python -B -m app.telegram_worker --check-identity` reports the sanitized
   username `kolibriai_bot` and exits successfully before enabling the worker;
7. webhook acknowledgement is below one second while a deliberately slow
   provider continues asynchronously;
8. a duplicate update ID neither invokes Responses again nor sends another
   acknowledgement or terminal notification.

No command in this directory registers the webhook, enables the unit, or reads
the protected Bot API credential automatically.
