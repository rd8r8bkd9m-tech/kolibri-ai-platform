# Result

Status: `completed_with_bounded_canary`

Node:

- execution node: `kolibri` server Agent Host lease, not local Mac
- target node: `qjns`
- qjns agent: `agent-host-qjns`
- qjns host: `kolibri-tools-executor`
- qjns health: `online`
- qjns freshness: `fresh`
- qjns heartbeat age at probe: `15` seconds
- qjns active task before probe: `null`
- qjns disk free at probe: `4868214784` bytes of `20109631488` bytes

Finding:

qjns GitHub noninteractive clone/auth is repaired enough for Agent Host review clone startup. The clone-phase canary was intentionally pointed at a missing branch. It failed after the clone phase at:

```text
git fetch origin __kolibri_probe_missing_ref_20260702_no_checkout__
```

The qjns task did not fail with the previous blocker:

```text
fatal: could not read Username for 'https://github.com': terminal prompts disabled
```

It also did not fail with `review_clone_auth_failed`.

Evidence:

- Control Plane health: `status=completed`, Redis `PONG`.
- qjns route: `status=ok`, target endpoint `/v1/nodes/qjns`, fallback nodes `home`, `main`, `new`, `primary-candidate`.
- qjns read-only probe:
  - task `P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_READONLY_HOST_PROBE`
  - state `completed`
  - result reference `/var/lib/kolibri-agent/artifacts/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_READONLY_HOST_PROBE/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_READONLY_HOST_PROBE-attempt-1/result.json`
- qjns clone-phase canary:
  - task `P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_CLONE_PHASE_CANARY`
  - leased to `qjns:agent-host-qjns`
  - attempt `1`
  - final state `failed`
  - error type `runtime_error`
  - error `command failed with rc=128: git fetch origin __kolibri_probe_missing_ref_20260702_no_checkout__`
  - result reference `/var/lib/kolibri-agent/artifacts/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_CLONE_PHASE_CANARY/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_CLONE_PHASE_CANARY-attempt-1/result.json`

Artifact caveat:

`/v1/agents/artifacts/{task_id}` listed the completed read-only probe artifact, but returned an empty `artifacts` list for the intentionally failed clone canary even though the task metadata includes `result_reference`. Treat this as an artifact listing gap for failed tasks, not a qjns clone/auth failure.

Blockers:

- None for qjns GitHub clone/auth at the clone phase.
- Direct SSH to qjns remains unavailable from this server path:
  - public aliases timed out
  - mesh IP returned public key/password denial
- This run did not prove full review checkout/tests because the canary intentionally stopped at a missing branch after clone.

Secrets:

- No secrets were printed.
- No environment dump was performed.
- No credential helper contents were printed.
- No interactive login was attempted.

Destructive actions:

- None.
- No force push.
- No push to `main`.
- No credential mutation.
