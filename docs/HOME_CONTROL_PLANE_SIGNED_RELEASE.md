# Signed immutable Home Control Plane release

Status: source runbook. This implementation did **not** apply a production
release while it was developed or tested.

This is the canonical release path for the Home backend, frontend, Agent Host
and Factory Control Plane. They share `/opt/kolibri-ai/current`, so an ops-only
or partial backend bundle is rejected before activation.

## Safety and authority contract

- Home is selected from the replicated mesh manifest; no hostname or IP is a
  durable authority.
- Planning is the default. Only explicit `--apply` submits a task.
- The detached OpenSSH signature and owner approval attestation bind the
  canonical manifest, Home-only rollout plan and signed rollback release.
- SSH is allowed only for the one-time protected authority bootstrap and
  immutable artifact staging. It is never a release execution transport.
- The worker independently verifies signature, approval, archive safety,
  every file hash/mode and the required unified payload profile.
- A candidate listener runs on a temporary loopback port with all HTTP POST
  and Redis mutation commands disabled. It must pass health, canonical dynamic
  membership and fleet-proof contracts before `current` can move.
- Activation is one atomic symlink replacement followed by fixed systemd
  `try-restart` actions. Failed restart or post-switch smoke restores the
  previous direct-child release and checks it again.
- The first owner-signed rollback may contain the exact legacy Control Plane,
  whose health contract predates release identity/read-only fields. Only a
  rollback task may accept those fields as absent, and evidence records
  `compatibility_mode=legacy-rollback-contract` from the dedicated canary exit
  code; an apply candidate never receives this compatibility exception.

## 1. One-time Home authority bridge

Run the bootstrap without `--apply` first. The plan performs only manifest,
Home identity, trust digest and managed-path preflight.

```bash
scripts/bootstrap-home-release-authority.sh \
  --manifest "$HOME/.kolibri-mesh/peers.json" \
  --signer-public-key "$KOLIBRI_RELEASE_SIGNING_PUBLIC_KEY" \
  --signer-identity "$KOLIBRI_RELEASE_SIGNER_ID"
```

After reviewing the plan, the owner may repeat with a unique `--run-id` and
`--apply`. This installs public trust, the fixed release helper, canary,
Home-only launcher and reversible systemd drop-in. It does not move `current`
or restart Factory Control.

The launcher is migration-safe: before the first complete unified release it
uses the exact legacy bootstrap root; after `current` contains the verified
Control Plane closure it selects only that immutable direct child.

## 2. Build a unified signed candidate

Use a clean committed source snapshot and a built `frontend/dist`. Add the
fixed runtime closure explicitly:

```bash
python3 ops/release_bundle_builder.py \
  --root "$SOURCE_ROOT" \
  --release-id "$RELEASE_ID" \
  --source-commit "$SOURCE_COMMIT" \
  --artifact-uri "artifact://bundles/$RELEASE_ID.tar.gz" \
  --output "$RELEASE_BUNDLE" \
  --runtime-path RELEASE_ID \
  --runtime-path ops/agent_host.py \
  --runtime-path ops/control_plane_endpoint.py \
  --runtime-path ops/factory_control.py \
  --runtime-path ops/fleet_membership.py \
  --runtime-path ops/mimo/kolibri-response-only.md \
  --runtime-path ops/release_authority.py \
  --runtime-path ops/release_helper.py \
  --runtime-path ops/release_installer.py \
  --runtime-path ops/runner_access.py \
  --runtime-path ops/telegram_superfactory.py \
  --build --sign \
  --signer-identity "$KOLIBRI_RELEASE_SIGNER_ID" \
  --signing-key "$KOLIBRI_RELEASE_SIGNING_KEY"
```

Require `self_verified=true`. Extract the canonical manifest and detached
signature using the fixed extraction procedure in
`docs/SIGNED_HOME_RELEASE_CANARY.md`; never reconstruct the manifest.

