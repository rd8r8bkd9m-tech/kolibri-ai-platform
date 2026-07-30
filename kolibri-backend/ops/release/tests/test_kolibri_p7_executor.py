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
import threading
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
        app_start, app_end, _ = blocks["/app"]
        app_block = rendered[app_start:app_end]
        assert "auth_request /api/v1/auth/me;" in app_block
        assert "error_page 401 403 = @kolibri_app_login;" in app_block
        assert "location @kolibri_app_login" in rendered
        assert "X-Robots-Tag" in app_block
        assert "kolibri-p7-test" in rendered


def test_render_canary_site_adds_release_prefix_without_touching_production_routes():
    release_id = "kolibri-p7-canary-test"
    rendered = executor.render_canary_site(
        PROXY_SITE,
        release_id=release_id,
        candidate_backend="http://127.0.0.1:18018",
        candidate_frontend="http://127.0.0.1:15194",
    ).decode()

    blocks = executor._location_blocks(rendered)
    original = PROXY_SITE.decode()
    original_blocks = executor._location_blocks(original)
    for route in (*executor.BACKEND_ROUTES, "/"):
        start, end, _ = original_blocks[route]
        rendered_start, rendered_end, _ = blocks[route]
        assert rendered[rendered_start:rendered_end] == original[start:end]

    base = executor.canary_base_path(release_id)
    app_path = f"{base}app"
    assert app_path in blocks
    app_start, app_end, _ = blocks[app_path]
    app_block = rendered[app_start:app_end]
    assert "auth_request " in app_block
    assert "error_page 401 403 = @kolibri_app_login;" in app_block
    assert "location @kolibri_app_login" in rendered
    assert "X-Robots-Tag" in app_block
    for route in executor.BACKEND_ROUTES:
        start, end, _ = blocks[f"{base}{route.lstrip('/')}"]
        assert executor._proxy_pass(rendered[start:end]) == f"http://127.0.0.1:18018{route}"
    start, end, _ = blocks[base]
    assert executor._proxy_pass(rendered[start:end]) == "http://127.0.0.1:15194"
    assert f"X-Forwarded-Prefix {base.rstrip('/')}" in rendered

    with pytest.raises(executor.P7ExecutorError, match="p7_canary_route_already_exists"):
        executor.render_canary_site(
            rendered.encode(),
            release_id=release_id,
            candidate_backend="http://127.0.0.1:18018",
            candidate_frontend="http://127.0.0.1:15194",
        )


def test_render_canary_site_uses_preferred_prefix_with_existing_regex_asset_location():
    active = b"""server {
    location /api/v1/ { proxy_pass http://127.0.0.1:18015; }
    location /api/ { proxy_pass http://127.0.0.1:18015; }
    location /v1/ { proxy_pass http://127.0.0.1:18015; }
    location /ws/ { proxy_pass http://127.0.0.1:18015; }
    location ~* \\.(?:js|css)$ {
        expires 1y;
        add_header Cache-Control public;
    }
    location / { proxy_pass http://127.0.0.1:15193; }
}
"""
    release_id = "kolibri-p7-canary-assets"

    rendered = executor.render_canary_site(
        active,
        release_id=release_id,
        candidate_backend="http://127.0.0.1:18018",
        candidate_frontend="http://127.0.0.1:15194",
    ).decode()

    base = executor.canary_base_path(release_id)
    assert f"location ^~ {base}assets/" not in rendered
    assert f"location ^~ {base}api/" in rendered
    assert f"location ^~ {base} {{" in rendered
    assert "location ~* \\.(?:js|css)$" in rendered
    assert "expires 1y;" in rendered
    original = active.decode()
    rendered_blocks = executor._location_blocks(rendered)
    original_blocks = executor._location_blocks(original)
    for route in (*executor.BACKEND_ROUTES, "/"):
        start, end, _ = original_blocks[route]
        rendered_start, rendered_end, _ = rendered_blocks[route]
        assert rendered[rendered_start:rendered_end] == original[start:end]


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
    assert "--base-path / " in frontend_unit
    assert "@@" not in backend_unit + frontend_unit


