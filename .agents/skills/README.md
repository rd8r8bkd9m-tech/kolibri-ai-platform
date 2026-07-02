# Kolibri Agent Skills

This directory contains internal Kolibri-authored agent skills. Each skill is a
self-contained Markdown definition that describes what the skill does, when to
use it, its inputs/outputs, and its safety constraints.

## Directory Structure

```
.agents/skills/
  README.md                          # This file
  kolibri-runner-hardening/SKILL.md  # AI runner contract hardening
  kolibri-github-curator/SKILL.md    # GitHub PR/branch/CI management
  kolibri-ci-doctor/SKILL.md         # CI failure diagnosis
  kolibri-fleet-inventory/SKILL.md   # Fleet health audit
  kolibri-server-recovery/SKILL.md   # Node repair procedures
  kolibri-pr-splitter/SKILL.md       # Large PR decomposition
  kolibri-formulalm-planner/SKILL.md # FormulaLM research planning
  kolibri-model-factory/SKILL.md     # Local LLM pipeline
  kolibri-business-builder/SKILL.md  # Revenue task drafting
  kolibri-finance-reporter/SKILL.md  # Financial reporting
```

## Skill Contract

Every skill must define:

| Field | Description |
| --- | --- |
| `skill_id` | Unique identifier |
| `version` | Semantic version |
| `purpose` | What the skill does |
| `trigger` | When to activate this skill |
| `inputs` | Required inputs |
| `outputs` | Expected outputs |
| `scope` | Deployment scope (dev/server/all_agents) |
| `safety` | Safety constraints and forbidden actions |
| `dependencies` | Required tools or services |
| `owner` | Responsible agent role |

## Usage

Skills are activated by the Command Fabric or by agent roles based on task
context. Skills do not execute autonomously; they are invoked through the
Control Plane task dispatch system.

## Adding New Skills

1. Create `kolibri-<name>/SKILL.md` with the required fields.
2. Submit for security review.
3. Register in `docs/superfactory/09_SKILL_REGISTRY.md`.
4. Deploy to matching scope nodes.
