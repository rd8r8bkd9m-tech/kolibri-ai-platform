# Server artifacts index

## Known artifact roots

- `/var/lib/kolibri-agent/artifacts/`
- `/var/lib/kolibri-agent/runtime-repo/`

## Confirmed/remembered task artifacts

| Task | Status | Node | Artifact reference | Notes |
|---|---|---|---|---|
| `2026-06-30-full-project-scan-for-chatgpt` | completed | `primary-candidate` | `/var/lib/kolibri-agent/artifacts/2026-06-30-full-project-scan-for-chatgpt/.../result.json` | Server full scan completed; branch `agent/2026-06-30-full-project-scan-for-chatgpt/read-only-scan` exists remotely |
| `2026-06-30-p0-integration-contract-audit` | failed | server runner | expected `docs/agent/integration/.../FRONTEND_BACKEND_CONTRACT.md` missing | Artifact contract failed |
| `2026-06-30-p0-integration-contract-audit-repair` | failed | server runner | expected `EXECUTIVE_SUMMARY.md` missing | Runner wrote wrong filenames/paths |

## Main server artifacts

Main server has artifact directories under `/var/lib/kolibri-agent/artifacts/...`. Full listing was not pulled to Mac to avoid noisy output and because the current task is read-only intelligence.

## Artifact risk

Artifact path drift is a P0 issue. A remote task should not be considered successful unless all declared required artifacts exist under the declared output directory.
