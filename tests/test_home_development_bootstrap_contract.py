from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "bootstrap-home-development.sh"


def run_script(*args: str, env: dict[str, str] | None = None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def test_default_mode_is_read_only_dry_run():
    result = run_script()

    assert result.returncode == 0, result.stderr
    assert "home_development_layout=dry-run" in result.stdout
    assert "production_services_changed=false" in result.stdout
    assert "required_node=26.5.0" in result.stdout
    assert "required_python=3.14.6" in result.stdout
    assert "DRY-RUN:" in result.stdout


def test_apply_requires_explicit_owner_approval():
    result = run_script("--apply", env={"KOLIBRI_OWNER_APPROVAL_ID": ""})

    assert result.returncode == 3
    assert "KOLIBRI_OWNER_APPROVAL_ID is required" in result.stderr


def test_unsafe_target_root_is_rejected():
    result = run_script(
        "--dry-run",
        env={"KOLIBRI_HOME_SOURCE_ROOT": "/tmp/not-home"},
    )

    assert result.returncode == 2
    assert "refusing unsafe Home source root" in result.stderr


def test_non_namespaced_integration_branch_is_rejected():
    result = run_script(
        "--dry-run",
        env={"KOLIBRI_INTEGRATION_BRANCH": "main"},
    )

    assert result.returncode == 2
    assert "codex/ namespace" in result.stderr


def test_script_does_not_contain_production_or_credential_mutations():
    source = SCRIPT.read_text(encoding="utf-8")

    forbidden = (
        "systemctl restart",
        "systemctl stop",
        "rsync",
        "scp ",
        "ops/telegram.env",
        "StrictHostKeyChecking=no",
    )
    assert not any(token in source for token in forbidden)


def test_existing_control_worktree_must_be_clean_before_safe_switch():
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'status --porcelain=v1 -uall' in source
    assert "existing Home control worktree is dirty; refusing branch switch" in source
    assert 'git -C "$CONTROL" switch "$INTEGRATION_BRANCH"' in source
    assert "reset --hard" not in source


def test_apply_checks_exact_runtime_pins_without_installing_them():
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'REQUIRED_NODE_VERSION=$(tr -d' in source
    assert 'REQUIRED_PYTHON_VERSION=$(tr -d' in source
    assert "verify_runtime_versions" in source
    assert "apt install" not in source
    assert "brew install" not in source
    assert "curl |" not in source
