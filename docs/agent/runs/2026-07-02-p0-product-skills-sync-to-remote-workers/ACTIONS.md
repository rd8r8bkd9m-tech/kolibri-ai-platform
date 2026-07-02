# ACTIONS

- Added `ops/skill_sync.py`.
- Added `tests/test_skill_sync.py`.
- Documented the deployable skills sync commands in `README.md`.
- Created this canonical run artifact set.

What now works:

- A release process can build a JSON registry from local skill bundle
  directories that contain `skill.json` metadata.
- A remote worker can run `install` or `update` against that registry and a
  local source root.
- The worker refuses HTTP/Git/SSH sources, verifies SHA-256 before copying,
  installs atomically, refuses downgrades unless explicitly allowed, and emits a
  proof JSON.

