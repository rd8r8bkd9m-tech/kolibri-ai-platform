# Next

Recommended next action:

1. Run a focused PR #85 release gate from GitHub/CI evidence:
   `P0_PR85_FINAL_RELEASE_GATE_AFTER_MAIN_UPDATE_2026_07_01`
2. Confirm PR #85 remains CI green and mergeable clean.
3. Review whether PR #85 should be marked ready/merged before broader feature PRs.

Do not merge PR #85 automatically:

- It touches API/backend/docs/ops/tests and remains a significant Fabric API PR.
- Owner release decision is required.

Environment follow-up:

- Fix server verifier environments so full tests run inside the project venv with `pydantic`/`httpx`.
- Upgrade Node on the heavy/test server path or route frontend build to a Node 20.19+/22.12+ runner.
