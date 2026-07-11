# Codex service-account readiness and OpenAI-compatible routing

Status: implementation contract. This document is not deployment evidence.

## One public AI protocol

Kolibri clients use the OpenAI-compatible surface. `POST /v1/responses` is the
canonical route, while `POST /v1/chat/completions` remains a compatibility
adapter and `GET /v1/models` exposes the public model `kolibri`. The Shell must
not call Codex, Mimo, or a node-specific endpoint directly. The Home Control
Plane resolves the provider and preserves the requested runner in the factory
task contract.

This keeps provider replacement internal: adding a runner changes routing and
readiness state, not the client protocol.

## Non-secret access declaration

Every dynamic mesh member receives `/etc/kolibri/runner-access.json`, validated
by `ops/runner_access.py`. The replicated declaration contains only:

- Home as the sole control authority;
- `dynamic-membership` as the node selector;
- a browser/device authorization flow for the `kolibri-agent` service user, or
  an allowlisted Home/Mac runner-broker reference;
- a bounded `gpt-5.5`, read-only readiness probe.

Raw tokens, API keys, passwords, cookies, HTTP endpoints, private keys,
Codex auth-file paths, and unknown manifest fields are rejected. A broker
declaration is not execution proof; it remains unschedulable until a live
broker attestation exists.

## Service-user authorization

Authorization is completed interactively with the Codex browser/device flow
as the target node's `kolibri-agent` identity. It is not converted into an API
key and is not copied between Home, Mac, or workers. In particular,
`~/.codex/auth.json` must never be read, archived, logged, transported, or
placed in a release artifact.

The owner controls the interactive authorization session. The fleet rollout
installs only the non-secret declaration; it does not manufacture a successful
login claim.

## Capability gate

Agent Host removes all configured `runner:*` capabilities and reconstructs
them from live evidence. `runner:codex` is advertised only when both checks
pass for the service user:

1. `codex login status` reports an authenticated session.
2. A real bounded Codex invocation with model `gpt-5.5` and sandbox
   `read-only` returns the exact readiness marker.

The same model is pinned explicitly on every real Codex task command; runtime
configuration cannot silently replace it with a model unsupported by the
installed CLI. Read-only tasks also use ephemeral execution, ignore local user
configuration/rules, disable colour, and transport the prompt on stdin.

The marker is sent on stdin and the response is reduced to a SHA-256 digest in
readiness evidence. Customer prompts, provider output, credentials, and auth
files are not stored in that evidence.

A 401 blocks the exact Codex runner as `runner_auth_failed`. A 403 blocks it as
`runner_access_denied`. The capability is withdrawn immediately and is not
restored merely because the binary still exists. A later explicit readiness
probe must pass before the runner can be scheduled again.

A provider response that requires a newer Codex version is classified as
`provider_runner_outdated`, not as an authentication failure. The runner is
withdrawn until its CLI is upgraded and readiness passes again. Likewise, a
runner set to `disabled` in the manifest never advertises a capability even if
its binary or a legacy static capability remains on disk.

## Runner binding

Every runner task records `requested_runner`. Agent Host finalization records
`runner`, verifies the binding, and blocks a mismatch. Home rejects `/complete`
and `/fail` with HTTP 409 when the result omits the requested runner or names a
different one. This prevents a fallback result from being attributed to the
wrong provider and quarantines only the runner that actually failed.

## Dynamic Home-only rollout gates

The systemd unit, new-node provisioner, and controlled Home-only rollout install
the same validator and declaration on every manifest member. Enrollment is
driven by the replicated mesh manifest, not a static endpoint list.

For an authorized rollout, evidence must be collected in this order:

1. Validate the signed release and non-secret runner-access declaration.
2. Apply to one manifest-selected canary.
3. Confirm Home registration and a readiness record matching
   `contracts/codex-runner-readiness.schema.json`.
4. Progress through the remaining dynamic membership only after the canary
   passes; never copy an authorization file to make a node appear ready.
5. Run a real OpenAI-compatible `/v1/responses` task bound to Codex on every
   node that advertises `runner:codex` and verify the returned runner binding.

Nodes that have not completed device authorization remain healthy factory
members but must not advertise Codex. No 21/21 availability claim is valid
until all 21 evidence records and real response tasks pass.
