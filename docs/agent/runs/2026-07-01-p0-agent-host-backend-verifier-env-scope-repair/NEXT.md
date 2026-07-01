# Backend Verifier Env Scope Repair Next

Task ID: `P0_AGENT_HOST_BACKEND_VERIFIER_ENV_SCOPE_REPAIR_2026_07_01`

Recommended next remote dispatch command:

```bash
ops/kolibri-dispatch submit --file <corrected-envelope.json>
```

The corrected envelope should keep PR #83 on
`p0/agent-host-runner-contract-hardening-2026-06-30`, point at PR #83, and use
this write scope:

```json
[
  ".gitignore",
  "docs/agent/AGENT_RUNNER_CONTRACT.md",
  "ops/agent_host.py",
  "tests/test_agent_host_runner_contract.py",
  "docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-contract/**",
  "docs/agent/runs/2026-07-01-p0-agent-host-backend-verifier-env-scope-repair/**"
]
```

No follow-up product-code task is required for this repair.
