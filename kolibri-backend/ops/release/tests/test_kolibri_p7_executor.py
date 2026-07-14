from __future__ import annotations

import importlib.util
import grp
import io
import json
import os
from pathlib import Path
import pwd
import sqlite3
import stat
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).parents[1] / "kolibri_p7_executor.py"
SPEC = importlib.util.spec_from_file_location("kolibri_p7_executor", SCRIPT)
assert SPEC and SPEC.loader
executor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = executor
SPEC.loader.exec_module(executor)


PROXY_SITE = b"""server {
    location /api/v1/ { proxy_pass http://127.0.0.1:18015; }
    location /api/ { proxy_pass http://127.0.0.1:18015; }
    location /v1/ { proxy_pass http://127.0.0.1:18015; }
    location /ws/ { proxy_pass http://127.0.0.1:18015; }
    location / { proxy_pass http://127.0.0.1:15193; }
}
"""


STATIC_SITE = b"""server {
    location /api/v1/ {
        proxy_pass http://127.0.0.1:18015;
    }
    location /api/ {
        proxy_pass http://127.0.0.1:18015;
    }
    location /v1/ {
        proxy_pass http://127.0.0.1:18015;
    }
    location /ws/ {
        proxy_pass http://127.0.0.1:18015;
    }
    location / {
        root /opt/kolibri/p6/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
}
"""


def test_render_paired_site_rewrites_all_routes_and_supports_static_p6():
    for active in (PROXY_SITE, STATIC_SITE):
        rendered = executor.render_paired_site(
            active,
            release_id="kolibri-p7-test",
            candidate_backend="http://127.0.0.1:18018",
            candidate_frontend="http://127.0.0.1:15194",
            rollback_backend="http://127.0.0.1:18015",
            rollback_frontend="http://127.0.0.1:15193",
        ).decode()
        blocks = executor._location_blocks(rendered)
        for route in executor.BACKEND_ROUTES:
            start, end, _ = blocks[route]
            assert executor._proxy_pass(rendered[start:end]) == "http://127.0.0.1:18018"
        start, end, _ = blocks["/"]
        assert executor._proxy_pass(rendered[start:end]) == "http://127.0.0.1:15194"
        assert "kolibri-p7-test" in rendered


def test_render_paired_site_rejects_route_drift_and_ambiguous_frontend():
    drifted = PROXY_SITE.replace(b"18015", b"19999", 1)
    with pytest.raises(executor.P7ExecutorError, match="p7_active_backend_route_drift"):
        executor.render_paired_site(
            drifted,
            release_id="p7",
            candidate_backend="http://127.0.0.1:18018",
            candidate_frontend="http://127.0.0.1:15194",
            rollback_backend="http://127.0.0.1:18015",
            rollback_frontend="http://127.0.0.1:15193",
        )
    ambiguous = STATIC_SITE.replace(
        b"root /opt/kolibri/p6/frontend/dist;",
        b"root /one;\n        root /two;",
    )
    with pytest.raises(executor.P7ExecutorError, match="p7_active_frontend_route_ambiguous"):
        executor.render_paired_site(
            ambiguous,
            release_id="p7",
            candidate_backend="http://127.0.0.1:18018",
            candidate_frontend="http://127.0.0.1:15194",
            rollback_backend="http://127.0.0.1:18015",
            rollback_frontend="http://127.0.0.1:15193",
        )


def _tar(path: Path, members: list[tuple[tarfile.TarInfo, bytes]]) -> None:
    with tarfile.open(path, "w") as archive:
        for info, content in members:
            archive.addfile(info, io.BytesIO(content))


def test_safe_extract_rejects_traversal_and_links(tmp_path: Path):
    traversal = tarfile.TarInfo("../escape")
    traversal.size = 1
    archive = tmp_path / "traversal.tar"
    _tar(archive, [(traversal, b"x")])
    with pytest.raises(executor.P7ExecutorError, match="p7_archive_path_invalid"):
        executor.safe_extract_tar(archive, tmp_path / "out-traversal")
    assert not (tmp_path / "escape").exists()

    link = tarfile.TarInfo("kolibri-backend/link")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    archive = tmp_path / "link.tar"
    _tar(archive, [(link, b"")])
    with pytest.raises(executor.P7ExecutorError, match="p7_archive_special_file_forbidden"):
        executor.safe_extract_tar(archive, tmp_path / "out-link")


