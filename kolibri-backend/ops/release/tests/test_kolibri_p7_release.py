from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile

import pytest


SCRIPT = Path(__file__).parents[1] / "kolibri_p7_release.py"
SPEC = importlib.util.spec_from_file_location("kolibri_p7_release", SCRIPT)
assert SPEC and SPEC.loader
p7 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = p7
SPEC.loader.exec_module(p7)


def _run(*command: str, cwd: Path) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def source_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    (repo / "kolibri-backend" / "app").mkdir(parents=True)
    (repo / "kolibri-v2").mkdir()
    (repo / ".gitignore").write_text(
        "kolibri-v2/dist/\nkolibri-backend/*.db\nkolibri-backend/*.schema.lock\n",
        encoding="utf-8",
    )
    (repo / "kolibri-backend" / "app" / "main.py").write_text(
        "print('kolibri')\n", encoding="utf-8"
    )
    (repo / "kolibri-backend" / "requirements.txt").write_text(
        "fastapi==1.0\n", encoding="utf-8"
    )
    (repo / "kolibri-v2" / "package.json").write_text(
        '{"scripts":{"build":"true"}}\n', encoding="utf-8"
    )
    _run("git", "init", "-q", cwd=repo)
    _run("git", "config", "user.email", "release-test@kolibri.invalid", cwd=repo)
    _run("git", "config", "user.name", "Kolibri release test", cwd=repo)
    _run("git", "add", ".", cwd=repo)
    _run("git", "commit", "-qm", "test source", cwd=repo)
    return repo


def fake_frontend_builder(repo: Path, release_id: str, _npm: str) -> None:
    dist = repo / "kolibri-v2" / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text(
        f"<html><script src='/assets/app.js'></script>{release_id}</html>\n",
        encoding="utf-8",
    )
    (dist / "assets").mkdir(exist_ok=True)
    (dist / "assets" / "app.js").write_text(
        f"window.KOLIBRI_RELEASE_ID={release_id!r};\n", encoding="utf-8"
    )


