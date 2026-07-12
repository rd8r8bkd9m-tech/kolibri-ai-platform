# Home Control Plane strict compatibility bootstrap

Status: one-time migration runbook. No production apply is claimed by this
document.

This bootstrap closes the verified legacy-split mismatch before the first
signed unified release. It is deliberately narrower than a release:

- authority is the local manifest member `home`;
- the launcher must already select `legacy-split-bootstrap`;
- the installed launcher, endpoint resolver and three import dependencies must
  byte-match the reviewed source;
- only `/usr/local/bin/kolibri-factory-control` may change;
- backend, frontend, credentials, mesh, Redis data and other units are out of
  scope;
- only `kolibri-factory-control.service` may restart.

The normal immutable signed release path remains
`docs/HOME_CONTROL_PLANE_SIGNED_RELEASE.md`. This compatibility bootstrap must
not become a general deploy mechanism.

The apply gate is intentionally closed until the Agent Runner/OpenAPI contract
freeze is reviewed. The plan binds the exact SHA-256 of the V1 OpenAPI, domain
schema and `ops/agent_host.py`; changing any of them invalidates both digests.

## 1. Dry-run plan

Run on Home as the operator against an exact clean commit:

```bash
python3 -B ops/home_control_plane_strict_compat_bootstrap.py \
  --source-root "$PWD" \
  --source-commit "$(git rev-parse HEAD)" \
  --manifest /var/lib/kolibri-mesh/peers.json \
  --run-id strict-compat-YYYYMMDDTHHMMSSZ \
  > /tmp/strict-compat-plan.json
```

The command is read-only by default. Review these fields:

- `target_node=home`;
- `changed_paths` contains exactly the Factory Control entrypoint;
- `restart_units` contains exactly the Factory Control service;
- `redis_before.lease_index_total=0`;
- source commit, membership digest, before/after SHA-256 and anchor SHA-256;
- `contract_freeze.status=candidate` and `contract_freeze.digest`; the owner
  binds that candidate only after the dedicated Agent Runner/OpenAPI contract
  tests pass;
- `plan_digest`.

Any active, expired or heartbeat-stale lease blocks the plan. Finish or recover
that work first; do not restart underneath an active attempt.

## 2. Digest-bound apply

The owner authorizes the exact reviewed plan by supplying its digest:

```bash
PLAN_DIGEST=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["plan_digest"])' \
  /tmp/strict-compat-plan.json)
CONTRACT_FREEZE_DIGEST=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["contract_freeze"]["digest"])' \
  /tmp/strict-compat-plan.json)

sudo python3 -B ops/home_control_plane_strict_compat_bootstrap.py \
  --source-root "$PWD" \
  --source-commit "$(git rev-parse HEAD)" \
  --manifest /var/lib/kolibri-mesh/peers.json \
  --run-id strict-compat-YYYYMMDDTHHMMSSZ \
  --expected-plan-digest "$PLAN_DIGEST" \
  --expected-contract-freeze-digest "$CONTRACT_FREEZE_DIGEST" \
  --apply
```

Apply recomputes the complete plan under a host lock. Any source, installed
file, membership or launcher change invalidates the digest and prevents a
restart. Do not run this command until the Agent Runner/OpenAPI freeze has a
reviewed commit and its dedicated compatibility suite is green.

Before installation, a separate loopback listener runs the candidate in
read-only mode and must pass strict health, canonical membership, fleet-proof
and Redis projection contracts. After the atomic file replacement, the helper
restarts only Factory Control and requires:

- strict live release identity and non-canary mode;
- unchanged task, queue and lease counts;
- unchanged systemd `NRestarts`;
- Redis `PONG`;
- canonical membership/fleet-proof digest.

On any post-install failure, the exact backed-up bytes, mode and ownership are
restored, the same single service is restarted, and the Redis projection is
checked again. Evidence is stored below
`/var/backups/kolibri/control-plane-strict-compat/<run-id>/` without secrets.

## 3. Execution proof after compatibility repair

The successful bootstrap proves only the Home Control Plane runtime contract.
It does not prove the factory. Submit one real API task and require all of:

- positive fencing token bound to the current attempt and lease owner;
- periodic task heartbeats longer than one lease window;
- non-empty result reference and content hash;
- completion evidence bound to the same attempt;
- independent verifier verdict;
- stale completion rejected after a forced worker-loss retry.

Only after that can the signed progressive Agent Host rollout and the 21-node
capability campaign begin.