def test_stage_release_is_immutable_readable_and_data_owned_by_runtime(tmp_path: Path):
    signed = tmp_path / "signed"
    signed.mkdir()
    lock_bytes = b"example==1 --hash=sha256:" + b"0" * 64 + b"\n"
    backend = tarfile.TarInfo("kolibri-backend/requirements.lock")
    backend.size = len(lock_bytes)
    _tar(signed / "backend.tar", [(backend, lock_bytes)])
    index_bytes = b"<html>kolibri-p7-permission-test</html>"
    index = tarfile.TarInfo("kolibri-v2/dist/index.html")
    index.size = len(index_bytes)
    _tar(signed / "frontend.tar", [(index, index_bytes)])
    verified = executor.VerifiedPlan(
        {"release_id": "kolibri-p7-permission-test"},
        {
            "toolchain": {
                "lockfiles": {
                    executor.REQUIREMENTS_LOCK: {
                        "sha256": executor.sha256_bytes(lock_bytes),
                        "size_bytes": len(lock_bytes),
                    }
                }
            }
        },
        {},
        SimpleNamespace(release_dir=signed),
    )
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name

    runtime = executor.stage_release(
        verified,
        tmp_path / "releases",
        tmp_path / "data",
        runtime_user=user,
        runtime_group=group,
    )

    assert stat.S_IMODE(runtime.release_dir.stat().st_mode) == 0o755
    assert runtime.backend_dir.joinpath("requirements.lock").read_bytes() == lock_bytes
    assert runtime.frontend_dir.joinpath("index.html").read_bytes() == index_bytes
    assert runtime.data_dir.stat().st_uid == os.getuid()
    assert runtime.data_dir.stat().st_gid == os.getgid()
    assert runtime.runtime_home == Path.home()


def test_runtime_units_bind_exact_account_secret_paths_and_ports(tmp_path: Path):
    backend = tmp_path / "runtime" / "backend"
    templates = backend / "ops" / "release" / "templates"
    templates.mkdir(parents=True)
    source_templates = SCRIPT.parent / "templates"
    for name in ("kolibri-backend-p7.service.in", "kolibri-frontend-p7.service.in"):
        (templates / name).write_bytes((source_templates / name).read_bytes())
    runtime = executor.RuntimePaths(
        tmp_path / "release" / "kolibri-p7-unit-test",
        backend,
        tmp_path / "runtime" / "frontend",
        tmp_path / "runtime" / "data",
        tmp_path / "runtime" / "data" / "kolibri.db",
        tmp_path / "runtime" / "data" / "venv",
        os.getuid(),
        os.getgid(),
        Path.home(),
    )
    runtime.frontend_dir.mkdir(parents=True)
    runtime.data_dir.mkdir(parents=True)
    config_root = tmp_path / "config"
    config_root.mkdir()
    config = _executor_config(config_root, _dummy_inputs(tmp_path))
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    config = executor.dataclasses.replace(config, runtime_user=user, runtime_group=group)

    backups = executor.install_runtime_units(runtime, config)

    assert len(backups) == 2
    backend_unit = (config.systemd_dir / executor.BACKEND_SERVICE).read_text()
    frontend_unit = (config.systemd_dir / executor.FRONTEND_SERVICE).read_text()
    assert f"User={user}" in backend_unit
    assert f"Group={group}" in backend_unit
    assert f"EnvironmentFile={config.runtime_secret_file}" in backend_unit
    assert f"Environment=HOME={Path.home()}" in backend_unit
    assert "--port 18018" in backend_unit
    assert "--port 15194" in frontend_unit
    assert "@@" not in backend_unit + frontend_unit