Build the rollback bundle first. If `current` is already unified, snapshot
that exact immutable release. For the first migration only, the known-good
runtime may still be split: product bytes are under the current immutable
release while Factory Control and Agent Host run from their bootstrap roots.
In that case create one private baseline snapshot containing those exact
currently effective bytes under the unified paths above, record their source
paths and SHA-256 digests, add a matching `RELEASE_ID`, and commit the snapshot
only for provenance before signing it. Do not substitute a newer checkout.
The resulting rollback release must pass the same full-profile validator; this
turns the split known-good state into an immutable rollback target. After the
first successful switch, all rollback bundles are direct snapshots of a prior
unified release.

## 3. Stage without activation

Both invocations default to plan. Repeat with `--apply` only after checking the
digest and collision result:

```bash
scripts/stage-home-release-bundle.sh \
  --manifest "$HOME/.kolibri-mesh/peers.json" --bundle "$ROLLBACK_BUNDLE"
scripts/stage-home-release-bundle.sh \
  --manifest "$HOME/.kolibri-mesh/peers.json" --bundle "$RELEASE_BUNDLE"
```

Staging writes immutable artifact bytes only; it cannot restart a service or
change `current`.

## 4. Plan and approve the exact Home wave

`home_control_plane_release.py` always selects exactly the manifest Home.
`--expected-nodes` is an optional observation gate, not a static membership
list; omit it when automatic mesh growth is intended.

```bash
python3 ops/home_control_plane_release.py \
  --manifest "$CONTROL_ROOT/current/manifest.json" \
  --mesh-manifest "$HOME/.kolibri-mesh/peers.json" \
  --control-url "$HOME_URL" >"$CONTROL_ROOT/home-plan.json"
```

Create and submit the short-lived owner approval with
`ops/release_approval.py`, binding:

- the candidate manifest digest and signer;
- the signed rollback manifest and signer;
- the exact `home-canary` rollout plan;
- expiry and a unique nonce.

Do not proceed unless the approval API returns the same digest and an owner
decision of `approved`.

## 5. One controlled API apply

```bash
python3 ops/home_control_plane_release.py \
  --manifest "$CONTROL_ROOT/current/manifest.json" \
  --signature "$CONTROL_ROOT/current/manifest.sig" \
  --rollback-manifest "$CONTROL_ROOT/rollback/manifest.json" \
  --rollback-signature "$CONTROL_ROOT/rollback/manifest.sig" \
  --allowed-signers "$CONTROL_ROOT/allowed_signers" \
  --signer-identity "$KOLIBRI_RELEASE_SIGNER_ID" \
  --approval-id "$APPROVAL_ID" \
  --mesh-manifest "$HOME/.kolibri-mesh/peers.json" \
  --control-url "$HOME_URL" \
  --apply
```

The only successful terminal result is `status=completed`. During self-restart
the controller may temporarily lose the loopback/API connection; polling must
resume until the fenced task reaches a terminal state. Any candidate,
systemd, backend, membership, fleet-proof or release-identity failure triggers
the signed rollback path.

## 6. Evidence gate

Retain, without secrets:

1. source commit, release ID, manifest digest and signature identity;
2. owner approval ID, attestation digest, expiry and bound rollout plan;
3. release task/attempt/lease IDs and worker completion verifier;
4. `health_checks.pre`, `health_checks.candidate` and
   `health_checks.post` results;
5. active and previous release IDs plus rollback status;
6. `/v1/health` active release ID;
7. `/v1/nodes?scope=active&limit=250` membership digest/count;
8. `/v1/runtime/fleet-proof` schema, matching digest/count and queue summary;
9. backend `/api/health` and public Shell/API smoke;
10. a fresh capability campaign only after the release task is terminal.

Do not claim fleet or product readiness from the signed switch alone. The
21/21 (or later 22+) execution campaign, public backend, provider answer and
browser evidence remain separate readiness gates.
