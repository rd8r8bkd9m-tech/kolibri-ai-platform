# Mini App Contract

The Telegram Mini App entrypoint remains:

`frontend/public/telegram-miniapp.html`

Every Mini App request sends `X-Telegram-Init-Data`. The Control Plane validates
Telegram Web App `initData` with HMAC-SHA256 and authorizes only configured
owner or admin identities.

Covered states:

- `loading`
- `error`
- `empty`
- `success`

The compatibility verifier path is satisfied by
`tests/test_telegram_superfactory_miniapp.py`, which exercises Mini App auth and
owner-scoped task envelope generation without exposing token values.
