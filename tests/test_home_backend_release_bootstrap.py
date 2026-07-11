from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ops import home_backend_release_bootstrap as backend_bootstrap
from ops.home_backend_release_bootstrap import (
    BACKEND_WORKING_DIRECTORY,
    CANONICAL_DROPIN,
    DROPIN_PATH,
    FRONTEND_DIST,
    BackendBootstrapError,
    apply,
    plan,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeRunner:
    def __init__(
        self,
        *,
        fail_health_calls: set[int] | None = None,
        effective_configured: bool = False,
    ):
        self.fail_health_calls = fail_health_calls or set()
        self.effective_configured = effective_configured
        self.health_calls = 0
        self.calls: list[tuple[str, ...]] = []
        self.import_env: dict[str, str] | None = None
        self.import_cwd: str | None = None

    def run(self, argv, *, cwd=None, env=None, timeout=30):
        del timeout
        command = tuple(str(item) for item in argv)
        self.calls.append(command)
        stdout = ""
        returncode = 0
        if command[1:3] == ("show", "kolibri-backend.service"):
            property_argument = next(
                (item for item in command if item.startswith("--property=")), ""
            )
            if "--value" not in command:
                working_directory = (
                    BACKEND_WORKING_DIRECTORY
                    if self.effective_configured
                    else "/srv/kolibri/repo/backend"
                )
                dropins = (
                    "/etc/systemd/system/kolibri-backend.service.d/zzzzzz-home-release.conf"
                    if self.effective_configured
                    else ""
                )
                stdout = (
                    "LoadState=loaded\nActiveState=active\nSubState=running\n"
                    "UnitFileState=enabled\n"
                    "FragmentPath=/etc/systemd/system/kolibri-backend.service\n"
                    f"DropInPaths={dropins}\nWorkingDirectory={working_directory}\n"
                    "MainPID=123\n"
                )
            elif property_argument == "--property=WorkingDirectory":
                stdout = f"{BACKEND_WORKING_DIRECTORY}\n"
            elif property_argument == "--property=DropInPaths":
                stdout = f"{DROPIN_PATH}\n"
            elif property_argument == "--property=Environment":
                stdout = (
                    f"KOLIBRI_FRONTEND_DIST={FRONTEND_DIST} "
                    "KOLIBRI_OWNER_API_TOKEN_FILE=/etc/kolibri/owner-api-token "
                    "PRIVATE_VALUE=must-not-be-returned\n"
                )
        elif command[1:3] == ("is-active", "--quiet"):
            returncode = 0
        elif command[0].endswith("/.venv/bin/python"):
            self.import_env = dict(env or {})
            self.import_cwd = cwd
        elif command[0] == "/usr/bin/curl":
            self.health_calls += 1
            if self.health_calls in self.fail_health_calls:
                returncode = 22
                stdout = "sensitive-error-must-not-be-emitted"
            else:
                stdout = json.dumps({"status": "ok"})
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


def _executable(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)


def prepared_root(tmp_path: Path, *, nested_current: bool = False) -> Path:
    root = tmp_path / "root"
    for relative in (
        "var/backups",
        "etc/systemd/system",
        "usr/bin",
        "srv/kolibri/repo/.venv/bin",
        "opt/kolibri-ai/releases",
    ):
        (root / relative).mkdir(parents=True, mode=0o755)
    _executable(root / "usr/bin/systemctl")
    _executable(root / "usr/bin/curl")
    _executable(root / "srv/kolibri/repo/.venv/bin/python")
    _executable(root / "srv/kolibri/repo/.venv/bin/uvicorn")
    release = root / "opt/kolibri-ai/releases/release-a"
    if nested_current:
        release = release / "nested"
    (release / "backend").mkdir(parents=True)
    (release / "frontend/dist").mkdir(parents=True)
    current = root / "opt/kolibri-ai/current"
    target = "releases/release-a/nested" if nested_current else "releases/release-a"
    current.symlink_to(target)
    return root


def source_dropin(tmp_path: Path) -> Path:
    path = tmp_path / "10-release.conf"
    path.write_bytes(CANONICAL_DROPIN)
    return path


def test_plan_is_read_only_and_imports_current_with_existing_venv(tmp_path):
    root = prepared_root(tmp_path)
    runner = FakeRunner()

    result = plan(root=root, runner=runner)

    assert result["status"] == "planned"
    assert result["mutation"] == "none"
    assert result["current_link"] == "contained_direct_release_child"
    assert not (root / DROPIN_PATH.lstrip("/")).exists()
    assert not (root / "var/backups/kolibri").exists()
    assert runner.import_cwd == f"{root}/opt/kolibri-ai/current/backend"
    assert runner.import_env == {
        "HOME": "/nonexistent",
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": (
            f"{root}/opt/kolibri-ai/current/backend:"
            f"{root}/opt/kolibri-ai/current"
        ),
        "KOLIBRI_ENV": "production",
        "KOLIBRI_FACTORY_CONTROL_URL": "http://127.0.0.1:9101",
        "KOLIBRI_FRONTEND_DIST": (
            f"{root}/opt/kolibri-ai/current/frontend/dist"
        ),
        "KOLIBRI_OWNER_API_TOKEN_FILE": "/etc/kolibri/owner-api-token",
    }
    assert not any(call[1:2] in {("restart",), ("daemon-reload",)} for call in runner.calls)


