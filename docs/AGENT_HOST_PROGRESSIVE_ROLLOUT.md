# Agent Host: signed progressive runtime rollout

Status: source/runbook contract, 2026-07-11. This document does **not** claim a
live fleet rollout, a strict Control Plane switch, or 21/21 runtime proof.

## What is reused

- `ops/release_bundle_builder.py` produces the canonical bounded bundle and
  detached `sshsig`.
- `ops/release_controller.py` supplies Home-only API transport, owner approval
  binding, fenced release/rollback tasks, release health and cancellation.
- `ops/release_installer.py` and the privileged release helper independently
  verify the signature, manifest and payload, switch the immutable `current`
  link, run local health policy and restore the prior link on failure.
- `ops/agent_host.py` supplies the existing `read_only_probe` runner result.
- `ops/agent_host_release_rollout.py` adds only the runtime-specific dynamic
  wave plan and two-phase completion gates.

Neither the rollout controller nor a worker opens SSH. Every release,
rollback, and proof is a Control Plane task with a lease and evidence record.

## Compatibility barrier (must not be hidden)

The legacy unit starts `/usr/local/bin/kolibri-agent-host`, while the release
installer switches `/opt/kolibri-ai/current`. The installer correctly forbids
restarting `kolibri-agent-host.service` while that process owns the release
lease. Therefore a legacy process cannot, by its old behavior alone, prove that
the new `ops/agent_host.py` is running.

The current source closes that gap as follows:

1. `/usr/local/bin/kolibri-agent-host` remains a bootstrap/fallback runtime.
2. At process start it validates the root-managed `current` target, canonical
   manifest, `ops/agent_host.py` digest and the digest-pinned
   `ops/mimo/kolibri-response-only.md` profile, then re-execs that immutable
   file. A historical product-only manifest containing neither runtime record
   is the sole migration fallback: it keeps the bootstrap process and never
   executes unmanifested bytes. Declaring only one half of the runtime/profile
   pair fails closed.
3. The installer emits signed-manifest-derived `agent_host_runtime` activation
   evidence when the payload contains `ops/agent_host.py`.
4. Only after the release task's completion POST succeeds does Agent Host exit.
   The existing `Restart=always` supervisor starts the bootstrap entry point,
   which enters the new release. It cannot lease another task on stale code.
5. A targeted probe must report that exact release ID, manifest digest and
   both runtime/profile digests before the wave advances.

Existing machines whose bootstrap binary predates this behavior need one
explicit, owner-controlled compatibility bootstrap before the first runtime
campaign. That transition is not silently represented as an API-only release
and is not claimed complete by this change. Newly provisioned nodes receive the
bootstrap behavior from the normal canonical installer. After the barrier is
met, all routine Agent Host updates and rollbacks use API tasks only.

## Dynamic membership and waves

The campaign reads both of these Home views:

- `GET /v1/nodes?scope=active&limit=250` — canonical mesh membership and live
  Agent Host readiness;
- `GET /v1/fleet/nodes` — semantic `control_plane` versus worker role.

The sets must match. The controller does not contain a server list and ignores
legacy per-node `rollout_stage` labels. It requires one semantic Control Plane,
fresh Agent Hosts, `release_apply_v1`, and `read_only_probe` on every member.

For 21 nodes the deterministic waves are `1 + 2 + 3 + 5 + 9 + 1`; for 22 they
are `1 + 2 + 3 + 5 + 10 + 1`. The final `1` is the semantic Control Plane role.
Any larger fleet is absorbed by `workers-rest`. A declared failure domain is
used to diversify the quorum; otherwise a release-digest/physical-ID hash
provides stable selection. No hostname is selected in source.

`--minimum-nodes 21` means 21 or more, not an exact static count. Membership is
re-read before every wave and at the final gate. A join, removal, identity
replacement, or role change invalidates the approved plan: mutation campaigns
rollback, proof-only campaigns stop, and the owner must sign a fresh plan.

## Why completion proof has two campaigns

A Control Plane that has not yet enabled the strict verifier cannot emit an
independent strict verdict. Requiring that verdict before its own switch would
be circular; synthesizing one in the rollout controller would be fake proof.

### Phase A — `pre_switch`

After every release wave, a new targeted `read_only_probe` campaign validates
the raw API task/result binding:

- task ID and attempt ID;
- leased node and leased agent;
- `status=completed`;
- non-empty `result_reference` equal to the runner's `result_path`;
- release-bound Agent Host release ID, canonical manifest digest, runtime path
  and runtime SHA-256;
- release-bound response-only Mimo profile path and SHA-256.

This phase explicitly records `control_plane_verifier=not_required_pre_switch`
and `strict_completion_proven=false`. It proves compatibility of the new Agent
Host payload but can never satisfy the final fleet criterion.

### Strict Control Plane canary barrier

Only after Phase A covers the full, unchanged membership may the independently
signed strict Control Plane release be applied to the canonical Home canary.
That release uses its own owner approval and rollback bundle. Its release gate
must show that completion evidence and the independent Home verifier are being
persisted; a process heartbeat is not sufficient.

If the Control Plane canary fails, roll it back before any final Agent Host
claim. Do not reuse Phase A task IDs after the switch.

### Phase B — `strict`