def _ssh_material(
    tmp_path: Path,
    name: str,
    identity: str,
) -> tuple[Path, Path, str, str]:
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        pytest.skip("ssh-keygen is unavailable")
    key = tmp_path / name
    result = subprocess.run(
        (ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(key)),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("ephemeral Ed25519 key generation is unavailable")
    key.chmod(0o600)
    public_parts = key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed = tmp_path / f"{name}.allowed_signers"
    allowed.write_text(
        f"{identity} {public_parts[0]} {public_parts[1]}\n", encoding="utf-8"
    )
    allowed.chmod(0o600)
    return key, allowed, identity, ssh_keygen


@pytest.fixture
def ssh_material(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, str, str]:
    material = _ssh_material(tmp_path, "release-key", p7.OWNER_SIGNER_IDENTITY)
    monkeypatch.setattr(p7, "OWNER_TRUST_ROOT", material[1])
    monkeypatch.setattr(p7, "TRUST_ROOT_REQUIRED_UID", os.getuid())
    return material


@pytest.fixture
def collector_material(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, str, str]:
    material = _ssh_material(tmp_path, "collector-key", p7.COLLECTOR_SIGNER_IDENTITY)
    monkeypatch.setattr(p7, "COLLECTOR_TRUST_ROOT", material[1])
    monkeypatch.setattr(p7, "TRUST_ROOT_REQUIRED_UID", os.getuid())
    return material


def write_canonical(path: Path, payload: dict) -> Path:
    path.write_bytes(p7.canonical_json(payload) + b"\n")
    return path


def sign_document(path: Path, key: Path, namespace: str, ssh_keygen: str) -> Path:
    signature = Path(f"{path}.sig")
    signature.unlink(missing_ok=True)
    result = subprocess.run(
        (ssh_keygen, "-Y", "sign", "-f", str(key), "-n", namespace, str(path)),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    assert result.returncode == 0
    assert signature.is_file()
    return signature


def build_candidate(
    source_repo: Path,
    tmp_path: Path,
    *,
    signed: tuple[Path, Path, str, str] | None = None,
    release_id: str = "kolibri-p7-test",
) -> tuple[dict, Path]:
    kwargs = {}
    if signed:
        key, _allowed, _identity, ssh_keygen = signed
        kwargs = {
            "signing_key": key,
            "ssh_keygen": ssh_keygen,
        }
    result = p7.build_release(
        repo=source_repo,
        output_root=tmp_path / "releases",
        release_id=release_id,
        frontend_builder=fake_frontend_builder,
        **kwargs,
    )
    return result, Path(result["release_dir"])


def valid_gate_evidence(release_dir: Path) -> dict:
    manifest, _, manifest_sha = p7.load_manifest(release_dir)
    release_id = manifest["release_id"]
    return {
        "schema_version": p7.GATE_SCHEMA_VERSION,
        "release_id": release_id,
        "manifest_sha256": manifest_sha,
        "collector": {
            "identity": p7.COLLECTOR_SIGNER_IDENTITY,
            "implementation": "kolibri-p7-gate-collector",
            "version": "1.0.0",
            "run_id": "gate-run-p7-test",
            "target": {
                "release_id": release_id,
                "manifest_sha256": manifest_sha,
                "backend_origin": manifest["targets"]["backend"]["origin"],
                "frontend_origin": manifest["targets"]["frontend"]["origin"],
            },
        },
        "results": {
            "release_identity": {
                "status": "passed",
                "backend_release_id": release_id,
                "frontend_release_id": release_id,
                "response_header_release_id": release_id,
            },
            "estimate_create_regional": {
                "status": "passed",
                "http_status": 201,
                "estimate_id": "estimate-p7",
                "individualized_scope": True,
                "template_reuse_detected": False,
                "truth_status": "source_backed",
                "evidence_count": 4,
            },
            "estimate_recalculate": {
                "status": "passed",
                "http_status": 200,
                "server_decimal_recalculation": True,
                "version_before": 1,
                "version_after": 2,
                "total_before": "92890.58",
                "total_after": "139335.87",
                "persisted_after_reload": True,
            },
            "estimate_revisions": {
                "status": "passed",
                "http_status": 200,
                "revision_count": 2,
                "previous_revision_immutable": True,
            },
            "estimate_pdf": {
                "status": "passed",
                "http_status": 200,
                "content_type": "application/pdf",
                "magic": "%PDF-",
                "size_bytes": 13900,
                "sha256": "a" * 64,
            },
            "capability_registry": {
                "status": "passed",
                "http_status": 200,
                "source": "backend_runtime_registry",
                "release_id": release_id,
                "probe_ttl_seconds": 25200,
                "release_bound": True,
                "statuses": ["available", "degraded", "unavailable"],
                "invocable_requires_live_probe": True,
                "capability_count": 18,
            },
            "chat_durable_stream": {
                "status": "passed",
                "create_http_status": 200,
                "text_delta_count": 4,
                "terminal_state": "completed",
                "history_persisted_after_reload": True,
                "cancel_terminal_state": "cancelled",
                "retry_terminal_state": "completed",
                "duplicate_assistant_detected": False,
                "project_id": "project-p7",
                "response_id": "response-p7",
            },
            "web_search_sources": {
                "status": "passed",
                "http_status": 200,
                "provider_invoked": True,
                "persisted_after_reload": True,
                "sources": [
                    {
                        "title": "Official source",
                        "url": "https://example.org/source",
                        "retrieved_at": "2026-07-14T10:00:00+00:00",
                    }
                ],
            },
            "file_lifecycle": {
                "status": "passed",
                "upload_http_status": 201,
                "upload_sha256": "b" * 64,
                "analysis_http_status": 201,
                "analysis_sha256": "c" * 64,
                "search_http_status": 200,
                "search_found_uploaded_content": True,
                "reopen_http_status": 200,
                "download_http_status": 200,
                "reopen_sha256": "b" * 64,
                "download_sha256": "b" * 64,
            },
            "document_artifacts": {
                "status": "passed",
                "formats": {
                    "pdf": {
                        "http_status": 200,
                        "mime_type": "application/pdf",
                        "magic": "%PDF-",
                        "size_bytes": 2048,
                        "sha256": "d" * 64,
                        "download_sha256": "d" * 64,
                        "reopen_sha256": "d" * 64,
                    },
                    "docx": {
                        "http_status": 200,
                        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "magic": "PK",
                        "size_bytes": 2048,
                        "sha256": "e" * 64,
                        "download_sha256": "e" * 64,
                        "reopen_sha256": "e" * 64,
                    },
                    "xlsx": {
                        "http_status": 200,
                        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "magic": "PK",
                        "size_bytes": 2048,
                        "sha256": "f" * 64,
                        "download_sha256": "f" * 64,
                        "reopen_sha256": "f" * 64,
                    },
                    "pptx": {
                        "http_status": 200,
                        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        "magic": "PK",
                        "size_bytes": 2048,
                        "sha256": "0" * 64,
                        "download_sha256": "0" * 64,
                        "reopen_sha256": "0" * 64,
                    },
                },
            },
            "image_lifecycle": {
                "status": "passed",
                "generate_http_status": 201,
                "edit_http_status": 201,
                "provider_tool_invoked": True,
                "mime_type": "image/png",
                "width": 1024,
                "height": 1024,
                "generated_sha256": "1" * 64,
                "edited_sha256": "2" * 64,
                "download_sha256": "2" * 64,
                "reopen_sha256": "2" * 64,
                "rendered_in_shell": True,
            },
            "site_app_lifecycle": {
                "status": "passed",
                "artifacts": {
                    kind: {
                        "http_status": 201,
                        "mime_type": "application/zip",
                        "magic": "PK",
                        "size_bytes": 2048,
                        "sha256": digest * 64,
                        "preview_http_status": 200,
                        "preview_content_type": "text/html",
                        "sandbox_headers_verified": True,
                        "download_sha256": digest * 64,
                        "reopen_sha256": digest * 64,
                    }
                    for kind, digest in (("site", "3"), ("app", "4"))
                },
            },
            "developer_api_keys": {
                "status": "passed",
                "create_http_status": 201,
                "secret_shown_once": True,
                "created_key_request_http_status": 200,
                "list_http_status": 200,
                "secret_present_in_list": False,
                "revoke_http_status": 200,
                "revoked_key_request_http_status": 401,
            },
            "structured_apis": {
                "status": "passed",
                "responses_http_status": 200,
                "responses_stream_valid": True,
                "chat_http_status": 200,
                "chat_stream_valid": True,
                "structured_json_schema_valid": True,
                "model": "kolibri",
            },
            "shell_desktop_mobile": {
                "status": "passed",
                "viewports": {
                    viewport: {
                        "status": "passed",
                        "console_errors": 0,
                        "unexplained_failed_requests": 0,
                        "visible_controls_actionable": True,
                        "horizontal_overflow": False,
                    }
                    for viewport in (
                        "desktop_1440",
                        "tablet_768",
                        "mobile_390",
                        "mobile_360",
                    )
                },
                "reload_reopens_all_artifact_types": True,
            },
            "optional_capability_gates": {
                "status": "passed",
                "unavailable_capabilities_hidden": True,
                "degraded_reasons_are_technical": True,
                "external_integrations_owner_gated": True,
                "placeholder_or_fake_success_detected": False,
            },
        },
    }


def valid_rollback_health_evidence(
    release_dir: Path,
    previous_route_config_sha256: str,
) -> dict:
    manifest, _, manifest_sha = p7.load_manifest(release_dir)
    release_id = manifest["release_id"]
    expected_routes = sorted(
        {
            *manifest["targets"]["backend"]["routes"],
            *manifest["targets"]["frontend"]["routes"],
        }
    )
    return {
        "schema_version": p7.ROLLBACK_HEALTH_SCHEMA_VERSION,
        "release_id": release_id,
        "manifest_sha256": manifest_sha,
        "route_config_sha256": previous_route_config_sha256,
        "collector": {
            "identity": p7.COLLECTOR_SIGNER_IDENTITY,
            "implementation": "kolibri-p7-gate-collector",
            "version": "1.0.0",
            "run_id": "rollback-health-run-p7-test",
            "target": {
                "release_id": release_id,
                "manifest_sha256": manifest_sha,
                "backend_origin": manifest["targets"]["backend"]["origin"],
                "frontend_origin": manifest["targets"]["frontend"]["origin"],
            },
        },
        "results": {
            "release_identity": {
                "status": "passed",
                "backend_release_id": release_id,
                "frontend_release_id": release_id,
                "response_header_release_id": release_id,
            },
            "backend_health": {
                "status": "passed",
                "http_status": 200,
                "release_id": release_id,
                "origin": manifest["targets"]["backend"]["origin"],
            },
            "frontend_health": {
                "status": "passed",
                "http_status": 200,
                "release_id": release_id,
                "origin": manifest["targets"]["frontend"]["origin"],
            },
            "routes": {
                "status": "passed",
                "checked_routes": expected_routes,
                "http_statuses": {route: 200 for route in expected_routes},
            },
        },
    }


def test_build_requires_a_clean_committed_worktree(source_repo: Path, tmp_path: Path):
    (source_repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(p7.P7ReleaseError, match="p7_git_worktree_not_clean"):
        p7.build_release(
            repo=source_repo,
            output_root=tmp_path / "releases",
            release_id="kolibri-p7-dirty",
            frontend_builder=fake_frontend_builder,
        )


def test_darwin_release_commands_require_explicit_apple_capability_worker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    monkeypatch.setattr(p7.platform, "system", lambda: "Darwin")
    monkeypatch.delenv(p7.APPLE_CAPABILITY_WORKER_ENV, raising=False)

    with pytest.raises(p7.P7ReleaseError, match="p7_darwin_requires_apple_capability_worker"):
        p7.build_release(
            repo=tmp_path / "missing",
            output_root=tmp_path / "releases",
            release_id="kolibri-p7-darwin",
            frontend_builder=fake_frontend_builder,
        )
    with pytest.raises(p7.P7ReleaseError, match="p7_darwin_requires_apple_capability_worker"):
        p7.verify_release(tmp_path / "missing-release")
    with pytest.raises(p7.P7ReleaseError, match="p7_darwin_requires_apple_capability_worker"):
        p7.verify_gate_evidence(
            tmp_path / "gates.json",
            tmp_path / "gates.json.sig",
            {},
            "1" * 64,
        )
    with pytest.raises(p7.P7ReleaseError, match="p7_darwin_requires_apple_capability_worker"):
        p7.paired_switch_plan(
            release_dir=tmp_path / "candidate",
            rollback_release_dir=tmp_path / "rollback",
            gate_evidence_path=tmp_path / "gates.json",
            gate_evidence_signature_path=tmp_path / "gates.json.sig",
            rollback_signature_path=tmp_path / "rollback.sig",
            rollback_health_evidence_path=tmp_path / "rollback-health.json",
            rollback_health_signature_path=tmp_path / "rollback-health.json.sig",
            previous_route_config_sha256="1" * 64,
            owner_approval_path=tmp_path / "approval.json",
            owner_approval_signature_path=tmp_path / "approval.json.sig",
            signature_path=tmp_path / "release-manifest.json.sig",
        )

    monkeypatch.setenv(p7.APPLE_CAPABILITY_WORKER_ENV, "1")
    with pytest.raises(p7.P7ReleaseError, match="p7_release_id_invalid"):
        p7.build_release(
            repo=tmp_path / "missing",
            output_root=tmp_path / "releases",
            release_id="../bad",
            frontend_builder=fake_frontend_builder,
        )
    with pytest.raises(p7.P7ReleaseError, match="p7_previous_route_config_sha_invalid"):
        p7.paired_switch_plan(
            release_dir=tmp_path / "candidate",
            rollback_release_dir=tmp_path / "rollback",
            gate_evidence_path=tmp_path / "gates.json",
            gate_evidence_signature_path=tmp_path / "gates.json.sig",
            rollback_signature_path=tmp_path / "rollback.sig",
            rollback_health_evidence_path=tmp_path / "rollback-health.json",
            rollback_health_signature_path=tmp_path / "rollback-health.json.sig",
            previous_route_config_sha256="not-a-sha",
            owner_approval_path=tmp_path / "approval.json",
            owner_approval_signature_path=tmp_path / "approval.json.sig",
            signature_path=tmp_path / "release-manifest.json.sig",
        )


def test_unsigned_candidate_binds_commit_artifacts_routes_and_one_release_identity(
    source_repo: Path, tmp_path: Path
):
    result, release_dir = build_candidate(source_repo, tmp_path)
    manifest, manifest_path, manifest_sha = p7.load_manifest(release_dir)

    assert result["status"] == "built_unsigned_candidate"
    assert result["production_applied"] is False
    assert manifest_sha == result["manifest_sha256"]
    assert manifest["source"]["commit"] == _run("git", "rev-parse", "HEAD", cwd=source_repo)
    assert manifest["release_identity"]["backend_environment"] == {
        "KOLIBRI_RELEASE_ID": "kolibri-p7-test"
    }
    assert manifest["release_identity"]["frontend_build_environment"] == {
        "VITE_KOLIBRI_RELEASE_ID": "kolibri-p7-test"
    }
    assert manifest["runtime_requirements"] == {
        "required_backend_secret_names": [
            "JWT_SECRET_KEY",
            "KOLIBRI_EVIDENCE_SIGNING_KEY",
        ],
        "secret_values_forbidden_in_manifest": True,
        "minimum_secret_bytes": 32,
    }
    assert manifest["targets"]["backend"]["routes"] == {
        route: "http://127.0.0.1:18018" for route in p7.BACKEND_ROUTES
    }
    assert manifest["targets"]["frontend"]["routes"] == {
        "/": "http://127.0.0.1:15194"
    }
    assert set(manifest["toolchain"]) == {"python", "node", "npm", "lockfiles"}
    assert manifest["toolchain"]["python"]
    assert manifest["toolchain"]["node"]
    assert manifest["toolchain"]["npm"]
    assert manifest["toolchain"]["lockfiles"]["kolibri-backend/requirements.txt"][
        "sha256"
    ] == p7.sha256_file(source_repo / "kolibri-backend" / "requirements.txt")
    assert [item["name"] for item in manifest["artifacts"]] == [
        "source.bundle",
        "backend.tar",
        "frontend.tar",
    ]
    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert p7.verify_release(release_dir, repo=source_repo)["signature_verified"] is False
    with pytest.raises(p7.P7ReleaseError, match="p7_signature_required"):
        p7.verify_release(release_dir, repo=source_repo, require_signature=True)


def test_real_openssh_signature_is_verified_and_tamper_fails_closed(
    source_repo: Path,
    tmp_path: Path,
    ssh_material: tuple[Path, Path, str, str],
):
    result, release_dir = build_candidate(source_repo, tmp_path, signed=ssh_material)
    _key, allowed, identity, ssh_keygen = ssh_material
    signature = release_dir / "release-manifest.json.sig"

    verified = p7.verify_release(
        release_dir,
        repo=source_repo,
        require_signature=True,
        signature_path=signature,
        ssh_keygen=ssh_keygen,
    )
    assert result["status"] == "built_signed"
    assert result["signature_verified"] is True
    assert verified["signature_verified"] is True

    manifest_path = release_dir / "release-manifest.json"
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["source"]["branch"] = "tampered-but-structurally-valid"
    manifest_path.write_bytes(p7.canonical_json(tampered) + b"\n")
    with pytest.raises(p7.P7ReleaseError, match="p7_signature_verification_failed"):
        p7.verify_release(
            release_dir,
            require_signature=True,
            signature_path=signature,
            ssh_keygen=ssh_keygen,
        )


def test_artifact_tamper_is_rejected_before_activation(source_repo: Path, tmp_path: Path):
    _result, release_dir = build_candidate(source_repo, tmp_path)
    with (release_dir / "backend.tar").open("ab") as stream:
        stream.write(b"tampered")

    with pytest.raises(p7.P7ReleaseError, match="p7_artifact_integrity_failed"):
        p7.verify_release(release_dir)


def test_ignored_runtime_database_and_schema_lock_never_enter_backend_archive(
    source_repo: Path, tmp_path: Path
):
    (source_repo / "kolibri-backend" / "kolibri.db").write_bytes(b"runtime database")
    (source_repo / "kolibri-backend" / "kolibri.schema.lock").write_text(
        "runtime lock\n", encoding="utf-8"
    )

    _result, release_dir = build_candidate(source_repo, tmp_path)
    with tarfile.open(release_dir / "backend.tar", "r") as archive:
        names = archive.getnames()

    assert "kolibri-backend/app/main.py" in names
    assert "kolibri-backend/requirements.txt" in names
    assert all(not name.endswith((".db", ".schema.lock")) for name in names)


def test_commit_backend_archive_never_reads_mutated_worktree_bytes(
    source_repo: Path,
    tmp_path: Path,
):
    commit = _run("git", "rev-parse", "HEAD", cwd=source_repo)
    source = source_repo / "kolibri-backend" / "app" / "main.py"
    committed = source.read_bytes()
    source.write_text("print('tampered after commit')\n", encoding="utf-8")

    artifact = p7.deterministic_commit_tar(
        source_repo,
        commit,
        ("kolibri-backend",),
        tmp_path / "backend.tar",
    )

    assert artifact.name == "backend.tar"
    with tarfile.open(tmp_path / "backend.tar", "r") as archive:
        archived = archive.extractfile("kolibri-backend/app/main.py")
        assert archived is not None
        assert archived.read() == committed


def test_commit_backend_archive_omits_tracked_excluded_files(
    source_repo: Path,
    tmp_path: Path,
):
    excluded = source_repo / "kolibri-backend" / ".env.example"
    excluded.write_text("EXAMPLE_ONLY=1\n", encoding="utf-8")
    _run("git", "add", "-f", "kolibri-backend/.env.example", cwd=source_repo)
    _run("git", "commit", "-qm", "add tracked excluded example", cwd=source_repo)
    commit = _run("git", "rev-parse", "HEAD", cwd=source_repo)

    p7.deterministic_commit_tar(
        source_repo,
        commit,
        ("kolibri-backend",),
        tmp_path / "backend.tar",
    )

    with tarfile.open(tmp_path / "backend.tar", "r") as archive:
        names = archive.getnames()
    assert "kolibri-backend/app/main.py" in names
    assert "kolibri-backend/.env.example" not in names


def test_release_fails_when_tracked_source_changes_after_post_build_check(
    source_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    real_require_clean_commit = p7.require_clean_commit
    calls = 0

    def racing_clean_check(repo: Path):
        nonlocal calls
        calls += 1
        result = real_require_clean_commit(repo)
        if calls == 2:
            (source_repo / "kolibri-backend" / "app" / "main.py").write_text(
                "print('raced after clean check')\n",
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(p7, "require_clean_commit", racing_clean_check)

    with pytest.raises(p7.P7ReleaseError, match="p7_git_worktree_not_clean"):
        build_candidate(source_repo, tmp_path, release_id="kolibri-p7-source-race")

    assert calls == 3
    assert not (tmp_path / "releases" / "kolibri-p7-source-race").exists()


def test_frontend_archive_uses_private_snapshot_not_mutable_original_dist(
    source_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    real_require_clean_commit = p7.require_clean_commit
    calls = 0

    def ignored_output_race(repo: Path):
        nonlocal calls
        calls += 1
        result = real_require_clean_commit(repo)
        if calls == 2:
            original_dist = source_repo / "kolibri-v2" / "dist"
            (original_dist / "assets").mkdir(parents=True, exist_ok=True)
            (original_dist / "index.html").write_text(
                "<html>attacker-original-dist</html>\n",
                encoding="utf-8",
            )
            (original_dist / "assets" / "app.js").write_text(
                "window.KOLIBRI_RELEASE_ID='attacker-original-dist';\n",
                encoding="utf-8",
            )
        return result

    monkeypatch.setattr(p7, "require_clean_commit", ignored_output_race)
    _result, release_dir = build_candidate(
        source_repo,
        tmp_path,
        release_id="kolibri-p7-frontend-snapshot",
    )

    assert calls == 3
    with tarfile.open(release_dir / "frontend.tar", "r") as archive:
        index = archive.extractfile("kolibri-v2/dist/index.html")
        script = archive.extractfile("kolibri-v2/dist/assets/app.js")
        assert index is not None and script is not None
        payload = index.read() + script.read()
    assert b"kolibri-p7-frontend-snapshot" in payload
    assert b"attacker-original-dist" not in payload


def test_signature_verification_fails_closed_when_tool_is_unavailable(
    source_repo: Path,
    tmp_path: Path,
    ssh_material: tuple[Path, Path, str, str],
):
    _result, release_dir = build_candidate(source_repo, tmp_path, signed=ssh_material)
    _key, _allowed, _identity, _ssh_keygen = ssh_material

    with pytest.raises(p7.P7ReleaseError, match="p7_signature_verification_unavailable"):
        p7.verify_release(
            release_dir,
            require_signature=True,
            signature_path=release_dir / "release-manifest.json.sig",
            ssh_keygen=str(tmp_path / "missing-ssh-keygen"),
        )


def test_release_signature_uses_pinned_owner_root_not_attacker_file(
    source_repo: Path,
    tmp_path: Path,
    ssh_material: tuple[Path, Path, str, str],
):
    _result, release_dir = build_candidate(source_repo, tmp_path, signed=ssh_material)
    _owner_key, _owner_root, _owner_identity, ssh_keygen = ssh_material
    attacker_key, attacker_allowed, _attacker_identity, _ = _ssh_material(
        tmp_path,
        "attacker-key",
        p7.OWNER_SIGNER_IDENTITY,
    )
    copied_manifest = tmp_path / "attacker-copy.json"
    copied_manifest.write_bytes((release_dir / "release-manifest.json").read_bytes())
    attacker_signature = sign_document(
        copied_manifest,
        attacker_key,
        p7.RELEASE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )

    assert attacker_allowed != p7.OWNER_TRUST_ROOT
    with pytest.raises(p7.P7ReleaseError, match="p7_signature_verification_failed"):
        p7.verify_release(
            release_dir,
            require_signature=True,
            signature_path=attacker_signature,
            ssh_keygen=ssh_keygen,
        )


def test_functional_gate_evidence_requires_recalculation_revisions_and_real_pdf(
    source_repo: Path,
    tmp_path: Path,
    collector_material: tuple[Path, Path, str, str],
):
    _result, release_dir = build_candidate(source_repo, tmp_path)
    manifest, _, manifest_sha = p7.load_manifest(release_dir)
    evidence = valid_gate_evidence(release_dir)
    collector_key, _collector_root, _collector_identity, ssh_keygen = collector_material
    evidence_path = write_canonical(tmp_path / "gates.json", evidence)
    signature_path = sign_document(
        evidence_path,
        collector_key,
        p7.GATE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )

    attestation = p7.verify_gate_evidence(
        evidence_path,
        signature_path,
        manifest,
        manifest_sha,
        ssh_keygen=ssh_keygen,
    )
    assert attestation["status"] == "verified"
    assert attestation["collector_signature_verified"] is True
    assert attestation["gates"] == sorted(
        item["id"] for item in p7.functional_gate_contract() if item["required"]
    )

    evidence["results"]["estimate_create_regional"]["truth_status"] = "preliminary"
    write_canonical(evidence_path, evidence)
    signature_path = sign_document(
        evidence_path,
        collector_key,
        p7.GATE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    with pytest.raises(p7.P7ReleaseError, match="p7_gate_estimate_create_failed"):
        p7.verify_gate_evidence(
            evidence_path,
            signature_path,
            manifest,
            manifest_sha,
            ssh_keygen=ssh_keygen,
        )

    evidence["results"]["estimate_create_regional"]["truth_status"] = "source_backed"
    evidence["results"]["estimate_pdf"]["magic"] = "<html"
    write_canonical(evidence_path, evidence)
    signature_path = sign_document(
        evidence_path,
        collector_key,
        p7.GATE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    with pytest.raises(p7.P7ReleaseError, match="p7_gate_estimate_pdf_failed"):
        p7.verify_gate_evidence(
            evidence_path,
            signature_path,
            manifest,
            manifest_sha,
            ssh_keygen=ssh_keygen,
        )

    evidence = valid_gate_evidence(release_dir)
    del evidence["results"]["shell_desktop_mobile"]["viewports"]["tablet_768"]
    write_canonical(evidence_path, evidence)
    signature_path = sign_document(
        evidence_path,
        collector_key,
        p7.GATE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    with pytest.raises(p7.P7ReleaseError, match="p7_gate_shell_desktop_mobile_failed"):
        p7.verify_gate_evidence(
            evidence_path,
            signature_path,
            manifest,
            manifest_sha,
            ssh_keygen=ssh_keygen,
        )

    evidence = valid_gate_evidence(release_dir)
    del evidence["results"]["image_lifecycle"]
    write_canonical(evidence_path, evidence)
    signature_path = sign_document(
        evidence_path,
        collector_key,
        p7.GATE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    with pytest.raises(p7.P7ReleaseError, match="p7_gate_results_incomplete"):
        p7.verify_gate_evidence(
            evidence_path,
            signature_path,
            manifest,
            manifest_sha,
            ssh_keygen=ssh_keygen,
        )


def test_gate_evidence_requires_pinned_collector_signature_and_exact_target(
    source_repo: Path,
    tmp_path: Path,
    collector_material: tuple[Path, Path, str, str],
):
    _result, release_dir = build_candidate(source_repo, tmp_path)
    manifest, _, manifest_sha = p7.load_manifest(release_dir)
    collector_key, _collector_root, _collector_identity, ssh_keygen = collector_material
    evidence = valid_gate_evidence(release_dir)
    evidence_path = write_canonical(tmp_path / "collector-bound-gates.json", evidence)

    with pytest.raises(p7.P7ReleaseError, match="p7_signature_material_missing"):
        p7.verify_gate_evidence(
            evidence_path,
            tmp_path / "missing.sig",
            manifest,
            manifest_sha,
            ssh_keygen=ssh_keygen,
        )

    evidence["collector"]["target"]["backend_origin"] = "http://127.0.0.1:19999"
    write_canonical(evidence_path, evidence)
    signature = sign_document(
        evidence_path,
        collector_key,
        p7.GATE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    with pytest.raises(p7.P7ReleaseError, match="p7_collector_target_mismatch"):
        p7.verify_gate_evidence(
            evidence_path,
            signature,
            manifest,
            manifest_sha,
            ssh_keygen=ssh_keygen,
        )


def test_gate_verification_uses_one_byte_snapshot_during_path_swap(
    source_repo: Path,
    tmp_path: Path,
    collector_material: tuple[Path, Path, str, str],
    monkeypatch: pytest.MonkeyPatch,
):
    _result, release_dir = build_candidate(source_repo, tmp_path)
    manifest, _, manifest_sha = p7.load_manifest(release_dir)
    collector_key, _collector_root, _collector_identity, ssh_keygen = collector_material
    original_evidence = valid_gate_evidence(release_dir)
    evidence_path = write_canonical(tmp_path / "swap-gates.json", original_evidence)
    signed_bytes = evidence_path.read_bytes()
    expected_sha = p7.sha256_bytes(signed_bytes)
    signature = sign_document(
        evidence_path,
        collector_key,
        p7.GATE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    swapped_evidence = json.loads(signed_bytes)
    swapped_evidence["results"]["estimate_create_regional"]["truth_status"] = "preliminary"
    swapped_bytes = p7.canonical_json(swapped_evidence) + b"\n"
    original_verify = p7._verify_pinned_signature

    def swap_then_verify(content_bytes: bytes, *args, **kwargs):
        evidence_path.write_bytes(swapped_bytes)
        return original_verify(content_bytes, *args, **kwargs)

    monkeypatch.setattr(p7, "_verify_pinned_signature", swap_then_verify)
    attestation = p7.verify_gate_evidence(
        evidence_path,
        signature,
        manifest,
        manifest_sha,
        ssh_keygen=ssh_keygen,
    )

    assert evidence_path.read_bytes() == swapped_bytes
    assert attestation["evidence_sha256"] == expected_sha
    assert attestation["status"] == "verified"


def test_owner_approval_is_signature_and_all_digest_bound(
    tmp_path: Path,
    ssh_material: tuple[Path, Path, str, str],
):
    owner_key, _owner_root, _owner_identity, ssh_keygen = ssh_material
    expected = {
        "release_id": "kolibri-p7-candidate",
        "manifest_sha256": "1" * 64,
        "gate_evidence_sha256": "2" * 64,
        "rollback_release_id": "kolibri-p6-prior",
        "rollback_manifest_sha256": "3" * 64,
        "rollback_health_evidence_sha256": "4" * 64,
        "previous_route_config_sha256": "5" * 64,
    }
    approval_path = write_canonical(
        tmp_path / "approval.json",
        {
            "schema_version": p7.APPROVAL_SCHEMA_VERSION,
            "action": "paired_switch",
            "approval_id": "approval-bound-test",
            **expected,
        },
    )
    signature = sign_document(
        approval_path,
        owner_key,
        p7.APPROVAL_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    verified = p7.verify_owner_approval(
        approval_path,
        signature,
        expected,
        ssh_keygen=ssh_keygen,
    )
    assert verified["signature_verified"] is True

    wrong_expected = {**expected, "gate_evidence_sha256": "9" * 64}
    with pytest.raises(p7.P7ReleaseError, match="p7_owner_approval_binding_mismatch"):
        p7.verify_owner_approval(
            approval_path,
            signature,
            wrong_expected,
            ssh_keygen=ssh_keygen,
        )


def test_rollback_health_requires_signed_live_release_identity_and_routes(
    source_repo: Path,
    tmp_path: Path,
    collector_material: tuple[Path, Path, str, str],
):
    _result, rollback_dir = build_candidate(
        source_repo,
        tmp_path,
        release_id="kolibri-p6-health-test",
    )
    rollback, _, rollback_sha = p7.load_manifest(rollback_dir)
    collector_key, _collector_root, _collector_identity, ssh_keygen = collector_material
    config_sha = "6" * 64
    evidence = valid_rollback_health_evidence(rollback_dir, config_sha)
    evidence_path = write_canonical(tmp_path / "rollback-health-check.json", evidence)
    signature = sign_document(
        evidence_path,
        collector_key,
        p7.ROLLBACK_HEALTH_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    attestation = p7.verify_rollback_health_evidence(
        evidence_path,
        signature,
        rollback,
        rollback_sha,
        config_sha,
        ssh_keygen=ssh_keygen,
    )
    assert attestation["collector_signature_verified"] is True

    evidence["results"]["backend_health"]["http_status"] = 503
    write_canonical(evidence_path, evidence)
    signature = sign_document(
        evidence_path,
        collector_key,
        p7.ROLLBACK_HEALTH_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    with pytest.raises(p7.P7ReleaseError, match="p7_rollback_health_failed"):
        p7.verify_rollback_health_evidence(
            evidence_path,
            signature,
            rollback,
            rollback_sha,
            config_sha,
            ssh_keygen=ssh_keygen,
        )


def test_paired_switch_plan_is_signature_gate_bound_and_has_atomic_rollback(
    source_repo: Path,
    tmp_path: Path,
    ssh_material: tuple[Path, Path, str, str],
    collector_material: tuple[Path, Path, str, str],
):
    _result, release_dir = build_candidate(source_repo, tmp_path, signed=ssh_material)
    _rollback_result, rollback_dir = build_candidate(
        source_repo,
        tmp_path,
        signed=ssh_material,
        release_id="kolibri-p6-previous",
    )
    owner_key, _owner_root, _owner_identity, ssh_keygen = ssh_material
    collector_key, _collector_root, _collector_identity, _ = collector_material
    previous_config_sha = "b" * 64
    evidence_path = write_canonical(
        tmp_path / "p7-gates.json",
        valid_gate_evidence(release_dir),
    )
    evidence_signature = sign_document(
        evidence_path,
        collector_key,
        p7.GATE_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    rollback_health_path = write_canonical(
        tmp_path / "rollback-health.json",
        valid_rollback_health_evidence(rollback_dir, previous_config_sha),
    )
    rollback_health_signature = sign_document(
        rollback_health_path,
        collector_key,
        p7.ROLLBACK_HEALTH_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )
    manifest, _, manifest_sha = p7.load_manifest(release_dir)
    rollback_manifest, _, rollback_manifest_sha = p7.load_manifest(rollback_dir)
    approval_path = write_canonical(
        tmp_path / "owner-approval.json",
        {
            "schema_version": p7.APPROVAL_SCHEMA_VERSION,
            "action": "paired_switch",
            "approval_id": "approval-p7-test",
            "release_id": manifest["release_id"],
            "manifest_sha256": manifest_sha,
            "gate_evidence_sha256": p7.sha256_file(evidence_path),
            "rollback_release_id": rollback_manifest["release_id"],
            "rollback_manifest_sha256": rollback_manifest_sha,
            "rollback_health_evidence_sha256": p7.sha256_file(rollback_health_path),
            "previous_route_config_sha256": previous_config_sha,
        },
    )
    approval_signature = sign_document(
        approval_path,
        owner_key,
        p7.APPROVAL_SIGNATURE_NAMESPACE,
        ssh_keygen,
    )

    plan = p7.paired_switch_plan(
        release_dir=release_dir,
        rollback_release_dir=rollback_dir,
        gate_evidence_path=evidence_path,
        gate_evidence_signature_path=evidence_signature,
        rollback_signature_path=rollback_dir / "release-manifest.json.sig",
        rollback_health_evidence_path=rollback_health_path,
        rollback_health_signature_path=rollback_health_signature,
        previous_route_config_sha256=previous_config_sha,
        owner_approval_path=approval_path,
        owner_approval_signature_path=approval_signature,
        signature_path=release_dir / "release-manifest.json.sig",
        repo=source_repo,
        ssh_keygen=ssh_keygen,
    )

    assert plan["status"] == "planned_not_applied"
    assert plan["production_applied"] is False
    assert plan["signature"]["verified"] is True
    assert plan["owner_approval"]["signature_verified"] is True
    assert plan["functional_gate_attestation"]["collector_signature_verified"] is True
    assert plan["candidate_routes"]["/"] == "http://127.0.0.1:15194"
    assert plan["candidate_routes"]["/v1/"] == "http://127.0.0.1:18018"
    assert plan["atomic_switch"]["single_site_config_replacement"] is True
    assert plan["atomic_switch"]["frontend_and_backend_must_switch_together"] is True
    assert plan["rollback"]["release_id"] == "kolibri-p6-previous"
    assert plan["rollback"]["signature_verified"] is True
    assert plan["rollback"]["artifact_count"] == 3
    assert plan["rollback"]["health_attestation"]["collector_signature_verified"] is True
    assert plan["rollback"]["restore_config_sha256"] == "b" * 64
    assert plan["rollback"]["bound_candidate_manifest_sha256"] == plan["manifest_sha256"]
    assert plan["executor_contract"]["this_tool_can_apply"] is False


def test_switch_plan_never_accepts_unsigned_candidate(
    source_repo: Path,
    tmp_path: Path,
    ssh_material: tuple[Path, Path, str, str],
):
    _result, release_dir = build_candidate(source_repo, tmp_path)
    evidence_path = write_canonical(tmp_path / "p7-gates.json", valid_gate_evidence(release_dir))

    with pytest.raises(p7.P7ReleaseError, match="p7_signature_material_missing"):
        p7.paired_switch_plan(
            release_dir=release_dir,
            rollback_release_dir=tmp_path / "rollback-release",
            gate_evidence_path=evidence_path,
            gate_evidence_signature_path=tmp_path / "missing-gates.sig",
            rollback_signature_path=tmp_path / "missing-rollback.sig",
            rollback_health_evidence_path=tmp_path / "missing-rollback-health.json",
            rollback_health_signature_path=tmp_path / "missing-rollback-health.sig",
            previous_route_config_sha256="b" * 64,
            owner_approval_path=tmp_path / "missing-approval.json",
            owner_approval_signature_path=tmp_path / "missing-approval.sig",
            signature_path=release_dir / "missing.sig",
        )


def test_builder_cannot_collide_ports_or_overwrite_release(source_repo: Path, tmp_path: Path):
    with pytest.raises(p7.P7ReleaseError, match="p7_target_ports_must_differ"):
        p7.build_release(
            repo=source_repo,
            output_root=tmp_path / "releases",
            release_id="kolibri-p7-collision",
            backend_port=18015,
            frontend_port=18015,
            frontend_builder=fake_frontend_builder,
        )

    _result, _release_dir = build_candidate(source_repo, tmp_path)
    with pytest.raises(p7.P7ReleaseError, match="p7_release_output_exists"):
        build_candidate(source_repo, tmp_path)
