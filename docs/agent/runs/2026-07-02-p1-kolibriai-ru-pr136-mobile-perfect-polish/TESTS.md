# Tests

## Commands

```text
git diff --check
```

Result: passed.

```text
PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm run build
```

Working directory: `remote/kolibriai-frontend`

Result: passed with Node.js `20.19.5`.

```text
PATH=/var/lib/kolibri-agent/tools/node20/node_modules/node/bin:$PATH npm run lint
```

Working directory: `remote/kolibriai-frontend`

Result: passed with Node.js `20.19.5`.

## Prior Mesh-Agent-17 Evidence

- The prior remote-authored run passed `npm run build` with Node 20.
- The prior remote-authored run passed `npm run lint` with Node 20.
- The prior remote-authored run served the Vite dev server and received `200 OK`.
