# Kolibri Living Interface Product Contract

Date: 2026-07-03
Branch: `codex/kolibriai-ru-turnkey-ai-app-redesign-2026-07-03`
Scope: PR #156 frontend concept alignment for `remote/kolibriai-frontend`.

This contract was recreated from the task envelope because it was not present in this branch at the start of this run.

## Operating Constraints

- Run only on the remote worker.
- Do not implement on Mac.
- Continue PR #156 branch `codex/kolibriai-ru-turnkey-ai-app-redesign-2026-07-03`.
- Do not create a separate Telegram branch or backend-heavy branch.
- Do not deploy live, merge, restart services, mutate credentials, or touch forbidden areas.
- If code already satisfies a requirement, document and QA it.
- If a requirement is visibly missing, implement the smallest safe frontend improvement on the same branch.
- Push the PR #156 branch only if checks pass enough to remain reviewable.

## Product Requirements

The web portal must align with the Kolibri living interface concept:

- Chat-first Russian interface with a visible Kolibri identity and immediate prompt entry.
- Mobile-first ergonomics with safe-area handling, usable navigation, readable controls, and no incoherent overlap.
- Backend-integrated work surfaces for estimates, documents, library, agents, search, auth, and AI/chat actions.
- A professional estimate pilot path that demonstrates list, editor, recalculation/save controls, export affordances, backend health status, and AI audit.
- Bird/mascot presence that communicates idle, ready, thinking, success, and error states without blocking work.
- Adaptive directions that point the user toward the next useful action based on current workspace state.
- Evidence artifacts proving concept alignment, mobile QA, dev-console/network QA, backend integration QA, professional estimate pilot QA, bird animation plan, adaptive directions QA, and production readiness.

## Acceptance Gate

Reviewable completion requires:

- Frontend build and lint pass or any failures are explicitly documented as environment blockers.
- Browser QA produces screenshots and console/network evidence.
- Backend integration gaps are documented instead of hidden.
- Changes stay scoped to frontend and product documentation unless a tiny compatibility fix is required.
