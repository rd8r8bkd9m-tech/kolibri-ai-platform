# CI And Test Evidence

Authoritative GitHub evidence gathered by Mac dispatcher before this remote gate:

- PR #85: draft, mergeable.
- Head: `06adeb54c0e7d7132c7f0817ea4755786cd3f092`.
- GitHub Actions: `Kolibri CI / ci` completed `SUCCESS` for that head.

Remote server evidence gathered by this release gate:

- Focused tests: `11 passed in 0.13s`.
- Full suite in isolated venv: `71 passed, 1 warning in 4.24s`.
- `python3 -m py_compile ops/factory_control.py`: passed.
- `git diff --check origin/main...HEAD`: failed only on extra blank lines at EOF in new docs.

Limitations:

- `gh` is not installed on the remote node.
- GitHub connector combined status returned no legacy statuses.
- Unauthenticated REST check/status endpoints returned HTTP `404` from the remote node.
