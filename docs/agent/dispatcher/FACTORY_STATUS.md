# Factory Status

Snapshot time:
- 2026-07-01T02:14:07Z

Mac executor:
- Hostname: `MacBook-Air-Vladislav.local`
- Kernel: `Darwin`
- Role: thin intelligent dispatcher only.

Control Plane:
- Default URL: `http://10.99.0.2:9101`
- Direct Mac health check: timeout after 5 seconds.
- Server-side check through `kolibri-primary-codex` to
  `http://10.99.0.2:9101/health`: `status=ok`, `redis=PONG`.
- `kolibri-primary-codex` local `127.0.0.1:9101` check failed; the active
  listener observed on that node is `10.99.0.10:9101`.
- Status: direct Mac route unavailable; fallback route through
  `kolibri-primary-codex` to mesh Control Plane is available.

Fabric law:
- API-first control is the primary management path.
- SSH is bootstrap, emergency recovery and diagnostics only.
- Agent responses must not dead-end at `server unavailable`; they must return a
  structured status with reason, fallback nodes, repair task and next action.
- Full owner control through API must be authenticated, authorized, scoped,
  logged, token-bound or signed, and protected from secret leakage.

Emergency SSH layer:
- Mac emergency-login topology probe checked 20 server aliases:
  `ok=20`, `fail=0`, `total=20`.
- This is a diagnostic/bootstrap layer only; normal control must move through
  Fabric API and fallback routing.

Submitted tasks:
- `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_06_30`: accepted by
  Control Plane at `2026-06-30T21:50:31Z`, state `queued`.
- Same task leased by `primary-candidate:agent-host-primary`, state `running`,
  heartbeat observed at `2026-06-30T21:51:23Z`.
- Latest observed heartbeat: `2026-06-30T21:54:24Z`; result fields are still
  empty.
- Latest exact task query observed heartbeat `2026-06-30T21:57:54Z`, state
  `running`, lease owner `primary-candidate:agent-host-primary`, result fields
  still empty.
- `P0_API_FIRST_FULL_CONTROL_FABRIC_2026_07_01`: accepted by Control Plane at
  `2026-06-30T23:15:13Z`; leased by
  `primary-candidate:agent-host-primary`; final Control Plane state `failed`
  at `2026-06-30T23:21:44Z` because required `docs/superfactory/*` files were
  missing. Artifact contains useful uncommitted implementation with remote test
  report `65 passed, 1 warning`; finalization task is required.
- `P0_API_FIRST_FULL_CONTROL_FABRIC_FINALIZE_2026_07_01`: accepted by Control
  Plane at `2026-06-30T23:26:24Z`; leased by
  `primary-candidate:agent-host-primary`; final Control Plane state `failed`
  because exact verifier filenames were missing, but it created draft PR #85
  and pushed branch head `44d7b9a`.
- `P0_API_FIRST_FULL_CONTROL_FABRIC_CONTRACT_ALIGN_2026_07_01`: accepted by
  Control Plane at `2026-06-30T23:38:28Z`; leased by
  `primary-candidate:agent-host-primary`; final Control Plane state `failed`
  because exact verifier filenames were still missing. Artifact contains useful
  docs-only commit evidence and remote tests `65 passed, 1 warning`.
- PR #85 was then synchronized through a thin-client relay of the server commit.
  GitHub source of truth now has branch
  `p0/api-first-full-control-fabric-2026-07-01` at
  `9690361f02addeff37771c52fd37878aef455e13`.
- GitHub API confirmed exact required files exist, including
  `docs/superfactory/API_FIRST_CONTROL_FABRIC.md` and
  `docs/agent/runs/2026-07-01-p0-api-first-full-control-fabric/RESULT.md`.
- GitHub Actions `Kolibri CI` run `28483527200` completed with conclusion
  `success`.
- `P0_REPAIR_QJNS_UIAP_DISK_2026_07_01`: Control Plane task state is `failed`
  because final verifier required missing `docs/agent/runs/.../RESULT.md`.
  Artifact stdout shows effective repair succeeded and current Control Plane
  cards confirm free disk on both nodes.
- `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_07_01`: submitted at
  `2026-07-01T02:12:34Z`; leased by `primary-candidate:agent-host-primary`;
  latest state `running` at `2026-07-01T02:13:40Z`. This finalizer preserves
  PR #83 and fixes the prior verifier path by requiring `python3` and exact
  run artifacts.

Node snapshot through Control Plane:
- Observed node cards: 42.
- Canonical nodes: 20.
- Fresh canonical nodes: 19.
- Fresh canonical generic implementation nodes: 7.
- Healthy owner-relevant execution nodes include `home`, `home-live`, `main`,
  `mesh-9fts`, `primary-candidate`, and mesh `agent-01..03` cards with
  implementation capability.
- `qjns`: online; current free disk observed `10970157056` bytes.
- `uiap`: online; current free disk observed `27758845952` bytes; RAM is tight
  (`MemAvailable` observed around `126788 kB`), so use for research/RAG only
  until resource pressure is reviewed.
- `main`: online; current free disk observed `7614488576` bytes; known
  Codex/MIMO runner auth is broken from prior task attempts.
- `primary-candidate`: online and currently running
  `P0_AGENT_HOST_GENERIC_RUNNER_CONTRACT_HARDENING_2026_07_01`.
- Many mesh cards are degraded/stale or metadata-only; they need inventory
  before broad execution.
- Aggregate `/v1/tasks` response showed 200 queued tasks while the direct P0
  endpoint showed `running`; treat aggregate queue status as stale/limited and
  use the direct task endpoint for P0 truth.

Known constraints:
- Do not run product implementation on Mac.
- Do not run heavy tests on Mac.
- Do not claim remote execution without task status/artifacts.
- Do not expose secrets.
- Use API-first paths for normal control. Use SSH only for bootstrap,
  emergency recovery and diagnostics.

Current blockers:
- Agent Host generic runner/verifier contract is too weak: useful work can be
  pushed while task state still becomes `failed` due exact artifact filename
  mismatches.
- Server shell GitHub write path on `primary-candidate` is not reliable:
  GitHub SSH port 22 timed out and SSH over port 443 authenticated with a
  read-only key. Mac had to relay the server commit to GitHub over HTTPS.
- `main` still has Codex/MIMO runner auth failures from prior attempts.

Known fleet notes from current owner context:
- Owner-facing server set is 20 servers; latest emergency SSH probe reached
  all 20.
- Control Plane currently exposes 42 node cards because it includes mesh,
  stale and metadata cards in addition to the owner-facing server set.
- `qjns` and `uiap` disk pressure was effectively repaired, but retention
  cleanup and GitHub auth validation are still follow-up tasks.
