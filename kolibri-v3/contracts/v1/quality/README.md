# Kolibri Evidence, Review and SignOff contracts v1

Task: `P02-T04`.

Evidence, Review and SignOff are different records and cannot substitute for
one another:

- Evidence supports one claim against an exact subject version and records
  source locator/hash, retrieved/effective dates, jurisdiction/region,
  applicability, confidence, method and verifier result.
- Review binds an independent author/reviewer pair to one exact artifact
  version/hash, criteria, evidence and typed findings. An open high/critical
  finding or failed/inconclusive criterion blocks `approved_internal`.
- SignOff records a policy-authorized decision for one exact artifact
  version/hash. Its type is one of `internal_approval`,
  `corporate_release_authorization`, `qualified_human_signoff` or
  `client_acceptance`; these gates are non-substitutable.

`qualified_human_signoff` requires a human actor, credential reference and
signature reference. An internal agent approval never becomes a legal
signature by carrying human-looking metadata.

All records are versioned. Evidence and SignOff are superseded, made stale or
revoked by a new record/state transition; history is not silently rewritten.
The quality manifest binds exact evidence/review/sign-off versions to the exact
artifact and lifecycle version. A stale, revoked or superseded artifact is
always release-ineligible.

The reference owner-boundary validator checks tenant/Goal/Case, artifact
ID/version/hash, lifecycle version, active/passed evidence, completed approved
reviews, granted sign-offs and explicitly required sign-off types. Runtime
adapters must preserve these checks; legacy `verified`, `APPROVED`, estimate
status strings and P7 owner approval are compatibility inputs, not aliases for
the canonical entities.
