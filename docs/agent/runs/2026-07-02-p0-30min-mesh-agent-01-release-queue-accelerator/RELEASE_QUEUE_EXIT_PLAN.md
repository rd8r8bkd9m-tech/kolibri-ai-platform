# Release Queue Exit Plan

Decision: `exit_ready_with_metadata_follow_up`

The P0 release queue is reduced to two concrete lanes:

| Lane | Status | Action |
| --- | --- | --- |
| Factory Control runtime | passed | Keep deployed runtime under normal canary monitoring. |
| Telegram gateway | owner diagnostic required | Run no-mutation ownership/startup diagnostic before any receiver or Bot API change. |
| Merged July 1 PR refs | non-blocking | Treat #83/#85/#88/#89/#91/#92/#95/#96/#97/#98 pull refs as stale-visible unless live metadata contradicts dispatcher evidence. |
| New priority refs #100-#104 | metadata-required | Recheck with authenticated GitHub metadata before owner mark-ready/merge/close decisions. |
| Legacy refs | backlog | Groom outside P0 unless a current release blocker is proven. |

Operational rule:

`git ls-remote` visibility is enough to prove a ref exists. It is not enough to
prove a PR is open, draft, mergeable, approved, green, closed, or merged.

P0 exit condition met by this accelerator:

- Runtime canary passed for Factory Control.
- Remaining Telegram work is isolated to an explicit safe diagnostic.
- PR queue blocker is no longer ambiguous: metadata-required refs are separated
  from already merged/superseded refs.
- No unsafe owner action was automated.
