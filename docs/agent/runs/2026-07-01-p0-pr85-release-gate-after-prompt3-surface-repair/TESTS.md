# Tests

Server-side verification on PR #85 head `06adeb54c0e7d7132c7f0817ea4755786cd3f092`:

| Command | Result | Classification |
| --- | --- | --- |
| `python3 -m pytest tests/test_fabric_control.py tests/test_prompt3_fabric_api_surface.py -q` | `11 passed in 0.13s` | pass |
| `python3 -m pytest -q` | exit `2`; missing `pydantic` and `httpx` in system interpreter | environment gap, not PR failure |
| `python3 -m venv .release-gate-venv && .release-gate-venv/bin/python -m pip install -q -r backend/requirements.txt` | exit `0` | setup pass |
| `.release-gate-venv/bin/python -m pip install -q pytest && .release-gate-venv/bin/python -m pytest -q` | `71 passed, 1 warning in 4.24s` | pass |
| `python3 -m py_compile ops/factory_control.py` | exit `0` | pass |
| `git diff --check origin/main...HEAD` | exit `2`; extra blank lines at EOF in new `docs/superfactory/*.md` files | minor docs whitespace blocker |

GitHub status evidence from server:

- `gh` unavailable on this node: `exit 127`.
- GitHub connector combined status for `06adeb54...`: `statuses: []`.
- Unauthenticated REST check/status endpoints returned HTTP `404`.
- Mac dispatcher independently confirmed PR #85 GitHub Actions `Kolibri CI / ci` completed `SUCCESS` for the same head.
