# PLAN

Task: `P0_PRODUCT_SKILLS_SYNC_TO_REMOTE_WORKERS_2026_07_02`

Plan:

1. Add a deployable local-only skills registry and install/update CLI.
2. Enforce versioning, content hashing, atomic copy, downgrade protection, and
   network-source rejection.
3. Add focused tests proving first install, update, blocked network source,
   blocked tamper/hash mismatch, missing update, and downgrade refusal.
4. Document the owner/operator command path and record verification evidence.

