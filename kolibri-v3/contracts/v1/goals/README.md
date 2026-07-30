# Kolibri Goal and ProjectCase contracts v1

Task: `P02-T02`

`Goal` is owned by the Logical Home Control Plane. It stores the user intent,
measurable acceptance criteria, bounded budget/deadline policy and lifecycle.
`ProjectCase` is the versioned structured case index linked to one exact Goal
version. Product/Data Authority may expose projections and domain editors but
does not create a second Goal or Case authority.

The contracts deliberately keep these concepts separate:

- `intent` contains the original request and normalized objective;
- `acceptance_criteria` state what success means and how it is verified;
- `budget_policy` and `deadline_policy` bound execution;
- `facts` are sourced observations;
- `assumptions` are temporary working values with confidence and impact;
- `proposals` are unselected options;
- `decisions` are authority-backed selections linked to proposals when used;
- `open_questions` are explicit unresolved or resolved requests, with blocking
  status independent from assumptions.

Goal creation and ordinary updates are explicit commands. Creation only accepts
version `1`, status `new`, empty case/workflow links, and timestamps bound to
the request. Updates use optimistic `expected_version`, carry the complete next
aggregate, and cannot change identity, creation time, or lifecycle state.
Lifecycle changes use a separate transition command.

State transitions are allowlisted in `goal-transitions.json` and
`../cases/project-case-transitions.json`. Transition commands use optimistic
`expected_version` and require `next_version == expected_version + 1`.
Terminal states have no outgoing transitions. Released/completed records are
not rewritten; later work creates a superseding version.

Transition payloads are never accepted as standalone transport commands.
`createGoalCaseCommandValidator` first validates the full common command
envelope (tenant, actor, authority, trace and idempotency), then validates the
domain payload and binds its Goal/ProjectCase identifier to
`identity.subject_refs`. Both transitions are owned by
`logical_home_control_plane`; the physical placement is carried separately in
the authority context and does not redefine logical ownership. Full examples
are provided as `valid-goal-create-command.json`,
`valid-goal-update-command.json`, `valid-goal-transition-command.json`, and
`valid-project-case-transition-command.json`.

The early `kolibri-backend/app/project_case.py` projection is an adapter input,
not the canonical contract. P04 will migrate it through versioned adapters
rather than silently treating its current metadata shape as authoritative.

Run:

```bash
backend/venv/bin/python -m pytest -q tests/test_goal_project_case_contract_schemas.py
```
