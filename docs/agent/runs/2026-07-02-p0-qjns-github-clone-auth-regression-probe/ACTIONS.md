# Actions

- Confirmed server execution context:
  - `hostname`: `kolibri`
  - kernel: Linux server host
  - worktree: `/var/lib/kolibri-agent/logical-workers/mesh-agent-14/worktrees/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02-attempt-1/repo`
  - branch: `agent/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02/generic`

- Queried Control Plane at `http://10.99.0.10:9101`:
  - `/v1/health` returned `status=completed`, Redis `PONG`.
  - `/v1/nodes` returned qjns as online/fresh.
  - `/v1/fleet/route?target_node=qjns&required_capability=review` returned route status `ok`.

- Ran local command-node GitHub reachability probes without printing secrets:
  - SSH `git ls-remote --heads git@github.com:rd8r8bkd9m-tech/kolibri-ai-platform.git main` returned `rc=0`.
  - HTTPS `git ls-remote --heads https://github.com/rd8r8bkd9m-tech/kolibri-ai-platform.git main` returned `rc=0`.
  - These prove command-node GitHub access only; they are not counted as qjns proof.

- Checked noninteractive SSH paths to qjns from the server:
  - `qjns` and `kolibri-qjns` public aliases timed out on port 22.
  - `10.99.0.4` returned public key/password denial.
  - No SSH repair was attempted.

- Dispatched qjns read-only Agent Host probe:
  - task: `P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_READONLY_HOST_PROBE`
  - target: `qjns`
  - state: `completed`
  - result reference: `/var/lib/kolibri-agent/artifacts/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_READONLY_HOST_PROBE/P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_READONLY_HOST_PROBE-attempt-1/result.json`

- Dispatched qjns clone-phase canary:
  - task: `P0_QJNS_GITHUB_CLONE_AUTH_REGRESSION_PROBE_2026_07_02_CLONE_PHASE_CANARY`
  - target: `qjns`
  - kind: `review_pr`
  - branch: `__kolibri_probe_missing_ref_20260702_no_checkout__`
  - state: `failed`, by design
  - error type: `runtime_error`
  - error excerpt: `command failed with rc=128: git fetch origin __kolibri_probe_missing_ref_20260702_no_checkout__`
  - interpretation: qjns got past `git clone`; clone/auth is repaired enough for noninteractive repository clone.
