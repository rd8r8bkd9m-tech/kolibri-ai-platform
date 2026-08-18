# Kolibri Agent Skills v3

This package is designed for autonomous coding agents that must **build the product**, not cycle indefinitely through tests.

## Core principle

`implementation > integration > focused verification > broad regression`

The skill set contains 250 operational skills. Every skill also carries the development-first anti-loop execution contract. The governance layer adds state-machine control, progress accounting, anti-loop rules, production-first completion gates, evidence contracts, and handoff discipline.

## Install

Copy `.agents/` into the root of the repository.

## Validate

Run:

```bash
bash .agents/scripts/validate-skills.sh
python3 .agents/scripts/validate_skills.py
```

## Recommended agent boot sequence

1. Read `AGENTS.md`.
2. Load `00-orchestration/mission-control`.
3. Load `00-orchestration/task-state-machine`.
4. Load only the domain skills needed for the task.
5. Implement one vertical slice.
6. Verify the real path.
7. Update progress ledger.
8. Handoff or continue with the next slice.