def test_consistent_sqlite_backup_is_integrity_checked_and_source_preserved(tmp_path: Path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('truth')")
    before = executor.sha256_file(source)
    destination = tmp_path / "candidate" / "kolibri.db"
    destination.parent.mkdir()

    evidence = executor.consistent_sqlite_backup(source, destination)

    assert executor.sha256_file(source) == before
    assert evidence["source_sha256"] == before
    assert evidence["backup_sha256"] == executor.sha256_file(destination)
    assert evidence["writer_drained"] is True
    with sqlite3.connect(destination) as connection:
        assert connection.execute("SELECT value FROM sample").fetchone() == ("truth",)


def test_consistent_sqlite_backup_rejects_another_writer(tmp_path: Path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
    destination = tmp_path / "candidate.db"
    blocker = sqlite3.connect(source)
    blocker.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(executor.P7ExecutorError, match="p7_sqlite_write_drain_not_proven"):
            executor.consistent_sqlite_backup(source, destination)
    finally:
        blocker.rollback()
        blocker.close()


def test_runtime_secret_gate_does_not_accept_missing_or_short_values(tmp_path: Path):
    secret_file = tmp_path / "backend.env"
    manifest = {
        "runtime_requirements": {
            "required_backend_secret_names": ["JWT_SECRET_KEY", "KOLIBRI_EVIDENCE_SIGNING_KEY"],
            "minimum_secret_bytes": 32,
        }
    }
    secret_file.write_text("JWT_SECRET_KEY=short\n", encoding="utf-8")
    with pytest.raises(executor.P7ExecutorError, match="p7_required_runtime_secret_missing"):
        executor.require_runtime_secrets(secret_file, manifest)
    secret_file.write_text(
        "JWT_SECRET_KEY=" + "a" * 32 + "\nKOLIBRI_EVIDENCE_SIGNING_KEY='" + "b" * 32 + "'\n",
        encoding="utf-8",
    )
    executor.require_runtime_secrets(secret_file, manifest)


def _valid_plan() -> dict:
    return {
        "schema_version": executor.EXPECTED_PLAN_SCHEMA,
        "status": "planned_not_applied",
        "production_applied": False,
        "release_id": "kolibri-p7-test",
        "source_commit": "a" * 40,
        "manifest_sha256": "1" * 64,
        "executor_contract": {
            "this_tool_can_apply": False,
            "root_required_by_downstream_executor": True,
            "owner_approval_and_all_bindings_must_be_reverified": True,
        },
        "atomic_switch": {"expected_previous_config_sha256": "3" * 64},
        "rollback": {"manifest_sha256": "2" * 64},
    }


def _snapshot(tmp_path: Path, plan: dict) -> executor.SnapshotInputs:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n")
    candidate = tmp_path / "candidate"
    rollback = tmp_path / "rollback"
    candidate.mkdir(exist_ok=True)
    rollback.mkdir(exist_ok=True)
    placeholder = tmp_path / "placeholder"
    placeholder.write_text("x")
    return executor.SnapshotInputs(
        path,
        candidate,
        placeholder,
        rollback,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        placeholder,
        {},
    )


def test_reverify_plan_calls_existing_planner_and_enforces_exact_ports_and_lock(tmp_path: Path):
    plan = _valid_plan()
    manifest = {
        "targets": {
            "backend": {"port": 18018, "origin": "http://127.0.0.1:18018"},
            "frontend": {"port": 15194, "origin": "http://127.0.0.1:15194"},
        },
        "toolchain": {"lockfiles": {executor.REQUIREMENTS_LOCK: {"sha256": "4" * 64}}},
    }
    rollback = {"release_id": "kolibri-p6", "targets": {}}
    calls = []

    class FakeP7:
        @staticmethod
        def canonical_json(payload):
            return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

        @staticmethod
        def paired_switch_plan(**kwargs):
            calls.append(kwargs)
            return plan

        @staticmethod
        def load_manifest(path):
            return (manifest, path / "release-manifest.json", "1" * 64) if path.name == "candidate" else (
                rollback,
                path / "release-manifest.json",
                "2" * 64,
            )

    verified = executor.reverify_plan(_snapshot(tmp_path, plan), FakeP7)
    assert verified.manifest is manifest
    assert len(calls) == 1
    assert calls[0]["previous_route_config_sha256"] == "3" * 64

    manifest["targets"]["backend"]["port"] = 18015
    with pytest.raises(executor.P7ExecutorError, match="p7_exact_runtime_target_invalid"):
        executor.reverify_plan(_snapshot(tmp_path, plan), FakeP7)


class FakeRunner(executor.CommandRunner):
    def __init__(self):
        self.commands: list[tuple[str, ...]] = []

    def run(self, command, **_kwargs):
        command = tuple(command)
        self.commands.append(command)
        stdout = "active\n" if "is-active" in command else ""
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


class PartialStartFailureRunner(FakeRunner):
    def run(self, command, **kwargs):
        command = tuple(command)
        if command[:3] == ("systemctl", "enable", "--now"):
            self.commands.append(command)
            raise executor.P7ExecutorError("p7_executor_command_failed")
        return super().run(command, **kwargs)


class PythonVersionRunner(FakeRunner):
    def __init__(self, version: str):
        super().__init__()
        self.version = version

    def run(self, command, **kwargs):
        command = tuple(command)
        self.commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=self.version + "\n", stderr="")


def test_locked_environment_rejects_runtime_python_drift(tmp_path: Path):
    runtime = executor.RuntimePaths(
        tmp_path / "release",
        tmp_path / "release" / "backend",
        tmp_path / "release" / "frontend",
        tmp_path / "data",
        tmp_path / "data" / "kolibri.db",
        tmp_path / "data" / "venv",
    )
    runtime.backend_dir.mkdir(parents=True)
    (runtime.backend_dir / "requirements.lock").write_text("example==1 --hash=sha256:" + "0" * 64)
    config = _executor_config(tmp_path, _dummy_inputs(tmp_path))
    runner = PythonVersionRunner("3.13.9")

    with pytest.raises(executor.P7ExecutorError, match="p7_runtime_python_version_mismatch"):
        executor.install_locked_environment(runtime, config, runner, "3.14.4")

    assert len(runner.commands) == 1


def test_locked_environment_uses_hashes_no_deps_and_pip_check(tmp_path: Path):
    runtime = executor.RuntimePaths(
        tmp_path / "release",
        tmp_path / "release" / "backend",
        tmp_path / "release" / "frontend",
        tmp_path / "data",
        tmp_path / "data" / "kolibri.db",
        tmp_path / "data" / "venv",
    )
    runtime.backend_dir.mkdir(parents=True)
    (runtime.backend_dir / "requirements.lock").write_text("example==1 --hash=sha256:" + "0" * 64)
    config = _executor_config(tmp_path, _dummy_inputs(tmp_path))
    runner = PythonVersionRunner("3.14.4")

    executor.install_locked_environment(runtime, config, runner, "3.14.4")

    install = next(command for command in runner.commands if "install" in command)
    assert "--require-hashes" in install
    assert "--no-deps" in install
    assert runner.commands[-1][-2:] == ("pip", "check")


def test_isolated_nginx_test_uses_candidate_without_replacing_active(tmp_path: Path):
    active = tmp_path / "sites-enabled" / "kolibriai"
    active.parent.mkdir()
    active.write_bytes(PROXY_SITE)
    other = active.parent / "other"
    other.write_text("server {}\n")
    main = tmp_path / "nginx.conf"
    main.write_text(f"events {{}}\nhttp {{\n    include {active.parent}/*;\n}}\n")
    runner = FakeRunner()

    executor.isolated_nginx_test(
        PROXY_SITE.replace(b"18015", b"18018").replace(b"15193", b"15194"),
        active_site=active,
        nginx_main=main,
        sites_enabled_dir=active.parent,
        nginx_binary="nginx",
        runner=runner,
    )

    assert active.read_bytes() == PROXY_SITE
    assert len(runner.commands) == 1
    assert runner.commands[0][:2] == ("nginx", "-t")


class RouteClient:
    def __init__(self, base_url: str, *, bad_header: bool = False):
        self.base_url = base_url
        self.bad_header = bad_header

    def request(self, method: str, path: str, payload=None):
        release = "wrong" if self.bad_header else "kolibri-p7-test"
        headers = {"x-kolibri-release": release, "content-type": "application/json"}
        if path == "/api/health":
            return executor.HttpResult(200, headers, b'{"status":"ok","release_id":"kolibri-p7-test"}')
        if path == "/":
            return executor.HttpResult(200, headers, b"kolibri-p7-test")
        if path == "/api/v1/__kolibri_p7_missing__":
            return executor.HttpResult(404, headers, b'{"detail":"not found"}')
        if method == "POST" and path == "/api/v1/shell/bootstrap":
            return executor.HttpResult(200, headers, b'{"session_type":"anonymous"}')
        raise AssertionError((method, path, payload))


def test_public_post_gates_require_exact_release_on_every_surface():
    passed = executor.public_post_gates(
        "https://kolibriai.invalid",
        "kolibri-p7-test",
        client_factory=lambda base: RouteClient(base),
    )
    assert passed["status"] == "passed"

    with pytest.raises(executor.P7ExecutorError, match="p7_public_post_gate_failed"):
        executor.public_post_gates(
            "https://kolibriai.invalid",
            "kolibri-p7-test",
            client_factory=lambda base: RouteClient(base, bad_header=True),
        )


def _executor_config(tmp_path: Path, inputs: executor.SignedInputs) -> executor.ExecutorConfig:
    active = tmp_path / "nginx" / "site.conf"
    active.parent.mkdir()
    active.write_bytes(PROXY_SITE)
    nginx_main = tmp_path / "nginx" / "nginx.conf"
    sites = tmp_path / "nginx" / "sites-enabled"
    sites.mkdir()
    (sites / "site.conf").symlink_to(active)
    nginx_main.write_text(f"events {{}}\nhttp {{ include {sites}/*; }}\n")
    database = tmp_path / "source.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample(value TEXT)")
    secrets = tmp_path / "backend.env"
    secrets.write_text("JWT_SECRET_KEY=" + "a" * 32 + "\nKOLIBRI_EVIDENCE_SIGNING_KEY=" + "b" * 32 + "\n")
    systemd = tmp_path / "systemd"
    systemd.mkdir()
    return executor.ExecutorConfig(
        inputs=inputs,
        active_site=active,
        nginx_main=nginx_main,
        sites_enabled_dir=sites,
        source_database=database,
        previous_backend_service="kolibri-backend-p6.service",
        runtime_secret_file=secrets,
        release_root=tmp_path / "releases",
        data_root=tmp_path / "data",
        backup_root=tmp_path / "backups",
        state_root=tmp_path / "state",
        systemd_dir=systemd,
        lock_path=tmp_path / "locks" / "p7.lock",
        public_base_url="https://kolibriai.invalid",
        python_binary="python3",
        nginx_binary="nginx",
        systemctl_binary="systemctl",
    )