def test_apply_backs_up_metadata_installs_dropin_and_restarts_only_backend(tmp_path):
    root = prepared_root(tmp_path)
    runner = FakeRunner()
    current = root / "opt/kolibri-ai/current"
    link_before = os.readlink(current)

    result = apply(
        source_dropin(tmp_path),
        "backend-test-apply",
        root=root,
        runner=runner,
    )

    destination = root / DROPIN_PATH.lstrip("/")
    backup = root / "var/backups/kolibri/backend-release-dropin/backend-test-apply"
    assert destination.read_bytes() == CANONICAL_DROPIN
    assert (backup / "metadata.json").is_file()
    assert (backup / "unit.before").is_file()
    assert (backup / "status").read_text(encoding="utf-8") == "applied\n"
    assert result["health_gate"] == "passed"
    assert result["working_directory"] == BACKEND_WORKING_DIRECTORY
    assert result["frontend_dist"] == FRONTEND_DIST
    assert os.readlink(current) == link_before
    mutating = [call for call in runner.calls if len(call) > 1 and call[1] in {"restart", "stop", "start"}]
    assert mutating == [("/usr/bin/systemctl", "restart", "kolibri-backend.service")]
    assert "PRIVATE_VALUE" not in json.dumps(result)


def test_failed_health_gate_restores_original_dropin_and_restarts_old_backend(
    tmp_path, monkeypatch
):
    root = prepared_root(tmp_path)
    runner = FakeRunner(fail_health_calls=set(range(2, 8)))
    monkeypatch.setattr(backend_bootstrap.time, "sleep", lambda _seconds: None)
    destination = root / DROPIN_PATH.lstrip("/")
    destination.parent.mkdir(parents=True)
    original = b"[Service]\nEnvironment=LEGACY_SAFE_VALUE=1\n"
    destination.write_bytes(original)
    destination.chmod(0o640)

    with pytest.raises(BackendBootstrapError) as captured:
        apply(
            source_dropin(tmp_path),
            "backend-test-rollback",
            root=root,
            runner=runner,
        )

    assert captured.value.code == "backend_health_gate_failed"
    assert captured.value.rollback == "complete"
    assert destination.read_bytes() == original
    assert destination.stat().st_mode & 0o777 == 0o640
    backup = root / "var/backups/kolibri/backend-release-dropin/backend-test-rollback"
    assert (backup / "dropin.before").read_bytes() == original
    assert (backup / "status").read_text(encoding="utf-8") == "rolled_back\n"
    restarts = [call for call in runner.calls if call[1:2] == ("restart",)]
    assert restarts == [
        ("/usr/bin/systemctl", "restart", "kolibri-backend.service"),
        ("/usr/bin/systemctl", "restart", "kolibri-backend.service"),
    ]