def test_runtime_units_accept_only_release_bound_canary_base_path(tmp_path: Path):
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
    user = pwd.getpwuid(os.getuid()).pw_name
    group = grp.getgrgid(os.getgid()).gr_name
    config = executor.dataclasses.replace(
        _executor_config(config_root, _dummy_inputs(tmp_path)),
        runtime_user=user,
        runtime_group=group,
        frontend_base_path="/__canary/kolibri-p7-unit-test/",
    )

    executor.install_runtime_units(runtime, config)

    frontend_unit = (config.systemd_dir / executor.FRONTEND_SERVICE).read_text()
    assert "--base-path /__canary/kolibri-p7-unit-test/" in frontend_unit

    bad_config = executor.dataclasses.replace(
        config,
        frontend_base_path="/__canary/other-release/",
    )
    with pytest.raises(executor.P7ExecutorError, match="p7_frontend_base_path_invalid"):
        executor.install_runtime_units(runtime, bad_config)


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


def test_online_sqlite_snapshot_does_not_require_draining_writer(tmp_path: Path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE sample(value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('committed')")
    destination = tmp_path / "candidate" / "kolibri.db"
    destination.parent.mkdir()
    writer = sqlite3.connect(source)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO sample VALUES ('uncommitted')")
    try:
        evidence = executor.online_sqlite_snapshot(source, destination)
    finally:
        writer.rollback()
        writer.close()

    assert evidence["writer_drained"] is False
    assert evidence["online_snapshot"] is True
    assert evidence["quick_check"] == "ok"
    assert evidence["foreign_key_check"] == "ok"
    assert evidence["backup_sha256"] == executor.sha256_file(destination)
    with sqlite3.connect(destination) as connection:
        rows = connection.execute("SELECT value FROM sample").fetchall()
    assert rows == [("committed",)]


def test_online_sqlite_snapshot_allows_wal_writer_commit_during_backup(tmp_path: Path):
    source = tmp_path / "source.db"
    blob = "x" * 4096
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA page_size=512")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE sample(batch TEXT, item INTEGER, payload TEXT)")
        for batch in range(160):
            connection.execute("INSERT INTO sample VALUES (?, ?, ?)", (f"seed-{batch}", 0, blob))
            connection.execute("INSERT INTO sample VALUES (?, ?, ?)", (f"seed-{batch}", 1, blob))
    destination = tmp_path / "candidate" / "kolibri.db"
    destination.parent.mkdir()
    progress_seen = threading.Event()
    backup_progress_triggered = threading.Event()
    commit_done = threading.Event()
    hook_timeout = threading.Event()
    committed_batches: list[str] = []

    def writer() -> None:
        progress_seen.wait(timeout=5)
        with sqlite3.connect(source, timeout=5.0) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            for index in range(3):
                batch = f"writer-{index}"
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("INSERT INTO sample VALUES (?, ?, ?)", (batch, 0, blob))
                connection.execute("INSERT INTO sample VALUES (?, ?, ?)", (batch, 1, blob))
                connection.commit()
                committed_batches.append(batch)
        commit_done.set()

    thread = threading.Thread(target=writer)
    thread.start()

    def progress(_status: int, remaining: int, _total: int) -> None:
        if remaining > 0 and not progress_seen.is_set():
            backup_progress_triggered.set()
            progress_seen.set()
            if not commit_done.wait(timeout=5):
                hook_timeout.set()

    try:
        evidence = executor.online_sqlite_snapshot(
            source,
            destination,
            deadline_seconds=15,
            backup_pages=1,
            backup_sleep=0.001,
            progress_hook=progress,
        )
    finally:
        progress_seen.set()
        thread.join(timeout=5)

    assert not thread.is_alive()
    assert backup_progress_triggered.is_set()
    assert not hook_timeout.is_set()
    assert committed_batches == ["writer-0", "writer-1", "writer-2"]
    assert evidence["quick_check"] == "ok"
    assert evidence["foreign_key_check"] == "ok"
    with sqlite3.connect(destination) as connection:
        candidate_batches = dict(
            connection.execute(
                "SELECT batch, COUNT(*) FROM sample GROUP BY batch HAVING batch LIKE 'writer-%'"
            ).fetchall()
        )
        seed_count = connection.execute(
            "SELECT COUNT(*) FROM sample WHERE batch LIKE 'seed-%'"
        ).fetchone()[0]
    assert seed_count == 320
    assert all(count == 2 for count in candidate_batches.values())


@pytest.mark.parametrize("deadline_pragma", ["quick_check", "foreign_key_check"])
def test_online_sqlite_snapshot_deadline_interrupts_candidate_pragmas(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    deadline_pragma: str,
):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("CREATE TABLE parent(id INTEGER PRIMARY KEY)")
        connection.execute("CREATE TABLE child(parent_id INTEGER REFERENCES parent(id))")
        connection.execute("INSERT INTO parent VALUES (1)")
        connection.execute("INSERT INTO child VALUES (1)")
    destination = tmp_path / "candidate" / "kolibri.db"
    destination.parent.mkdir()
    now = {"value": 0.0}
    target_connections: list[RecordingConnection] = []
    real_connect = sqlite3.connect

    class RecordingConnection(sqlite3.Connection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.progress_handler_calls: list[tuple[object, int]] = []

        def set_progress_handler(self, progress_handler, n):
            self.progress_handler_calls.append((progress_handler, n))
            return super().set_progress_handler(progress_handler, n)

        def execute(self, sql, parameters=(), /):
            if isinstance(sql, str) and sql == f"PRAGMA {deadline_pragma}":
                now["value"] = 2.0
            return super().execute(sql, parameters)

    def connect(database, *args, **kwargs):
        if kwargs.get("uri"):
            return real_connect(database, *args, **kwargs)
        connection = real_connect(database, *args, factory=RecordingConnection, **kwargs)
        target_connections.append(connection)
        return connection

    monkeypatch.setattr(executor.time, "monotonic", lambda: now["value"])
    monkeypatch.setattr(executor.sqlite3, "connect", connect)

    with pytest.raises(executor.P7ExecutorError, match="p7_sqlite_online_snapshot_deadline_exceeded"):
        executor.online_sqlite_snapshot(source, destination, deadline_seconds=1.0)

    assert len(target_connections) == 1
    progress_calls = target_connections[0].progress_handler_calls
    assert progress_calls[-2][1] == 1
    assert progress_calls[-2][0] is not None
    assert progress_calls[-1] == (None, 0)
    assert not destination.exists()


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
        "activation_mode": "production",
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


def test_reverify_plan_rejects_legacy_or_tampered_activation_mode(tmp_path: Path):
    signed_plan = _valid_plan()
    manifest = {
        "targets": {
            "backend": {"port": 18018, "origin": "http://127.0.0.1:18018"},
            "frontend": {"port": 15194, "origin": "http://127.0.0.1:15194"},
        },
        "toolchain": {"lockfiles": {executor.REQUIREMENTS_LOCK: {"sha256": "4" * 64}}},
    }
    rollback = {"release_id": "kolibri-p6", "targets": {}}

    class FakeP7:
        @staticmethod
        def canonical_json(payload):
            return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

        @staticmethod
        def paired_switch_plan(**_kwargs):
            return signed_plan

        @staticmethod
        def load_manifest(path):
            return (manifest, path / "release-manifest.json", "1" * 64) if path.name == "candidate" else (
                rollback,
                path / "release-manifest.json",
                "2" * 64,
            )

    legacy = dict(signed_plan)
    legacy.pop("activation_mode")
    with pytest.raises(executor.P7ExecutorError, match="p7_plan_recomputation_mismatch"):
        executor.reverify_plan(_snapshot(tmp_path, legacy), FakeP7)

    tampered = {
        **signed_plan,
        "activation_mode": "canary",
        "canary_base_path": executor.canary_base_path(signed_plan["release_id"]),
    }
    with pytest.raises(executor.P7ExecutorError, match="p7_plan_recomputation_mismatch"):
        executor.reverify_plan(_snapshot(tmp_path, tampered), FakeP7)


def test_reverify_plan_rejects_ambiguous_canary_base_path(tmp_path: Path):
    canary_plan = {
        **_valid_plan(),
        "activation_mode": "canary",
        "canary_base_path": "/__canary/other-release/",
    }
    manifest = {
        "targets": {
            "backend": {"port": 18018, "origin": "http://127.0.0.1:18018"},
            "frontend": {"port": 15194, "origin": "http://127.0.0.1:15194"},
        },
        "toolchain": {"lockfiles": {executor.REQUIREMENTS_LOCK: {"sha256": "4" * 64}}},
    }
    rollback = {"release_id": "kolibri-p6", "targets": {}}

    class FakeP7:
        @staticmethod
        def canonical_json(payload):
            return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

        @staticmethod
        def paired_switch_plan(**_kwargs):
            return canary_plan

        @staticmethod
        def load_manifest(path):
            return (manifest, path / "release-manifest.json", "1" * 64) if path.name == "candidate" else (
                rollback,
                path / "release-manifest.json",
                "2" * 64,
            )

    with pytest.raises(executor.P7ExecutorError, match="p7_plan_canary_base_path_invalid"):
        executor.reverify_plan(_snapshot(tmp_path, canary_plan), FakeP7)


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


def test_darwin_executor_requires_explicit_apple_capability_worker(monkeypatch):
    monkeypatch.setattr(executor.platform, "system", lambda: "Darwin")
    monkeypatch.delenv("KOLIBRI_APPLE_CAPABILITY_WORKER", raising=False)

    with pytest.raises(executor.P7ExecutorError, match="p7_darwin_requires_apple_capability_worker"):
        executor.require_p7_runtime_host()

    monkeypatch.setenv("KOLIBRI_APPLE_CAPABILITY_WORKER", "1")
    executor.require_p7_runtime_host()


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
    ASSET_PATH = "/assets/index-a1b2c3d4.js"

    def __init__(
        self,
        base_url: str,
        *,
        bad_header: bool = False,
        prefix: str = "/",
        header_mode: str = "both",
    ):
        self.base_url = base_url
        self.bad_header = bad_header
        self.prefix = prefix
        self.header_mode = header_mode
        self.paths: list[tuple[str, str]] = []

    def request(self, method: str, path: str, payload=None):
        self.paths.append((method, path))
        release = "wrong" if self.bad_header else "kolibri-p7-test"
        release_headers = {"x-kolibri-release": release}
        if self.header_mode == "both":
            release_headers["x-kolibri-release-id"] = release
        elif self.header_mode == "alias_only":
            release_headers = {"x-kolibri-release-id": release}
        elif self.header_mode == "conflicting":
            release_headers["x-kolibri-release-id"] = "kolibri-p7-other"

        def expected(relative: str) -> str:
            return relative if self.prefix == "/" else self.prefix + relative.lstrip("/")

        if path == expected("/api/health"):
            return executor.HttpResult(
                200,
                {**release_headers, "content-type": "application/json"},
                b'{"status":"ok","release_id":"kolibri-p7-test"}',
            )
        if path == expected("/"):
            html_asset_path = expected(self.ASSET_PATH) if self.prefix != "/" else self.ASSET_PATH
            body = (
                f"<html><script type=\"module\" src=\"{html_asset_path}\"></script>"
                "kolibri-p7-test</html>"
            ).encode("utf-8")
            return executor.HttpResult(200, {**release_headers, "content-type": "text/html"}, body)
        if path == expected(self.ASSET_PATH):
            return executor.HttpResult(
                200,
                {**release_headers, "content-type": "text/javascript; charset=utf-8"},
                b"console.log('kolibri-p7-test');",
            )
        if path == expected("/api/v1/__kolibri_p7_missing__"):
            return executor.HttpResult(
                404,
                {**release_headers, "content-type": "application/json"},
                b'{"detail":"not found"}',
            )
        if method == "POST" and path == expected("/api/v1/shell/bootstrap"):
            return executor.HttpResult(
                200,
                {**release_headers, "content-type": "application/json"},
                b'{"session_type":"anonymous"}',
            )
        raise AssertionError((method, path, payload))


def test_public_post_gates_require_exact_release_on_every_surface():
    passed = executor.public_post_gates(
        "https://kolibriai.invalid",
        "kolibri-p7-test",
        client_factory=lambda base: RouteClient(base),
    )
    assert passed["status"] == "passed"
    assert passed["frontend_asset"]["production_path"] == RouteClient.ASSET_PATH
    assert passed["frontend_asset"]["request_path"] == RouteClient.ASSET_PATH
    assert passed["frontend_asset"]["content_type"] == "text/javascript"

    with pytest.raises(executor.P7ExecutorError, match="p7_public_post_gate_failed"):
        executor.public_post_gates(
            "https://kolibriai.invalid",
            "kolibri-p7-test",
            client_factory=lambda base: RouteClient(base, bad_header=True),
        )


def test_public_post_gates_require_canonical_release_header_and_reject_alias_conflict():
    canonical_only = executor.public_post_gates(
        "https://kolibriai.invalid",
        "kolibri-p7-test",
        client_factory=lambda base: RouteClient(base, header_mode="canonical_only"),
    )
    assert canonical_only["status"] == "passed"

    for header_mode in ("alias_only", "conflicting"):
        with pytest.raises(executor.P7ExecutorError, match="p7_public_post_gate_failed"):
            executor.public_post_gates(
                "https://kolibriai.invalid",
                "kolibri-p7-test",
                client_factory=lambda base, mode=header_mode: RouteClient(base, header_mode=mode),
            )


def test_public_post_gates_are_prefix_aware_for_canary():
    client = RouteClient(
        "https://kolibriai.invalid",
        prefix="/__canary/kolibri-p7-test/",
    )

    passed = executor.public_post_gates(
        "https://kolibriai.invalid",
        "kolibri-p7-test",
        base_path="/__canary/kolibri-p7-test/",
        client_factory=lambda _base: client,
    )

    assert passed["status"] == "passed"
    assert passed["frontend_asset"]["production_path"] == RouteClient.ASSET_PATH
    assert passed["frontend_asset"]["request_path"] == f"/__canary/kolibri-p7-test{RouteClient.ASSET_PATH}"
    assert client.paths == [
        ("GET", "/__canary/kolibri-p7-test/api/health"),
        ("GET", "/__canary/kolibri-p7-test/"),
        ("GET", "/__canary/kolibri-p7-test/assets/index-a1b2c3d4.js"),
        ("GET", "/__canary/kolibri-p7-test/api/v1/__kolibri_p7_missing__"),
        ("POST", "/__canary/kolibri-p7-test/api/v1/shell/bootstrap"),
    ]
    with pytest.raises(executor.P7ExecutorError, match="p7_canary_base_path_invalid"):
        executor.public_post_gates(
            "https://kolibriai.invalid",
            "kolibri-p7-test",
            base_path="/__canary/other-release/",
            client_factory=lambda _base: client,
        )


def test_public_post_gates_canary_resolves_relative_asset_under_signed_base():
    class RelativeAssetCanaryClient(RouteClient):
        def request(self, method: str, path: str, payload=None):
            if path == self.prefix:
                self.paths.append((method, path))
                body = b'<html><script type="module" src="./assets/index-a1b2c3d4.js"></script>kolibri-p7-test</html>'
                headers = {
                    "x-kolibri-release": "kolibri-p7-test",
                    "x-kolibri-release-id": "kolibri-p7-test",
                    "content-type": "text/html",
                }
                return executor.HttpResult(200, headers, body)
            return super().request(method, path, payload)

    client = RelativeAssetCanaryClient(
        "https://kolibriai.invalid",
        prefix="/__canary/kolibri-p7-test/",
    )

    passed = executor.public_post_gates(
        "https://kolibriai.invalid",
        "kolibri-p7-test",
        base_path="/__canary/kolibri-p7-test/",
        client_factory=lambda _base: client,
    )

    assert passed["frontend_asset"]["request_path"] == "/__canary/kolibri-p7-test/assets/index-a1b2c3d4.js"
    assert client.paths[2] == ("GET", "/__canary/kolibri-p7-test/assets/index-a1b2c3d4.js")


def test_public_post_gates_canary_rejects_absolute_root_asset_outside_signed_base():
    class RootAbsoluteAssetCanaryClient(RouteClient):
        def request(self, method: str, path: str, payload=None):
            if path == self.prefix:
                self.paths.append((method, path))
                body = (
                    f"<html><script type=\"module\" src=\"{self.ASSET_PATH}\"></script>"
                    "kolibri-p7-test</html>"
                ).encode("utf-8")
                headers = {
                    "x-kolibri-release": "kolibri-p7-test",
                    "x-kolibri-release-id": "kolibri-p7-test",
                    "content-type": "text/html",
                }
                return executor.HttpResult(200, headers, body)
            if path.endswith(self.ASSET_PATH):
                raise AssertionError(f"unexpected rewritten asset probe: {path}")
            return super().request(method, path, payload)

    client = RootAbsoluteAssetCanaryClient(
        "https://kolibriai.invalid",
        prefix="/__canary/kolibri-p7-test/",
    )

    with pytest.raises(executor.P7ExecutorError, match="p7_frontend_hashed_asset_missing"):
        executor.public_post_gates(
            "https://kolibriai.invalid",
            "kolibri-p7-test",
            base_path="/__canary/kolibri-p7-test/",
            client_factory=lambda _base: client,
        )

    assert client.paths == [
        ("GET", "/__canary/kolibri-p7-test/api/health"),
        ("GET", "/__canary/kolibri-p7-test/"),
    ]


def test_public_post_gates_reject_html_or_empty_hashed_asset():
    class HtmlAssetClient(RouteClient):
        def request(self, method: str, path: str, payload=None):
            if path == self.ASSET_PATH:
                self.paths.append((method, path))
                return executor.HttpResult(
                    200,
                    {
                        "x-kolibri-release": "kolibri-p7-test",
                        "x-kolibri-release-id": "kolibri-p7-test",
                        "content-type": "text/html",
                    },
                    b"<html></html>",
                )
            return super().request(method, path, payload)

    with pytest.raises(executor.P7ExecutorError, match="p7_public_asset_gate_failed"):
        executor.public_post_gates(
            "https://kolibriai.invalid",
            "kolibri-p7-test",
            client_factory=lambda base: HtmlAssetClient(base),
        )


def test_direct_release_identity_probe_allows_canary_frontend_prefix():
    paths: list[tuple[str, str]] = []

    class DirectClient:
        def __init__(self, base_url: str):
            self.base_url = base_url

        def request(self, method: str, path: str, payload=None):
            paths.append((self.base_url, path))
            headers = {"x-kolibri-release": "kolibri-p7-test"}
            if self.base_url.endswith(":18018") and path == "/api/health":
                return executor.HttpResult(200, headers, b'{"status":"ok","release_id":"kolibri-p7-test"}')
            if self.base_url.endswith(":15194") and path == "/__canary/kolibri-p7-test/":
                return executor.HttpResult(200, headers, b"kolibri-p7-test")
            raise AssertionError((method, path, payload))

    passed = executor.probe_release_identity(
        "http://127.0.0.1:18018",
        "http://127.0.0.1:15194",
        "kolibri-p7-test",
        frontend_path="/__canary/kolibri-p7-test/",
        client_factory=DirectClient,
    )

    assert passed["status"] == "passed"
    assert paths == [
        ("http://127.0.0.1:18018", "/api/health"),
        ("http://127.0.0.1:15194", "/__canary/kolibri-p7-test/"),
    ]


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


def _patch_orchestration(
    monkeypatch,
    tmp_path: Path,
    config: executor.ExecutorConfig,
    *,
    activation_mode: str = "production",
    fail_public=False,
    fail_production_regression=False,
    capture: dict | None = None,
    unit_backups: list[executor.UnitBackup] | None = None,
):
    capture = capture if capture is not None else {}
    plan = _valid_plan()
    plan["atomic_switch"]["expected_previous_config_sha256"] = executor.sha256_file(config.active_site)
    plan["activation_mode"] = activation_mode
    if activation_mode == "canary":
        plan["canary_base_path"] = executor.canary_base_path(plan["release_id"])
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
    def fake_install_runtime_units(_runtime, runtime_config):
        capture["frontend_base_path"] = runtime_config.frontend_base_path
        if unit_backups is not None:
            for backup in unit_backups:
                backup.path.write_text("candidate unit\n", encoding="utf-8")
        return unit_backups if unit_backups is not None else []

    monkeypatch.setattr(executor, "install_runtime_units", fake_install_runtime_units)

    def fake_backup(_source, destination):
        destination.touch()
        capture["database_backup"] = "consistent"
        return {"status": "ok", "writer_drained": True}

    def fake_online_snapshot(_source, destination):
        destination.touch()
        capture["database_backup"] = "online"
        return {"status": "ok", "writer_drained": False, "online_snapshot": True}

    monkeypatch.setattr(executor, "consistent_sqlite_backup", fake_backup)
    monkeypatch.setattr(executor, "online_sqlite_snapshot", fake_online_snapshot)

    def fake_probe_release_identity(*_args, **kwargs):
        capture["direct_frontend_path"] = kwargs.get("frontend_path", "/")
        return {"status": "passed"}

    monkeypatch.setattr(executor, "probe_release_identity", fake_probe_release_identity)
    monkeypatch.setattr(executor, "isolated_nginx_test", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(executor, "_service_active", lambda *_args: None)
    def fake_probe_rollback_identity(_base_url, release_id, **_kwargs):
        capture.setdefault("rollback_identity_release_ids", []).append(release_id)
        if fail_production_regression and len(capture["rollback_identity_release_ids"]) == 1:
            raise executor.P7ExecutorError("p7_rollback_identity_probe_failed")
        capture["rollback_identity_probed"] = True
        return {"status": "passed", "release_id": release_id}

    monkeypatch.setattr(executor, "probe_rollback_identity", fake_probe_rollback_identity)
    if fail_public:
        def fail(*_args, **_kwargs):
            raise executor.P7ExecutorError("p7_public_post_gate_failed")
        monkeypatch.setattr(executor, "public_post_gates", fail)
    else:
        def fake_public_post_gates(*_args, **kwargs):
            capture["public_base_path"] = kwargs.get("base_path", "/")
            return {"status": "passed"}

        monkeypatch.setattr(executor, "public_post_gates", fake_public_post_gates)
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


def test_execute_canary_success_never_stops_p6_and_only_inserts_prefix(monkeypatch, tmp_path: Path):
    config = executor.dataclasses.replace(
        _executor_config(tmp_path, _dummy_inputs(tmp_path)),
        frontend_base_path="/__canary/unsigned-runtime-value/",
    )
    original = config.active_site.read_bytes()
    runner = FakeRunner()
    capture: dict = {}
    migrate = _patch_orchestration(
        monkeypatch,
        tmp_path,
        config,
        activation_mode="canary",
        capture=capture,
    )
    real_render_canary = executor.render_canary_site

    def wrapped_render_canary(*args, **kwargs):
        capture["render_canary_used"] = True
        return real_render_canary(*args, **kwargs)

    monkeypatch.setattr(executor, "render_canary_site", wrapped_render_canary)

    result = executor.execute(config, runner=runner, p7_module=object(), migrate_hook=migrate)

    canary_base = executor.canary_base_path("kolibri-p7-test")
    assert result["status"] == "canary_applied_verified"
    assert result["activation_mode"] == "canary"
    assert result["production_applied"] is False
    assert result["canary_base_path"] == canary_base
    assert result["production_regression_gate"] == {"status": "passed", "release_id": "kolibri-p6"}
    assert capture["rollback_identity_release_ids"] == ["kolibri-p6"]
    assert capture["database_backup"] == "online"
    assert capture["frontend_base_path"] == canary_base
    assert capture["direct_frontend_path"] == canary_base
    assert capture["public_base_path"] == canary_base
    assert capture["render_canary_used"] is True
    assert sum(command == ("systemctl", "reload", "nginx") for command in runner.commands) == 1
    assert ("systemctl", "stop", "kolibri-backend-p6.service") not in runner.commands
    assert ("systemctl", "start", "kolibri-backend-p6.service") not in runner.commands

    rendered = config.active_site.read_bytes().decode()
    original_text = original.decode()
    rendered_blocks = executor._location_blocks(rendered)
    original_blocks = executor._location_blocks(original_text)
    for route in (*executor.BACKEND_ROUTES, "/"):
        start, end, _ = original_blocks[route]
        rendered_start, rendered_end, _ = rendered_blocks[route]
        assert rendered[rendered_start:rendered_end] == original_text[start:end]
    for route in executor.BACKEND_ROUTES:
        start, end, _ = rendered_blocks[f"{canary_base}{route.lstrip('/')}"]
        assert executor._proxy_pass(rendered[start:end]) == f"http://127.0.0.1:18018{route}"
    start, end, _ = rendered_blocks[canary_base]
    assert executor._proxy_pass(rendered[start:end]) == "http://127.0.0.1:15194"


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


def test_execute_canary_failure_rolls_back_only_canary_and_candidate_units(monkeypatch, tmp_path: Path):
    config = _executor_config(tmp_path, _dummy_inputs(tmp_path))
    original = config.active_site.read_bytes()
    backend_unit = config.systemd_dir / executor.BACKEND_SERVICE
    frontend_unit = config.systemd_dir / executor.FRONTEND_SERVICE
    backend_unit.write_text("old backend unit\n", encoding="utf-8")
    frontend_unit.write_text("old frontend unit\n", encoding="utf-8")
    unit_backups = [
        executor.UnitBackup(backend_unit, True, backend_unit.read_bytes(), backend_unit.lstat()),
        executor.UnitBackup(frontend_unit, True, frontend_unit.read_bytes(), frontend_unit.lstat()),
    ]
    runner = FakeRunner()
    capture: dict = {}
    migrate = _patch_orchestration(
        monkeypatch,
        tmp_path,
        config,
        activation_mode="canary",
        fail_public=True,
        capture=capture,
        unit_backups=unit_backups,
    )

    with pytest.raises(executor.P7ExecutorError, match="p7_public_post_gate_failed"):
        executor.execute(config, runner=runner, p7_module=object(), migrate_hook=migrate)

    assert config.active_site.read_bytes() == original
    assert backend_unit.read_text(encoding="utf-8") == "old backend unit\n"
    assert frontend_unit.read_text(encoding="utf-8") == "old frontend unit\n"
    assert capture["database_backup"] == "online"
    assert capture["rollback_identity_probed"] is True
    assert sum(command == ("systemctl", "reload", "nginx") for command in runner.commands) == 2
    assert ("systemctl", "stop", "kolibri-backend-p6.service") not in runner.commands
    assert ("systemctl", "start", "kolibri-backend-p6.service") not in runner.commands
    assert any(command[:3] == ("systemctl", "disable", "--now") for command in runner.commands)
    result_files = list(config.state_root.glob("*/result.json"))
    assert len(result_files) == 1
    audit = json.loads(result_files[0].read_text())
    assert audit["status"] == "canary_rolled_back_verified"
    assert audit["activation_mode"] == "canary"
    assert audit["canary_base_path"] == executor.canary_base_path("kolibri-p7-test")


def test_execute_canary_regression_probe_failure_rolls_back_only_canary(monkeypatch, tmp_path: Path):
    config = _executor_config(tmp_path, _dummy_inputs(tmp_path))
    original = config.active_site.read_bytes()
    runner = FakeRunner()
    capture: dict = {}
    migrate = _patch_orchestration(
        monkeypatch,
        tmp_path,
        config,
        activation_mode="canary",
        fail_production_regression=True,
        capture=capture,
    )

    with pytest.raises(executor.P7ExecutorError, match="p7_rollback_identity_probe_failed"):
        executor.execute(config, runner=runner, p7_module=object(), migrate_hook=migrate)

    assert config.active_site.read_bytes() == original
    assert capture["public_base_path"] == executor.canary_base_path("kolibri-p7-test")
    assert capture["rollback_identity_release_ids"] == ["kolibri-p6", "kolibri-p6"]
    assert sum(command == ("systemctl", "reload", "nginx") for command in runner.commands) == 2
    assert ("systemctl", "stop", "kolibri-backend-p6.service") not in runner.commands
    assert ("systemctl", "start", "kolibri-backend-p6.service") not in runner.commands
    assert any(command[:3] == ("systemctl", "disable", "--now") for command in runner.commands)
    result_files = list(config.state_root.glob("*/result.json"))
    assert len(result_files) == 1
    audit = json.loads(result_files[0].read_text())
    assert audit["status"] == "canary_rolled_back_verified"
    assert audit["failure_code"] == "p7_rollback_identity_probe_failed"


def test_execute_partial_candidate_start_is_stopped_and_p6_restarted(monkeypatch, tmp_path: Path):
    config = _executor_config(tmp_path, _dummy_inputs(tmp_path))
    runner = PartialStartFailureRunner()
    migrate = _patch_orchestration(monkeypatch, tmp_path, config)

    with pytest.raises(executor.P7ExecutorError, match="p7_executor_command_failed"):
        executor.execute(config, runner=runner, p7_module=object(), migrate_hook=migrate)

    assert any(command[:3] == ("systemctl", "disable", "--now") for command in runner.commands)
    assert ("systemctl", "start", "kolibri-backend-p6.service") in runner.commands
    assert b"127.0.0.1:18015" in config.active_site.read_bytes()