def _dummy_inputs(tmp_path: Path) -> executor.SignedInputs:
    path = tmp_path / "unused"
    return executor.SignedInputs(path, path, path, path, path, path, path, path, path, path, path)


def _patch_orchestration(monkeypatch, tmp_path: Path, config: executor.ExecutorConfig, *, fail_public=False):
    plan = _valid_plan()
    plan["atomic_switch"]["expected_previous_config_sha256"] = executor.sha256_file(config.active_site)
    snapshot = SimpleNamespace(digests={"plan.json": "a" * 64})
    manifest = {
        "targets": {
            "backend": {"origin": "http://127.0.0.1:18018"},
            "frontend": {"origin": "http://127.0.0.1:15194"},
        },
        "runtime_requirements": {},
        "toolchain": {"python": "3.14.4"},
    }
    rollback = {
        "release_id": "kolibri-p6",
        "targets": {
            "backend": {"origin": "http://127.0.0.1:18015"},
            "frontend": {"origin": "http://127.0.0.1:15193"},
        },
    }
    verified = executor.VerifiedPlan(plan, manifest, rollback, snapshot)
    runtime = executor.RuntimePaths(
        config.release_root / "kolibri-p7-test",
        tmp_path / "runtime" / "backend",
        tmp_path / "runtime" / "frontend",
        tmp_path / "runtime" / "data",
        tmp_path / "runtime" / "data" / "kolibri.db",
        tmp_path / "runtime" / "data" / "venv",
        os.getuid(),
        os.getgid(),
        Path.home(),
    )
    for path in (runtime.backend_dir, runtime.frontend_dir, runtime.data_dir, runtime.venv_dir / "bin"):
        path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(executor, "snapshot_inputs", lambda *_args: snapshot)
    monkeypatch.setattr(executor, "reverify_plan", lambda *_args: verified)
    monkeypatch.setattr(executor, "stage_release", lambda *_args, **_kwargs: runtime)
    monkeypatch.setattr(executor, "require_runtime_secrets", lambda *_args: None)
    monkeypatch.setattr(executor, "install_locked_environment", lambda *_args: None)
    monkeypatch.setattr(executor, "install_runtime_units", lambda *_args: [])
    def fake_backup(_source, destination):
        destination.touch()
        return {"status": "ok"}

    monkeypatch.setattr(executor, "consistent_sqlite_backup", fake_backup)
    monkeypatch.setattr(executor, "probe_release_identity", lambda *_args, **_kwargs: {"status": "passed"})
    monkeypatch.setattr(executor, "isolated_nginx_test", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(executor, "_service_active", lambda *_args: None)
    monkeypatch.setattr(executor, "probe_rollback_identity", lambda *_args, **_kwargs: {"status": "passed"})
    if fail_public:
        def fail(*_args, **_kwargs):
            raise executor.P7ExecutorError("p7_public_post_gate_failed")
        monkeypatch.setattr(executor, "public_post_gates", fail)
    else:
        monkeypatch.setattr(executor, "public_post_gates", lambda *_args, **_kwargs: {"status": "passed"})
    return lambda *_args: {
        "status": "migrated_verified",
        "schema_head": executor.EXPECTED_SCHEMA_HEAD,
    }


def test_execute_success_switches_once_and_leaves_previous_writer_stopped(monkeypatch, tmp_path: Path):
    config = _executor_config(tmp_path, _dummy_inputs(tmp_path))
    runner = FakeRunner()
    migrate = _patch_orchestration(monkeypatch, tmp_path, config)

    result = executor.execute(config, runner=runner, p7_module=object(), migrate_hook=migrate)

    assert result["status"] == "applied_verified"
    assert result["production_applied"] is True
    assert sum(command == ("systemctl", "reload", "nginx") for command in runner.commands) == 1
    assert ("systemctl", "stop", "kolibri-backend-p6.service") in runner.commands
    assert ("systemctl", "start", "kolibri-backend-p6.service") not in runner.commands
    assert b"127.0.0.1:18018" in config.active_site.read_bytes()


def test_execute_public_failure_restores_exact_p6_bytes_and_service(monkeypatch, tmp_path: Path):
    config = _executor_config(tmp_path, _dummy_inputs(tmp_path))
    original = config.active_site.read_bytes()
    runner = FakeRunner()
    migrate = _patch_orchestration(monkeypatch, tmp_path, config, fail_public=True)

    with pytest.raises(executor.P7ExecutorError, match="p7_public_post_gate_failed"):
        executor.execute(config, runner=runner, p7_module=object(), migrate_hook=migrate)

    assert config.active_site.read_bytes() == original
    assert sum(command == ("systemctl", "reload", "nginx") for command in runner.commands) == 2
    assert ("systemctl", "start", "kolibri-backend-p6.service") in runner.commands
    assert any(command[:3] == ("systemctl", "disable", "--now") for command in runner.commands)
    restart_index = runner.commands.index(("systemctl", "start", "kolibri-backend-p6.service"))
    rollback_reload_index = max(
        index
        for index, command in enumerate(runner.commands)
        if command == ("systemctl", "reload", "nginx")
    )
    assert restart_index < rollback_reload_index
    result_files = list(config.state_root.glob("*/result.json"))
    assert len(result_files) == 1
    assert json.loads(result_files[0].read_text())["status"] == "rolled_back_verified"


def test_execute_partial_candidate_start_is_stopped_and_p6_restarted(monkeypatch, tmp_path: Path):
    config = _executor_config(tmp_path, _dummy_inputs(tmp_path))
    runner = PartialStartFailureRunner()
    migrate = _patch_orchestration(monkeypatch, tmp_path, config)

    with pytest.raises(executor.P7ExecutorError, match="p7_executor_command_failed"):
        executor.execute(config, runner=runner, p7_module=object(), migrate_hook=migrate)

    assert any(command[:3] == ("systemctl", "disable", "--now") for command in runner.commands)
    assert ("systemctl", "start", "kolibri-backend-p6.service") in runner.commands
    assert b"127.0.0.1:18015" in config.active_site.read_bytes()
