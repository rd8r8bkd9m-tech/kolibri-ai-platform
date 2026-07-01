# P0 Primary Candidate Telegram Receiver Probe Tests

Remote verification reported:

- Exactly 5 redacted server-local artifacts were created.
- Redaction scan with `rg --pcre2`: `redaction_scan=PASS`.
- `systemctl is-active kolibri-telegram-gateway.service`: `inactive`.
- `systemctl is-enabled kolibri-telegram-gateway.service`: `disabled`.
- `git status --short`: only `?? run_artifacts/`; no product code modified.

Control Plane wrapper result:

- State: `failed`
- Failure:
  `command failed with rc=1: test -f docs/agent/runs/2026-07-01-p0-primary-candidate-telegram-receiver-probe-and-repair/PLAN.md`

Interpretation:

The runtime probe itself produced useful redacted evidence, but the generic
runner wrote artifacts to `run_artifacts/...` instead of the exact envelope
paths. This is another artifact-contract failure, not proof that the host probe
failed.

Mac relay checks:

- `python3 -m json.tool` passed for the dispatcher envelope.
- `git diff --check` passed before relay.
- Redaction scan passed for the relayed prior task artifacts.
