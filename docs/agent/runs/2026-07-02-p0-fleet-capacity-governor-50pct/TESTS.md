# Tests

Task: `P0_FLEET_CAPACITY_GOVERNOR_50PCT_2026_07_02`

Verification commands:

```bash
hostname
date -u +%Y-%m-%dT%H:%M:%SZ
git status --short
test -f docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/CAPACITY_GOVERNOR_50PCT.md
test -f docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/PLAN.md
test -f docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/ACTIONS.md
test -f docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/TESTS.md
test -f docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/RESULT.md
test -f docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct/NEXT.md
rg -n "P0_FLEET_CAPACITY_GOVERNOR_50PCT_2026_07_02|Temporary Fleet Capacity Governor|Overload Stop Conditions" docs/agent/runs/2026-07-02-p0-fleet-capacity-governor-50pct
```

Expected result: all file-existence checks pass and `rg` finds the task record,
governor title, and stop-condition section.

