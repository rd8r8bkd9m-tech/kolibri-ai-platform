# Top 5 Fastest P0 Exits

1. PR #84, `[docs] Add Kolibri Superfactory master canvas`
   - Why fast: docs-only, 6 files, mergeable, no runtime surface.
   - Exact next action: owner mark ready and merge as docs-only, or close if superseded by newer superfactory docs.

2. PR #93, `Record PR85 Fabric API gap review`
   - Why fast: docs-only, mergeable, PR85 already landed in `main`.
   - Exact next action: close as superseded by PR85 merge unless owner wants the historical artifact packet in main; if keeping, mark ready and merge docs-only.

3. PR #94, `Record PR85 release gate after Prompt3 repair`
   - Why fast: docs-only, mergeable, PR85 already landed in `main`.
   - Exact next action: close as superseded by PR85 merge unless owner wants the historical gate packet in main; if keeping, mark ready and merge docs-only.

4. PR #38, `Проверить удалённый runner фабрики`
   - Why fast: one test file, mergeable, stale proof PR.
   - Exact next action: close as stale proof if PR83/runner contracts in main supersede it; otherwise run `python3 -m pytest tests/test_factory_runtime_contracts_remote.py -q` on the PR head and merge test-only.

5. PR #86, `P0: Establish Kolibri GitHub Operating System`
   - Why fast: mergeable docs/templates with no product code, but workflow-affecting.
   - Exact next action: owner review `.github/CODEOWNERS` and templates, then mark ready and merge; defer blocked admin actions documented in the PR.

Near-fast but not top 5:
- PR #90 is mergeable and important, but changes backend auth code and requires dependency-satisfied verifier plus post-merge auth smoke.
- PR #87 is docs-only but large business material and should be moved out of P0 unless it is an owner priority.
