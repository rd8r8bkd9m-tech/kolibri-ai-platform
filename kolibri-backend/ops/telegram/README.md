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

The Bot API token is not an application environment variable and must not be
copied into the repository or worker nodes. An owner-controlled activation job
uses the protected token once to register the exact
`https://kolibriai.ru/api/v1/telegram/webhook` URL with the same secret, checks
`getWebhookInfo`, sends one canary update, and records sanitized evidence.
Until that external check succeeds, `/api/v1/telegram/info` reports
`configured_unverified`, never `live`.

The production systemd source reads only
`/etc/kolibri/telegram-webhook.env`. If the file is absent, the explicit unit
defaults keep Telegram disabled. The file must be root-owned and mode `0600`.

Required release checks:

1. the same update ID executes the provider once and creates one assistant
   placeholder;
2. text is returned without provider stderr, local paths, or HTML parsing;
3. an image response uses `sendPhoto` only with a verified artifact URL, size,
   MIME type, and SHA-256;
4. an unapproved chat is rejected before provider execution;
5. watchdog, GoMesh, legacy sender, polling, and duplicate gateway processes
   remain absent from the Home runtime inventory.

No source change in this directory registers the webhook, enables the unit, or
reads the protected Bot API credential.
