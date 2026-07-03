# PLAN

Task: repair the Home NOC so it is an operator control surface, not a static wallboard.

Base/source of truth:
- Remote branch: `origin/p0/home-noc-worktree-salvage-artifact-relay-mesh09-20260703t091408z`
- Local repair branch: `p0/home-noc-clickable-drilldown-repair-mesh16-20260703t094202z`

Plan:
1. Inspect the Home NOC frontend implementation and existing factory status contract.
2. Add URL/query-param backed drilldown state for fleet, servers/nodes, agents, queues, alerts, repairs, tasks, and Control Plane.
3. Convert metric cards, attention chips, topology rows, problem server rows, incident rows, active task rows, repair rows, and node rows into keyboard-focusable buttons.
4. Add cursor, accessible labels, focus-visible styling, and visible drilldown state.
5. Preserve the root summary-first layout for 100k+ servers by rendering capped summaries and paginated drilldowns only after search/filter selection.
6. Verify with focused tests, production build, and a browser click test.
