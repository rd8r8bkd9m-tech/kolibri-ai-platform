# TRUTH_FACTORY_CONCEPT.md

**Date:** 2026-07-04T22:40:00Z

## Core Idea

Kolibri Truth Factory is a decision system where no agent answer becomes accepted truth until it passes adversarial review and evidence verification.

The factory is not a queue of executors. It is a living organism where:
- Agent proposes solution
- Anti-agent finds errors
- Verifier demands evidence
- Arbiter decides
- Director creates next task
- Owner gets clear summary

Chaos is not suppressed. Chaos becomes a controlled mechanism for finding truth.

## Core Cycle

```
Claim → Counter-claim → Evidence → Test → Artifact → Verdict → Next task
```

## Example

**Agent says:** "Control Plane works."

**Anti-agent asks:** "Which endpoint? Which timestamp? Which node? What about queue submit? What about artifact path?"

**Verifier checks:**
- GET /v1/health → 200 OK
- POST /v1/tasks → 201 Created
- POST /v1/tasks/lease → 200 Leased
- Artifact at /tmp/PROOF.md → exists, 221 bytes

**Arbiter decides:** true (with evidence)

**Director creates:** P0 stability monitoring task

## Key Principles

1. **No claim is truth without evidence**
2. **Generic completion is never proof**
3. **Every verdict must have confidence level**
4. **Contradictions are logged, not hidden**
5. **Anti-agent protects truth, not ego**
6. **Owner gets short, clear summaries**
