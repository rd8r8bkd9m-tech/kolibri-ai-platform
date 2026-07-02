# Token Window Budget Policy

Snapshot: 2026-07-02

## Rule

The director treats each 5-hour model-token window as 100% of the available
local reasoning budget. The local Mac/Codex session must not burn the whole
window on work that remote agents can do.

When exact platform quota counters are not exposed, the director uses the
available thread token counter, elapsed time, rate-limit signals and manual
checkpoints as the control signal.

## Budget Bands

Green: 0-60%

- normal planning and verification;
- remote task dispatch remains preferred;
- local code reading is allowed when it materially improves decisions.

Yellow: 60-80%

- summarize current state;
- avoid broad local exploration;
- delegate implementation and long verification to remote agents;
- keep only decision-making and integration local.

Orange: 80-90%

- stop non-P0 work;
- create/update checkpoint artifacts;
- submit remote continuation tasks;
- ask owner only for decisions that block P0 progress.

Red: 90-100%

- preserve state immediately;
- hand off all runnable work to remote Control Plane/MIMO;
- continue locally only for owner communication, emergency rollback or minimal
  dispatcher repair;
- do not start large local reads, refactors or UI investigations.

## 5-Hour Window State

Owner-facing status should show:

- current 5-hour window start and estimated reset time;
- percent used;
- remaining safe local work band;
- active remote tasks;
- pending owner approvals;
- latest checkpoint artifact.

## Checkpoint Contract

At Yellow or higher, the director keeps a concise checkpoint:

- current objective;
- completed actions;
- active blockers;
- remote tasks submitted;
- files/branches touched;
- next three decisions.

At Red, this checkpoint becomes mandatory before any non-emergency work.

## Remote-First Token Conservation

When token pressure rises, the director must:

- stop duplicating remote-agent analysis locally;
- ask remote agents for short structured artifacts;
- prefer API status and targeted tests over wide log reads;
- avoid launching local subagents except for Mac-local inspection;
- route development to remote MIMO/Codex agents with scoped context grants.

