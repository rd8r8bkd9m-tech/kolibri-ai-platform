# PR Ready Checklist

Ready:
- [x] Branch is isolated from P0 Control Plane and Telegram work.
- [x] Frontend and Telegram are not mixed.
- [x] Backend product routes were not changed.
- [x] Billing, FormulaLM, model gateway, PR #46, PR #119, and PR #121 were not touched.
- [x] `frontend/` remains the code source of truth.
- [x] `kolibriai.ru` is documented as product source of truth.
- [x] Required run artifacts are present.
- [x] Build passed.
- [x] Lint passed.
- [x] Mobile layout guard passed.
- [x] Targeted pytest passed under Python 3.12.
- [x] Yandex Browser local visual check passed.

Known blockers outside this branch:
- Public `kolibriai.ru` hard refresh can blank in Yandex.
- `curl` sees TLS hostname mismatch for `kolibriai.ru`.
- `curl -k https://kolibriai.ru/` returns MikroTik File Sharing HTML.
- `curl -k https://kolibriai.ru/api/health` and `/api/factory/status` return `{"error":"Invalid request."}`.

PR recommendation:
- Open as draft until deployment/proxy owner confirms where this frontend should be published.

