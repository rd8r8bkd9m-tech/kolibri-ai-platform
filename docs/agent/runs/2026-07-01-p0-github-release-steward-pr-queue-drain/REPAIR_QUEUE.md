# Repair Queue

Repair before merge:

- PR #96: update after PR #95, verify runner permission tests, confirm CI. This was partially handled by command-node update to head `42625cadb2c0d164e2d82598a8a887d5a9a3d1e1` with CI success.
- PR #90: rebase after PR #95 and rerun exact venv verifier.
- PR #87: rebase and review business docs for current identity and approval gates.
- PR #85: run `P0_PR85_MINOR_DOCS_WHITESPACE_FIX_2026_07_01`, rebase after #95, rerun full suite.
- PR #5: repair remote PDF QA dependencies or explicitly accept local QA.
- PR #3: port proxy contract onto current backend and run staging/production smoke.