def test_current_must_be_direct_child_of_release_root(tmp_path):
    root = prepared_root(tmp_path, nested_current=True)

    with pytest.raises(
        BackendBootstrapError, match="release_current_not_direct_release_child"
    ):
        plan(root=root, runner=FakeRunner())


def test_matching_dropin_is_idempotent_without_restart(tmp_path):
    root = prepared_root(tmp_path)
    destination = root / DROPIN_PATH.lstrip("/")
    destination.parent.mkdir(parents=True)
    destination.write_bytes(CANONICAL_DROPIN)
    runner = FakeRunner(effective_configured=True)

    result = apply(
        source_dropin(tmp_path),
        "backend-test-idempotent",
        root=root,
        runner=runner,
    )

    assert result["status"] == "already_configured"
    assert result["restart_performed"] is False
    assert not any(call[1:2] == ("restart",) for call in runner.calls)
    assert not (root / "var/backups/kolibri").exists()


def test_effective_legacy_named_dropin_prevents_duplicate_install(tmp_path):
    root = prepared_root(tmp_path)
    runner = FakeRunner(effective_configured=True)
    legacy = (
        root
        / "etc/systemd/system/kolibri-backend.service.d/zzzzzz-home-release.conf"
    )
    legacy.parent.mkdir(parents=True)
    legacy.write_text("[Service]\n# pre-existing effective release layout\n", encoding="utf-8")

    planned = plan(root=root, runner=runner)
    applied = apply(
        source_dropin(tmp_path),
        "backend-existing-effective",
        root=root,
        runner=runner,
    )

    assert planned["status"] == "already_configured"
    assert planned["dropin"] == "effective_existing"
    assert planned["effective_dropin_count"] == 1
    assert applied["status"] == "already_configured"
    assert applied["restart_performed"] is False
    assert not (root / DROPIN_PATH.lstrip("/")).exists()
    assert legacy.is_file()
    assert not any(call[1:2] == ("restart",) for call in runner.calls)
    assert not (root / "var/backups/kolibri").exists()


def test_health_gate_retries_startup_race_within_bounded_attempts(
    tmp_path, monkeypatch
):
    root = prepared_root(tmp_path)
    runner = FakeRunner(fail_health_calls={1, 2})
    sleeps: list[float] = []
    monkeypatch.setattr(backend_bootstrap.time, "sleep", sleeps.append)

    result = plan(root=root, runner=runner)

    assert result["status"] == "planned"
    assert runner.health_calls == 3
    assert sleeps == [0.5, 0.5]


def test_repository_dropin_and_wrapper_contracts_are_fail_closed():
    dropin = (ROOT / "ops/systemd/kolibri-backend-home-release.conf").read_bytes()
    wrapper = (ROOT / "scripts/bootstrap-home-backend-release.sh").read_text(
        encoding="utf-8"
    )
    helper = (ROOT / "ops/home_backend_release_bootstrap.py").read_text(
        encoding="utf-8"
    )

    assert dropin == CANONICAL_DROPIN
    assert "APPLY=false" in wrapper
    assert 'if [ "$APPLY" != true ]' in wrapper
    assert "control_plane_endpoint.py" in wrapper
    assert 'REMOTE_TARGET="root@$HOME_HOST"' in wrapper
    assert "10.99.0.1" not in wrapper
    assert '"main"' not in wrapper
    assert '"primary"' not in wrapper
    assert "printenv" not in wrapper + helper
    assert "systemctl cat" not in wrapper + helper
    assert "ops/telegram.env" not in wrapper + helper
    assert "kolibri-factory-control.service" not in wrapper + helper
    assert "kolibri-mesh" not in wrapper + helper
    assert "current.symlink_to" not in helper
    assert "os.replace(temporary, path)" in helper
    assert "backend_health_gate_failed" in helper
