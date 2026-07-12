# Local model and FormulaLM admission policy

Status: tracked Home-first policy slice, not a deployment claim.

This policy separates two decisions that must never be inferred from a node
heartbeat or a provider response:

1. whether a node may run a particular local model;
2. whether sanitized execution material may enter FormulaLM learning.

The machine-readable contract is
`contracts/kolibri-os-v1/model-and-learning-policy.schema.json`. The fail-closed
Rust evaluator is `crates/kolibri-core/src/model_policy.rs`.

## Local model eligibility

A local LLM is schedulable on a node only when all six gates pass for that
exact model/runtime combination:

| Gate | Required proof |
| --- | --- |
| Memory | Available memory meets the model requirement. |
| Compute | CPU capacity passes for CPU models; GPU availability and VRAM pass for GPU-required models; CPU-or-GPU models may satisfy either declared path. |
| License | The model and runtime license decision is `permitted`. Restricted, negative and unknown decisions fail closed. |
| Disk | Available disk meets the model/runtime requirement and preserves the node safety reserve upstream. |
| Runtime | A live model-runtime invocation probe passed. Installed files or an open port are not enough. |
| Benchmark | The declared capability benchmark passed for this model/runtime/node. |

Every passed gate carries a canonical `sha256:<64 lowercase hex>` evidence
reference. A successful measurement without content-addressed evidence is a
failed eligibility gate. Eligibility does not install a model, start a service
or make the node schedulable by itself; node attestation, policy and canary task
gates still apply.

## FormulaLM admission

FormulaLM may admit only declared, permitted learning material:

- model outputs that policy and license allow;
- sanitized tool traces;
- code diffs;
- test results;
- independent verifier verdicts.

Admission rejects all of the following before candidate creation:

- foreign or proprietary model weights;
- provider-private chain-of-thought, hidden reasoning, system prompts or other
  inaccessible internals;
- secrets or credentials;
- PII without explicit, contractual or public-permitted consent;
- license-negative traces;
- material with restricted, negative or unknown license status.

Permitted outputs and safe work summaries are not private chain-of-thought.
They may be used only when provenance, consent, license, retention,
sanitization, quality and verifier gates also pass. FormulaLM does not copy
third-party weights, does not infer permission from API access, and does not
mutate production weights in the request path.

The admission report is evidence, not training. Dataset construction,
training/distillation, independent evaluation, canary promotion and signed
production release remain separate asynchronous, approval-gated stages.

## Verification

`crates/kolibri-core/tests/model_policy_contracts.rs` proves:

- every local-model resource, license, runtime and benchmark gate is required;
- GPU-required models cannot pass with CPU capacity alone;
- missing or malformed evidence fails closed;
- permitted outputs/tool traces/diffs/tests/verdicts can pass;
- weights, private reasoning, secrets, unconsented PII and license-negative
  traces are rejected;
- the JSON contract rejects fabricated `eligible=true` reports.
