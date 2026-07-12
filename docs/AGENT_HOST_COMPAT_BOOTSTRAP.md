# Agent Host compatibility bootstrap

Status: owner-controlled transition contract. This document does not claim a
live worker rollout or `21/21` execution proof.

## Purpose

The existing worker entry point may predate immutable Agent Host re-exec and
task heartbeats that outlive the historical 60-second lease. That gap must be
closed once before the signed API-only runtime rollout can begin.

`ops/agent_host_compat_bootstrap.py` is intentionally node-local. It has no
SSH/SCP transport and cannot deploy itself. An approved operator stages the
public source bundle on each worker and invokes it locally as root, one
approved wave at a time.

The bootstrap updates only:

- `/usr/local/bin/kolibri-agent-host`;
- the digest-pinned Mimo response-only profile;
- Python modules imported by that bootstrap entry point;
- `kolibri-agent-host.service`.

It does not write Agent Host environment, runner-access declarations, mesh
membership, credentials, backend, Control Plane, release trust, or provider
state. Only `kolibri-agent-host.service` is restarted. Existing release-helper
trust remains a separate prerequisite; absence is reported as missing
`release_apply_v1`, never synthesized as success.

## Dynamic plan and canary

The plan reads the replicated membership manifest, removes semantic `home`,
and orders all current workers by the source-bundle digest plus durable node
ID. There is no host list, IP list, or rollout-stage label in source. Waves are
deterministic:

```text
1 → 2 → 3 → 5 → remaining workers
```

Read-only full plan:

```bash
python3 ops/agent_host_compat_bootstrap.py plan \
  --source-root "$PWD" \
  --manifest /var/lib/kolibri-mesh/peers.json \
  --minimum-workers 20
```

Read-only canary-only plan:

```bash
python3 ops/agent_host_compat_bootstrap.py plan \
  --source-root "$PWD" \
  --manifest /var/lib/kolibri-mesh/peers.json \
  --minimum-workers 20 \
  --canary-only
```

The reviewed `plan_digest` must be passed back when applying on the one local
node selected by that plan. Omitting `--apply` remains read-only:

```bash
python3 ops/agent_host_compat_bootstrap.py node \
  --source-root /root/staged-kolibri-source \
  --manifest /var/lib/kolibri-mesh/peers.json \
  --node-id DYNAMIC_NODE_FROM_PLAN \
  --run-id OWNER_APPROVED_RUN_ID \
  --approved-plan-digest sha256:REVIEWED_PLAN_DIGEST \
  --canary-only \
  --apply
```

Before mutation the node proves that its local interface owns the manifest IP.
Every replaced file is backed up with before-checksums. The three preserved
runtime inputs are hashed before/after. A failed checksum, service activation,
or stable `NRestarts` gate triggers automatic rollback.

Explicit rollback uses the same run and node identity:

```bash
python3 ops/agent_host_compat_bootstrap.py rollback \
  --source-root /root/staged-kolibri-source \
  --manifest /var/lib/kolibri-mesh/peers.json \
  --node-id DYNAMIC_NODE_FROM_PLAN \
  --run-id OWNER_APPROVED_RUN_ID \
  --approved-plan-digest sha256:REVIEWED_PLAN_DIGEST \
  --canary-only \
  --apply
```

## Long lease proof

The new Agent Host advertises `lease_heartbeat_probe`. The proof task runs for
65 seconds by default, sends repeated authoritative heartbeats, and completes
only with a matching attempt ID, positive fencing token, node/lease binding,
result reference, duration evidence and, when the deployed Control Plane
supports it, an independent `control-plane/home` verifier verdict.

```bash
python3 ops/agent_host_compat_bootstrap.py prove \
  --manifest /var/lib/kolibri-mesh/peers.json \
  --node-id DYNAMIC_NODE_FROM_PLAN \
  --campaign-id OWNER_APPROVED_CAMPAIGN \
  --duration-seconds 65
```

A wave advances only after this proof is `completed`, `release_apply_ready` is
true, membership still matches the approved plan, and no restart storm was
observed. After the compatibility barrier, all subsequent Agent Host changes
use the signed API-only rollout described in
`docs/AGENT_HOST_PROGRESSIVE_ROLLOUT.md`.
