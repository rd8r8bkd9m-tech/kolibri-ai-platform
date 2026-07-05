# Next

Owner gate:

1. Owner reviews PR #85.
2. If approved, mark PR #85 ready and merge through GitHub.
3. After merge, route any required deployment/canary through a separate Control Plane task.

Runner follow-up:

- Fix release-gate verifier sequencing so final shell verification stays on the reviewed PR head or uses explicit paths available on the active branch.
- Provide server GitHub Actions/check-run access or route check-run verification through command-node API relay.

Do not merge automatically.
