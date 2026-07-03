# Next

The first PR gates declared package-change manifests before runner execution and
in result finalization. Deeper runtime interception needs a separate PR because
it must wrap every command execution path and distinguish allowed task-local
venv/node_modules/cache installs from node mutation.

Exact follow-up Control Plane envelope:

```json
{
  "task_id": "P0_FACTORY_PACKAGE_MANAGER_RUNTIME_INTERCEPTOR_20260703",
  "idempotency_key": "primary-candidate:P0_FACTORY_PACKAGE_MANAGER_RUNTIME_INTERCEPTOR_20260703",
  "priority": "P0",
  "kind": "impl_factory_smoke",
  "target_node": "primary-candidate",
  "required_capability": "generic_implementation",
  "branch": "p0/package-manager-runtime-interceptor-2026-07-03",
  "objective": "Add Agent Host command-level runtime interception for package manager commands. Block apt/dpkg, npm/npx/pnpm/yarn, pip/pipx/uv, go, cargo, binary downloads, service bootstrap packages, global installs, curl|bash, inline credential URLs, git/file/http package specs, unmanaged mutation, Mac package installs by remote agents, and secret-printing commands unless a matching package_changes/package_policy manifest has already passed the Kolibri Package Manager Law. Preserve isolated task-local venv/node_modules/cache installs only when declared as install_scope=ephemeral_task_env and isolated=true. Add tests for blocked shell commands and allowed isolated test env installs. Do not push main, do not force push, do not print secrets.",
  "envelope": {
    "kind": "impl_factory_smoke",
    "write_scope": [
      "ops/agent_host.py",
      "tests/test_agent_host_package_runtime_interceptor.py",
      "docs/agent/runs/2026-07-03-p0-package-manager-runtime-interceptor/**"
    ],
    "canonical_run_artifact_dir": "docs/agent/runs/2026-07-03-p0-package-manager-runtime-interceptor",
    "package_policy": {
      "changes": []
    },
    "required_artifacts": [
      "docs/agent/runs/2026-07-03-p0-package-manager-runtime-interceptor/PLAN.md",
      "docs/agent/runs/2026-07-03-p0-package-manager-runtime-interceptor/ACTIONS.md",
      "docs/agent/runs/2026-07-03-p0-package-manager-runtime-interceptor/TESTS.md",
      "docs/agent/runs/2026-07-03-p0-package-manager-runtime-interceptor/RESULT.md",
      "docs/agent/runs/2026-07-03-p0-package-manager-runtime-interceptor/NEXT.md"
    ]
  },
  "verification_commands": [
    "python3 -m pytest -q tests/test_agent_host_package_runtime_interceptor.py tests/test_agent_host_runner_contract.py",
    "python3 -m compileall ops tests",
    "git diff --check"
  ]
}
```
