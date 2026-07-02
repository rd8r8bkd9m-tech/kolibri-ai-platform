# Tests

Verification commands run from the dispatcher:

```bash
python3 -m json.tool docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_2026_07_02.json >/dev/null
python3 -m json.tool docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_REMOTE_PROBE_2026_07_02.json >/dev/null
python3 ops/kolibri-dispatch submit --file docs/agent/dispatcher/envelopes/P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_REMOTE_PROBE_2026_07_02.json
python3 ops/kolibri-dispatch status P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_REMOTE_PROBE_2026_07_02
python3 ops/kolibri-dispatch collect P0_AUTOPILOT_EXTRA_30_HOSTVDS_AGENT_08_READINESS_REMOTE_PROBE_2026_07_02
python3 -m json.tool docs/agent/runs/2026-07-02-p0-hostvds-agent-08-readiness-remote-probe/REMOTE_RESULT.json >/dev/null
git status --short
```

Remote task verifier status: failed on missing exact `PLAN.md` in the remote worktree, but produced useful sanitized readiness evidence and a remote result reference.

