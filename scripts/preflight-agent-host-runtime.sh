#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-$(pwd)}"
UNIT="${ROOT}/ops/systemd/kolibri-agent-host.service"
SOURCE="${ROOT}/ops/agent_host.py"
LAUNCHER="${KOLIBRI_AGENT_HOST_LAUNCHER:-/usr/local/bin/kolibri-agent-host}"
REQUIRE_LAUNCHER="${KOLIBRI_AGENT_HOST_REQUIRE_LAUNCHER:-0}"

if [[ ! -f "${SOURCE}" ]]; then
  echo "agent_host_missing:${SOURCE}" >&2
  exit 1
fi

if [[ ! -f "${UNIT}" ]]; then
  echo "agent_host_unit_missing:${UNIT}" >&2
  exit 1
fi

if ! grep -qx "EnvironmentFile=/etc/kolibri-agent-host.env" "${UNIT}"; then
  echo "agent_host_unit_missing_environment_file" >&2
  exit 1
fi

if ! grep -qx "ExecStart=/usr/local/bin/kolibri-agent-host" "${UNIT}"; then
  echo "agent_host_unit_unexpected_execstart" >&2
  exit 1
fi

if [[ "${REQUIRE_LAUNCHER}" == "1" && ! -f "${LAUNCHER}" ]]; then
  echo "agent_host_launcher_missing:${LAUNCHER}" >&2
  exit 1
fi

KOLIBRI_REPO_ROOT="${ROOT}" \
KOLIBRI_AGENT_HOST_LAUNCHER="${LAUNCHER}" \
KOLIBRI_AGENT_HOST_REQUIRE_LAUNCHER="${REQUIRE_LAUNCHER}" \
python3 - <<'PY'
import importlib.util
import os
import tempfile
from importlib.machinery import SourceFileLoader
from pathlib import Path


root = Path(os.environ["KOLIBRI_REPO_ROOT"])
launcher = Path(os.environ["KOLIBRI_AGENT_HOST_LAUNCHER"])
require_launcher = os.environ["KOLIBRI_AGENT_HOST_REQUIRE_LAUNCHER"] == "1"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_loader(name, SourceFileLoader(name, str(path)))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def assert_pr83_contract(module, label: str) -> None:
    required_fields = {
        "task_id",
        "status",
        "changed_files",
        "artifact_dir",
        "required_artifacts_present",
        "required_artifacts_missing",
        "write_scope",
        "write_scope_violations",
        "read_only",
        "product_code_modification_forbidden",
        "product_code_changed",
        "push_attempted",
        "push_blocked",
        "blocked_reason",
        "failure_reason",
        "tests_run",
        "next_recommended_task",
    }
    missing_fields = sorted(required_fields - set(module.CONTRACT_RESULT_FIELDS))
    if missing_fields:
        raise SystemExit(f"{label}:contract_fields_missing:{missing_fields}")

    for flag in ("git_push_forbidden", "no_push", "read_only"):
        if flag not in module.NO_PUSH_FLAGS:
            raise SystemExit(f"{label}:no_push_flag_missing:{flag}")

    if not hasattr(module.AgentHost, "git_push_after_contract_verification"):
        raise SystemExit(f"{label}:publish_preflight_method_missing")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        worktree = tmp_path / "repo"
        artifact_dir = tmp_path / "artifacts"
        worktree.mkdir()
        artifact_dir.mkdir()
        task = {
            "task_id": "PR83-RUNTIME-CANARY",
            "kind": "impl_factory_smoke",
            "envelope": {
                "required_artifacts": ["docs/agent/runs/pr83-runtime-canary/RESULT.md"],
            },
        }
        result = module.finalize_runner_contract(
            task,
            {
                "task_id": task["task_id"],
                "status": "completed",
                "changed_files": ["tests/pr83_runtime_canary.py"],
                "checks": ["contract preflight synthetic missing artifact"],
            },
            artifact_dir,
            worktree=worktree,
            changed_files=["tests/pr83_runtime_canary.py"],
            push_attempted=False,
        )
        if result["status"] != "blocked":
            raise SystemExit(f"{label}:missing_artifact_did_not_block")
        if result["push_attempted"] is not False:
            raise SystemExit(f"{label}:preflight_marked_push_attempted")
        if "required_artifacts_missing" not in str(result.get("blocked_reason")):
            raise SystemExit(f"{label}:missing_artifact_blocker_not_reported")

        no_push = module.finalize_runner_contract(
            {
                "task_id": "PR83-NO-PUSH-CANARY",
                "kind": "impl_factory_smoke",
                "envelope": {"no_push": True},
            },
            {"task_id": "PR83-NO-PUSH-CANARY", "status": "completed", "changed_files": []},
            artifact_dir,
            worktree=worktree,
            changed_files=[],
            push_attempted=False,
        )
        if no_push["status"] != "completed" or no_push["push_blocked"] is not True:
            raise SystemExit(f"{label}:no_push_completion_contract_failed")


source_module = load_module(root / "ops" / "agent_host.py", "agent_host_source_preflight")
assert_pr83_contract(source_module, "source")

if require_launcher:
    launcher_module = load_module(launcher, "agent_host_launcher_preflight")
    assert_pr83_contract(launcher_module, "launcher")

print("agent_host_pr83_runtime_preflight=ok")
PY
