# Result

Status: local repair patch prepared and focused checks passed.

The Control Plane compatibility path now computes the effective AI runner and
requires the corresponding runner capability before leasing the task. This
prevents Codex/MIMO tasks from spending retry attempts on nodes without the
requested runner.

The MIMO Pool bootstrap task remains `queued` in Control Plane and has not
started a full wave.

## Remaining gap

This local code change is not yet deployed to the live Control Plane. Production
still needs PR/CI/release gate and owner-approved canary before it can be
claimed live.

