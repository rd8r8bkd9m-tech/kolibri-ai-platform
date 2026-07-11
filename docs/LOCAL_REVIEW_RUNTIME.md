# Local review runtime

The Vite review server derives its default API origin from the checked-in
`frontend/CNAME`. A process that happens to listen on a common local port is not
evidence that it is the Kolibri backend. `VITE_API_PROXY` can override the
default only with a reviewed, credential-free HTTP(S) origin; `/api`, `/v1`,
and `/ws` remain same-origin paths in the browser.

## Preflight

Verify the intended target before starting Vite:

```bash
KOLIBRI_REVIEW_API_ORIGIN=https://kolibriai.ru

curl --fail --silent --show-error \
  "$KOLIBRI_REVIEW_API_ORIGIN/v1/models" \
  | jq -e '.object == "list" and ([.data[].id] == ["kolibri"])'
```

Do not put API keys, user information, credentials, paths, query parameters, or
fragments in the origin. The Vite configuration rejects those URL forms. An
internal or locally launched backend can be used only after the same model and
health checks identify it as the intended Kolibri runtime.

## Launch

```bash
cd frontend

npm run dev
```

Use `VITE_API_PROXY="$KOLIBRI_REVIEW_API_ORIGIN" npm run dev` only to override
the CNAME-derived target after the preflight above.
The checked-in review configuration binds only `127.0.0.1:5174` and refuses to
silently choose another port.

## Verification

```bash
curl --fail --silent --show-error http://127.0.0.1:5174/v1/models \
  | jq -e '.object == "list" and ([.data[].id] == ["kolibri"])'

npm run test:proxy
```

The review listener is disposable. It never changes production, DNS, Home,
Control Plane, or another process already bound to the requested port.
