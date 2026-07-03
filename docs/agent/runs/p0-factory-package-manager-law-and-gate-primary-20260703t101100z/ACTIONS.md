# Actions

- Added `docs/superfactory/PACKAGE_MANAGER_LAW.md` as the canonical Kolibri
  package-change law.
- Extended `ops/agent_host.py` with `kolibri_package_manager_law` validation for
  `package_changes` and `package_policy.changes`.
- Added package-policy result fields and violation blockers to runner contract
  finalization.
- Blocked invalid package envelopes before task dispatch with
  `error_type: package_policy_violation`.
- Added MIMO Code rollout checks for npm registry source, loopback service,
  `/etc/kolibri/mimocode.env`, `0600`, and raw secret output denial.
- Added focused contract tests in `tests/test_agent_host_runner_contract.py`.
