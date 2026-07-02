# P1 KolibriAI.ru PR136 Mobile Perfect Polish Plan

Task: `P1_KOLIBRIAI_RU_PR136_MOBILE_PERFECT_POLISH_2026_07_02`

Publish branch: `p1/kolibriai-ru-mobile-uiux-production-hardening-mesh-wide-2026-07-02`

## Scope

- Recover the mesh-agent-17 remote-authored PR #136 mobile polish from its run log.
- Keep product edits limited to `remote/kolibriai-frontend/src/**`.
- Add only required evidence/docs artifacts outside product source.
- Verify the final diff boundary before commit and push.
- Update draft PR #136 after the branch publish.

## Validation

- `git diff --check`
- `npm run build` in `remote/kolibriai-frontend` using Node 20
- `npm run lint` in `remote/kolibriai-frontend` using Node 20
- changed-file allowlist check

