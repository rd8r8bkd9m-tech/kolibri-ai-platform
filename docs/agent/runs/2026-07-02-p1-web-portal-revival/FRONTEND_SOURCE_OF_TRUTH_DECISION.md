# Frontend Source Of Truth Decision

Decision:
- Code source of truth: `frontend/` on current main.
- Product source of truth: public `kolibriai.ru`.
- Remote branches are artifact sources, not merge bases.

Why:
- `origin/main` contains `frontend/` and does not contain `remote/kolibriai-frontend/` or `landing/`.
- The live product direction seen in Yandex is chat-first and minimal.
- FE V3 branches contain useful UI artifacts but also stale route contracts.
- Pulling a whole remote branch would risk mixing unrelated frontend, billing, canvas, estimates, or old backend assumptions.

Applied artifacts:
- From `kolibriai.ru` live view: "Чем могу помочь?", "Спросите Колибри...", prompt-action shape.
- From FE V3 shell: welcome-state structure and owner-facing first-screen tone.
- From public proxy/frontend branches: `frontend/eslint.config.js`.
- From current main: `/api/factory/status`, same-origin `/ws/chat`, and current app shell.

Rejected artifacts:
- Direct `/cluster/status` usage from old FE V3 hooks.
- Direct host `:8000` websocket assumptions from older branches.
- Billing, canvas, FormulaLM, Telegram, and Control Plane panel work.