A new campaign ID creates new task attempts on the same dynamic wave plan. In
addition to every raw check above, each stored task must contain:

- `kolibri.task-completion-evidence.v1`;
- `kolibri.control-plane-completion-verifier.v1` from
  `control-plane/home`, marked independent with `verdict=passed`;
- all verifier checks equal to `true` and no failed checks;
- a recomputed canonical result SHA-256;
- a recomputed task/attempt/lease/reference binding SHA-256.

The controller reads these records from Home. It never writes or fabricates a
verifier. Only Phase B can return `strict_completion_proven=true`.

## Offline build and plan

First ensure the signed bundle includes both `ops/agent_host.py` and
`ops/mimo/kolibri-response-only.md` (plus the compatible runtime dependencies
selected for that release). The installer rejects an Agent Host payload that
omits the profile. The builder is read-only unless both build and signing
options are supplied; see
`docs/RELEASE_BUNDLE_BUILDER.md`.

Example read-only dynamic plan after a bundle has been signed:

```bash
python3 ops/agent_host_release_rollout.py plan \
  --manifest /secure/release/manifest.json \
  --signature /secure/release/manifest.sig \
  --allowed-signers /secure/release/allowed_signers \
  --signer-identity owner \
  --minimum-nodes 21
```

Review the returned membership fingerprint and every wave. The owner approval
must bind the exact signed manifest, rollback manifest and canonical rollout
plan before mutation is attempted.

## Phase A apply and rollback

After approval (example only; not run by this change):

```bash
python3 ops/agent_host_release_rollout.py apply-pre-switch \
  --manifest /secure/release/manifest.json \
  --signature /secure/release/manifest.sig \
  --rollback-manifest /secure/known-good/manifest.json \
  --rollback-signature /secure/known-good/manifest.sig \
  --allowed-signers /secure/release/allowed_signers \
  --signer-identity owner \
  --approval-id OWNER_APPROVAL_ID \
  --campaign-id agent-host-v2-pre-001 \
  --minimum-nodes 21
```

The first failed release health, runtime re-entry, raw result binding, or
membership check causes the controller to:

1. cancel and fence all still-active release/probe attempts;
2. submit the owner-authorized known-good rollback in reverse attempted order;
3. require known-good release health;
4. require a fresh release-bound raw handshake after each rollback.

`rolled_back` is not success. `rollback_failed` and `rollback_blocked` require
operator incident handling; they must not be converted to completed.

## Phase B strict verification

After the separate strict Control Plane canary succeeds, use a different
campaign ID:

```bash
python3 ops/agent_host_release_rollout.py verify-strict \
  --manifest /secure/release/manifest.json \
  --signature /secure/release/manifest.sig \
  --allowed-signers /secure/release/allowed_signers \
  --signer-identity owner \
  --campaign-id agent-host-v2-strict-001 \
  --minimum-nodes 21
```

The final evidence is valid only when:

- command status is `completed`;
- `strict_completion_proven=true`;
- the final dynamic membership fingerprint equals the approved snapshot;
- every current member occurs exactly once and has a strict proof;
- the reported count is `N/N`, where `N` is the current dynamic membership
  (21/21, 22/22, or larger), never a hard-coded display value.

## New-node behavior

A newly enrolled physical node receives the same bootstrap runtime, release
helper, digest-pinned Mimo response profile, local signer trust and health
policy through the canonical provisioning contract. Once it is present in
replicated mesh membership and advertises both required capabilities, the next
plan includes it automatically. If it appears during a signed campaign,
snapshot drift deliberately stops that campaign so the owner can approve a new
plan containing the node.

## Provider process fences

Every subprocess is placed in its own process group. The Agent Host applies
`constraints.max_wall_seconds` to the complete task attempt, not independently
to each command. While the process runs, it polls the authoritative task
heartbeat at most every two seconds. A deadline, owner cancellation, terminal
task state, lease-fence loss, or Agent Host stop sends `SIGTERM` to the whole
group and then bounded `SIGKILL` if needed. Timeout and cancellation are
reported as non-retryable typed failures (`provider_timeout` and
`task_cancelled`), so a late process cannot publish after its lease was fenced.

For read-only Mimo tasks, the worktree receives only the signed
`kolibri-response-only` agent profile. The invocation uses `--pure --agent
kolibri-response-only`; `tool_allowlist` is empty, all known tools are also
permission-denied for compatibility, and wildcard permissions are denied. A
structured tool event is a non-retryable policy violation. Its
raw command arguments and provider payload are withheld from result and logs.

The older write-capable direct Mimo path is kept as a separate compatibility
runner for non-provider implementation tasks. Its evidence now says exactly
that it uses argv transport, no sandbox and the permission-bypass CLI contract;
it does not advertise the Home factory provider contract. Production provider
responses and chat/orchestrator response kinds never enter that path.

## Local source verification performed for this change

```text
43 passed: focused Mimo response-only, process fencing and Agent Host rollout tests
256 passed: broad Agent Host, provider scheduling, release and Home-only contract regressions
python py_compile: passed
bash syntax validation: passed
git diff --check: passed
MiMoCode 0.1.4 `--pure agent list`: parsed `kolibri-response-only` as a primary agent
```

These are local source tests, not production evidence.
