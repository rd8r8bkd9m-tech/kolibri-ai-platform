# P0 Home NOC Worktree Salvage Artifact Relay

Task: `P0_HOME_NOC_WORKTREE_SALVAGE_ARTIFACT_RELAY_MESH09_20260703T091408Z`

Plan:

1. Inspect the failed mesh-04 worktree and result artifact instead of restarting from zero.
2. Preserve the implemented Home NOC UI/API work from branch `p0/home-noc-control-center-relay-repair-20260703`.
3. Clone the salvaged branch into the empty mesh-09 worktree.
4. Verify the Home surface remains the Kolibri AI Control Center server NOC, with aggregate topology and compact incident/action views.
5. Create the exact required run artifacts for this mesh-09 task in both the repository run directory and the external worker artifact directory.
6. Push a non-main salvage branch without force pushing.
