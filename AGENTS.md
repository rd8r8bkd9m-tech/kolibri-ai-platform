# KolibriAI Platform Agent Handoff

Owner directive date: 2026-07-05.

This branch is the clean Home-first implementation candidate for Kolibri AI OS. It preserves the active runtime as an external compatibility source while building the tracked Rust/API/Shell foundation side by side.

## Active Workspace

- Worktree: `/Users/kolibri/Documents/Codex/worktrees/kolibri-ai-os-foundation-20260712`
- Branch: `codex/kolibri-ai-os-foundation-20260712`
- Base commit: `9028a20d8522649e419dcae31ce906bebf7ad6b1`
- Production status: unchanged; this worktree is not deployed
- Related Rust foundation worktree: `/Users/kolibri/.codex/worktrees/b56d/kolibri-ai-platform`
- Clean V2 donor worktree: `/Users/kolibri/Documents/Codex/worktrees/kolibri-home-first-release-20260711`

## Read First

1. `.kolibri/AGENT_START_HERE.md`
2. `.kolibri/LEAD_AGENT_ACCESS_POLICY.md`
3. `docs/SOURCE_OF_TRUTH.md`
4. `docs/PROJECT_MAP.md`
5. `docs/CONTROL_PLANE_AGENT_MODEL.md`
6. `docs/BOOTSTRAP_TRUTH.md`
7. `README.md`

## Current Verified Slice

Use the repository-managed Python environment where present and the pinned Rust toolchain. The minimum foundation checks are:

```bash
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace --all-targets
backend/venv/bin/python -m pytest -q tests/test_factory_control_superfactory.py tests/test_telegram_superfactory_miniapp.py tests/test_telegram_superfactory_contracts.py
```

The base commit carried passing Rust contract/parity tests and the existing Superfactory compatibility slice. Re-run all checks after every imported donor slice; do not treat base evidence as proof for new changes.

## Safety

- Do not read or commit `ops/telegram.env`.
- Do not log raw secrets.
- Do not run production deploy, bootstrap, DNS, REG.RU, firewall, server reboot/reinstall, or destructive data operations without approval.
- Do not discard untracked runtime artifacts without approval.
- Worker agents must use API contracts, not SSH.
- Do not deploy this candidate or change REG.RU/DNS until an exact owner-approved release diff exists.
