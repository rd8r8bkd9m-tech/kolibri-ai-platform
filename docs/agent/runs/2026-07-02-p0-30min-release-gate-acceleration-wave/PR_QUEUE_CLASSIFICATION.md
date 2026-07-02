# PR Queue Classification

Snapshot date: 2026-07-02 UTC.

GitHub access:
- `gh` CLI: unavailable on node.
- REST without token: blocked for private repo, `404`.
- Git over SSH: available for remote refs.
- GitHub connector: available for PR metadata.

## Classified Open PRs

| PR | State | Draft | Mergeable | Base | Size | Classification | Exact next action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| #90 | open | yes | yes | `main` | 24 files, +961/-1 | Fast merge candidate after dependency-satisfied verifier; product code auth contract. | Owner mark ready only after rerunning `.venv/bin/python -m pytest tests/test_telegram_miniapp_auth.py tests/test_telegram_gateway.py -q`; then merge with post-merge Telegram Mini App auth smoke. |
| #93 | open | yes | yes | `main` | 11 files, +290/-0 | Docs-only PR85 gap-review artifact; PR85 is already merged to `main`, so this is now archival. | Close as superseded by PR85 merge unless owner wants historical run artifacts in main. If keeping, mark ready and merge as docs-only. |
| #94 | open | yes | yes | `main` | 11 files, +292/-0 | Docs-only PR85 release-gate artifact; PR85 is already merged to `main`, so this is now archival. | Close as superseded by PR85 merge unless owner wants historical gate artifacts in main. If keeping, mark ready and merge as docs-only. |
| #87 | open | yes | yes | `main` | 38 files, +4174/-0 | Business/Kwork docs package; not runtime-blocking P0. | Move out of P0 or owner mark ready as docs-only business package after quick secret scan. |
| #86 | open | yes | yes | `main` | 38 files, +1338/-0 | Governance docs/templates; low runtime risk but affects repo workflow. | Owner review CODEOWNERS/templates, then mark ready and merge as governance docs if acceptable. |
| #84 | open | yes | yes | `main` | 6 files, +403/-0 | Docs-only Superfactory canvas; lowest technical risk. | Owner mark ready and merge as docs-only, or close if superseded by later superfactory docs. |
| #81 | open | yes | no | `main` | 5 files, +604/-61 | Telegram runtime code, stale and non-mergeable after PR89/main changes. | Do not merge. Rebase onto current `main`, resolve conflicts against current Telegram receiver/gateway code, rerun targeted Telegram/mesh tests. |
| #61 | open | no | no | `main` | 25 files, +1240/-118 | Older Telegram Mini App/director bot implementation, non-mergeable and likely overlapped by PR89/#90. | Close or supersede after confirming #89/#90 cover Mini App/director requirements; otherwise rebase into a new focused PR. |
| #60 | open | no | yes | `codex/factory-autonomy-pwa-billing` | 1 file, +77/-0 | Result-capture PR against non-main base; not a direct release gate. | Retarget/close. If evidence is still needed, cherry-pick the single docs file into a fresh `main` docs PR. |
| #38 | open | no | yes | `main` | 1 file, +35/-0 | Remote runner smoke test proof; stale but tiny. | Close as stale proof if newer runner contracts in main supersede it; otherwise merge as test-only after one targeted pytest. |
| #37 | open | no | yes | `factory/kol-live-factory-status-ui-20260626-050716` | 14 files, +3261/-390 | Runtime hardening PR against non-main base, large/stale. | Do not merge directly. Split current still-needed changes into focused main-based PRs; close this branch after split. |

## Already-Landed / Superseded Signals

Local `origin/main` includes merge commits through PR #104 and previous dispatcher records show PR #83, #85, #88, #89, #91, #92, #96, #97, and #98 landed. Their PR refs may still appear as unmerged by ancestry because several landed through squash/merge commits or release-sync branches, so connector state and main commit history are the source of truth.
