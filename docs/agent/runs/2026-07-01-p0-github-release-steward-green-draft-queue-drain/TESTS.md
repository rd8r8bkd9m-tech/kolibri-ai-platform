# Tests

Command-node checks:

```bash
git ls-remote --heads origin main codex/factory-dispatcher-ledger-2026-07-01
```

Evidence:

- `main` -> `a0d34d6d97a1a2af90463a1205649a24b4a178d7`
- `codex/factory-dispatcher-ledger-2026-07-01` -> `d4559722ea3e0a36109fcf6401e695d60deadb3b`

GitHub API snapshot:

| PR | Draft | Mergeable | State | Head | Checks |
| --- | --- | --- | --- | --- | --- |
| #83 | true | true | clean | `3560af06` | `ci:success` |
| #85 | true | true | clean | `30b7e5dc` | `ci:success` |
| #88 | true | true | clean | `d4559722` | `ci:success`, `ci:success` |
| #89 | true | true | clean | `e14aae21` | `ci:success` |
| #91 | true | true | clean | `35054449` | `ci:success` |
| #92 | true | true | clean | `5a33c3fc` | `ci:success` |
| #96 | true | true | clean | `42625cad` | `ci:success` |
| #97 | true | true | clean | `f542c5c7` | `ci:success` |

Local file validation to run before commit:

```bash
python3 -m json.tool docs/agent/dispatcher/envelopes/P0_GITHUB_RELEASE_STEWARD_GREEN_DRAFT_QUEUE_DRAIN_2026_07_01.json
git diff --check
```
