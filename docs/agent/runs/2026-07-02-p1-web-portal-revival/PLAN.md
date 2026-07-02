# P1 Web Portal Revival Plan

Task: `P1_KOLIBRI_WEB_APP_PORTAL_REVIVAL_2026_07_02`

Branch: `p1/web-portal-revival-2026-07-02`

Scope:
- Work only on the Kolibri AI web portal track.
- Use `kolibriai.ru` as the product reference.
- Keep backend changes out unless a tiny route shim is unavoidable.
- Do not mix Telegram, billing, FormulaLM, Control Plane repair, model gateway, PR #46, PR #119, or PR #121.

Execution plan:
1. Audit current `frontend/`, public `kolibriai.ru`, backend route contracts, and useful remote frontend artifacts.
2. Decide frontend source of truth.
3. Refresh the first screen toward the live `kolibriai.ru` chat shell.
4. Make runtime status honest for factory, model providers, documents, and RAG/search.
5. Switch public search call from direct `/rag/search` to same-origin `/api/knowledge/search`.
6. Add focused route-contract tests and CI lint config from existing frontend branches.
7. Verify build, lint, mobile layout guard, targeted backend/frontend tests, and Yandex browser rendering.

