# FormulaLM: signed estimate local-candidate foundation

This module prepares provenance-first candidate views of Russian construction
estimate **structures**. It is an integrity and evaluation boundary. It is not
a claim that 10,000 estimates have been collected, not proof of an independent
legal review, not authorization to train, and not a production training or
model-promotion pipeline.

Every generated bundle has the fixed state:

```text
unapproved_local_candidate
training_authorized=false
```

Every artifact, including `splits/*.learning.jsonl`, is marked
`training_eligible=false`. No command-line approval ID can change that state.

## Integrity and authorization are separate

The candidate manifest is canonical JSON and is signed with OpenSSH `sshsig`.
Production policy fixes all verification inputs in code:

```text
trust root: /etc/kolibri/trust/formulalm-estimate-corpus-candidate.allowed_signers
identity:   kolibri-formulalm-estimate-corpus-candidate
namespace:  kolibri-formulalm-estimate-corpus-candidate-v1
```

The allowed-signers file must be an absolute regular file, root-owned, and not
group/world writable. The trust-root path, identity and namespace are not CLI
arguments. A caller cannot provide an attacker-controlled trust root.

The signature proves only that the pinned candidate builder produced the exact
manifest bytes. It does **not** mean:

- a data owner approved the snapshot;
- a lawyer confirmed the asserted licence;
- FormulaLM training was approved;
- a training budget or provider was approved;
- a model was trained, evaluated, promoted or deployed.

Training remains forbidden until a future, separately signed data-and-training
approval contract binds the exact candidate ID, manifest SHA-256, content root,
scope, retention, budget and model purpose. That promotion contract is not
implemented here.

## Candidate record gates

The module accepts only records declaring one of these source/rights bases:

- open data with an identified licence and licence URL;
- a public official factual record with a recorded rights review;
- user-provided data with a consent ID and timestamp.

Records must declare FormulaLM estimate training/evaluation uses, no PII, no
secrets and no private reasoning. Paid/private sources, missing declarations,
browser sessions, credentials, prompts and secret-like values are rejected.
These are structured policy assertions, not independent legal proof.

The CLI performs no crawling, scraping, authentication or network fetching.
It consumes one local JSONL byte snapshot. The signed manifest binds:

- exact input snapshot SHA-256, size and record count;
- normalized record hashes and a record-set SHA-256;
- every artifact path, SHA-256, size and record count;
- a content-root SHA-256 over all descriptors and source/record roots;
- fixed candidate signer identity and signature namespace.

Verification reads the canonical manifest once, verifies that exact byte
snapshot, then validates artifact bytes and record hashes. Manifest, checksum,
artifact and record changes fail verification.

Normative schemas:

- `packages/formulalm_estimate_corpus/schemas/estimate-corpus-record.schema.json`;
- `packages/formulalm_estimate_corpus/schemas/estimate-corpus-manifest.schema.json`.

## Decimal calculator remains deterministic

The restricted normalized dataset retains quantities and money only for
verification. Candidate learning views exclude `quantity`, `unit_price`,
`line_total`, subtotals, tax and grand totals. Those values remain the
responsibility of the deterministic Decimal engine.

`eval/decimal-boundary.jsonl` contains arithmetic fixtures and is also marked
`training_eligible=false`.

## Deduplication and leakage-safe split

The builder removes records with the same document hash or normalized estimate
hash. Connected components use both `project_id` and `source_group_id`, keeping
project siblings, revisions, exports and source-family duplicates in one split.

## Build a local candidate

Provision the pinned allowed-signers file out of band, then pass only the
matching private key path. Python never reads or logs private key bytes; the
path is passed to `ssh-keygen -Y sign`.

```bash
backend/venv/bin/python -m packages.formulalm_estimate_corpus \
  build-local-candidate \
  --input /read-only/estimate-candidate-records.jsonl \
  --output /new/empty/formulalm-estimate-candidate \
  --candidate-signing-key "$KOLIBRI_FORMULALM_CANDIDATE_SIGNING_KEY" \
  --eval-ratio 0.20 \
  --max-records 10000
```

The output path must be new or empty. One rejected record fails the entire
build. Missing signing tools, insecure key permissions, missing/insecure trust
root, wrong signer or wrong namespace fail closed.

Verify independently without a caller-supplied trust policy:

```bash
backend/venv/bin/python -m packages.formulalm_estimate_corpus \
  verify-local-candidate \
  --manifest /new/empty/formulalm-estimate-candidate/manifest.json
```

The files named `splits/train.learning.jsonl` and
`splits/eval.learning.jsonl` are structural candidate views only. Their names
do not grant training eligibility; the signed manifest explicitly forbids it.

## FGIS CS period rule

For official quarterly prices, acquisition must first read available periods
for the price zone, download the complete latest-period dataset and perform an
exact resource-code lookup. A resource absent from the latest period must not
silently inherit an older price.

For the Republic of Tatarstan on 2026-07-14, the observed latest period was
`periodId=426` (Q2 2026) for `priceZoneId=202`. Those observations remain
factual source references, not a licence or training-approval claim. Commercial
reuse or redistribution requires a separate recorded rights decision. An older
price may be retained only as `stale_reference`, never as current official
evidence.
