from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_legacy_control_plane_authority.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("legacy_control_plane_authority_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_repository_runtime_and_release_manifests_pass_the_gate():
    gate = load_gate()

    assert gate.scan_repository(ROOT) == []


def test_hardcoded_legacy_control_plane_url_fails(tmp_path):
    gate = load_gate()
    write(
        tmp_path / "ops" / "worker.py",
        'CONTROL_URL = "http://10.99.0.2:9101"\n',
    )

    violations = gate.scan_repository(tmp_path)

    assert [(item.path, item.line, item.rule) for item in violations] == [
        ("ops/worker.py", 1, "legacy_control_plane_url")
    ]


def test_hardcoded_legacy_control_plane_identity_fails(tmp_path):
    gate = load_gate()
    write(tmp_path / "scripts" / "runner.py", 'TARGET_NODE = "primary-candidate"\n')

    violations = gate.scan_repository(tmp_path)

    assert any(item.rule == "legacy_control_plane_alias" for item in violations)


def test_release_manifest_rejects_plain_main_control_plane_identity(tmp_path):
    gate = load_gate()
    write(
        tmp_path / "release" / "manifest.json",
        json.dumps(
            {
                "release_id": "release-test",
                "services": [{"node_id": "main", "role": "control_plane"}],
            }
        ),
    )

    violations = gate.scan_repository(tmp_path)

    assert any(
        item.rule == "release_manifest_legacy_control_plane_role"
        for item in violations
    )


def test_release_manifest_accepts_home_authority_and_git_main_ref(tmp_path):
    gate = load_gate()
    write(
        tmp_path / "release" / "manifest.json",
        json.dumps(
            {
                "release_id": "release-test",
                "source_ref": "origin/main",
                "services": [{"node_id": "home", "role": "control_plane"}],
            }
        ),
    )

    assert gate.scan_repository(tmp_path) == []


def test_historical_docs_and_test_fixtures_are_outside_runtime_gate(tmp_path):
    gate = load_gate()
    legacy = 'http://10.99.0.2:9101 primary-candidate\n'
    write(tmp_path / "docs" / "historical-control-plane.md", legacy)
    write(tmp_path / "tests" / "test_legacy_fixture.py", f'FIXTURE = {legacy!r}\n')
    write(tmp_path / "backend" / "tests" / "legacy_fixture.py", f'FIXTURE = {legacy!r}\n')

    assert gate.scan_repository(tmp_path) == []


def test_exact_inline_rust_negative_fixture_is_allowed(tmp_path):
    gate = load_gate()
    write(
        tmp_path / "crates" / "kolibri-core" / "src" / "event_store.rs",
        'let tampered = original.replace("control-plane/home", "control-plane/main");\n',
    )

    assert gate.scan_repository(tmp_path) == []


def test_arbitrary_control_plane_main_source_is_not_treated_as_fixture(tmp_path):
    gate = load_gate()
    write(
        tmp_path / "crates" / "kolibri-core" / "src" / "runtime.rs",
        'let source = "control-plane/main";\n',
    )

    violations = gate.scan_repository(tmp_path)

    assert any(item.rule == "legacy_control_plane_source" for item in violations)


def test_secret_files_are_never_candidates(tmp_path):
    gate = load_gate()
    write(tmp_path / "ops" / "telegram.env", 'URL="http://10.99.0.2:9101"\n')
    write(tmp_path / "ops" / "install-telegram-secret.sh", "primary-candidate\n")

    assert gate.candidate_files(tmp_path) == []
    assert gate.scan_repository(tmp_path) == []
