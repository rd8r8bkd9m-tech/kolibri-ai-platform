# OpenAI-compatible gateway

Vista exposes a transparent gateway:

```text
REST:      /v1/{any OpenAI REST path}
Realtime:  /v1/realtime
```

Authentication uses a Vista developer project key or a signed developer/owner session. Vista forwards methods, query strings, content types, multipart/binary bodies, streaming responses and WebSocket messages to the configured upstream. The upstream `OPENAI_API_KEY` never enters the browser.

This is compatibility/proxy behavior. Vista does not claim to locally reproduce proprietary OpenAI model behavior.
