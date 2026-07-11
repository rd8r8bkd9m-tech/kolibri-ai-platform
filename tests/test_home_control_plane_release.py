from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops import home_control_plane_canary as canary
from ops import home_control_plane_launcher as launcher
from ops import home_control_plane_release as control_release
from ops.fleet_membership import MeshMembershipSource
from ops.release_controller import FleetNode, ReleaseFile, ReleaseManifest


ROOT = Path(__file__).resolve().parents[1]


def write_manifest(path: Path) -> Path:
    path.write_text(json.dumps({
        "schema_version": 1,
        "epoch": 7,
        "cluster_id": "test-cluster",
        "peers": {
            "home": {"node_id": "home", "mesh_ip": "10.99.0.1"},
            "worker": {"node_id": "worker-a", "mesh_ip": "10.99.0.2"},
        },
    }), encoding="utf-8")
    return path


def unified_manifest(release_id: str = "release-a") -> ReleaseManifest:
    paths = sorted({
        *control_release.REQUIRED_RUNTIME_PATHS,
        "backend/main.py",
        "frontend/dist/index.html",
    })
    return ReleaseManifest(
        release_id=release_id,
        source_commit="0123456789abcdef",
        artifact_uri=f"artifact://bundles/{release_id}.tar.gz",
        files=tuple(
            ReleaseFile(path=path, sha256="0" * 64, size_bytes=1)
            for path in paths
        ),
    )


def home_node() -> FleetNode:
    return FleetNode(
        node_id="home",
        physical_node_id="home",
        freshness="fresh",
        health="online",
        draining=False,
        capabilities=("release_apply_v1",),
        agent_live=True,
    )


def test_home_release_operator_path_has_no_ssh_execution_transport():
    source = (ROOT / "ops/home_control_plane_release.py").read_text(encoding="utf-8")
    assert "import subprocess" not in source
    assert "paramiko" not in source
    assert "os.system" not in source
    assert "ControlPlaneClient" in source


def test_full_bundle_closure_binds_response_only_mimo_profile():
    profile_path = ROOT / "ops/mimo/kolibri-response-only.md"
    profile = profile_path.read_text(encoding="utf-8")
    assert "ops/mimo/kolibri-response-only.md" in control_release.REQUIRED_RUNTIME_PATHS
    assert "model: mimo/mimo-auto" in profile
    assert '"*": deny' in profile
    for tool in ("bash", "read", "write", "edit", "webfetch", "actor", "task"):
        assert f"  {tool}: false" in profile


@pytest.mark.parametrize("missing_path", ["ops/factory_control.py", "ops/agent_host.py"])
def test_unified_profile_fails_closed_when_shared_runtime_payload_missing(missing_path):
    valid = unified_manifest()
    profile = control_release.validate_unified_profile(valid)
    assert profile["profile"] == "unified-home-runtime"

    incomplete = ReleaseManifest(
        release_id="incomplete",
        source_commit=valid.source_commit,
        artifact_uri="artifact://bundles/incomplete.tar.gz",
        files=tuple(item for item in valid.files if item.path != missing_path),
    )
    with pytest.raises(control_release.ReleaseError, match="unified"):
        control_release.validate_unified_profile(incomplete)


def test_home_control_plane_release_defaults_to_read_only_plan(monkeypatch, capsys):
    manifest = unified_manifest()
    client = SimpleNamespace(fleet=lambda: [home_node()])
    monkeypatch.setattr(control_release, "load_release_manifest", lambda _path: manifest)
    monkeypatch.setattr(
        control_release.ControlPlaneClient,
        "from_environment",
        classmethod(lambda cls, **kwargs: client),
    )
    monkeypatch.setattr(
        control_release,
        "verify_ssh_signature",
        lambda *args, **kwargs: pytest.fail("plan must not verify or use signing material"),
    )

    assert control_release.main(["--manifest", "manifest.json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "planned"
    assert payload["mutation"] == "none"
    assert payload["authority"] == "home-only"
    assert payload["waves"] == [{"name": "home-canary", "nodes": ["home"]}]


def test_apply_delegates_signed_owner_approved_home_wave(monkeypatch, capsys):
    current = unified_manifest("current")
    rollback = unified_manifest("rollback")
    loaded = iter((current, rollback))
    client = SimpleNamespace(fleet=lambda: [home_node()])
    verified = SimpleNamespace(manifest=current)
    rollback_verified = SimpleNamespace(manifest=rollback)
    verified_values = iter((verified, rollback_verified))
    monkeypatch.setattr(control_release, "load_release_manifest", lambda _path: next(loaded))
    monkeypatch.setattr(
        control_release.ControlPlaneClient,
        "from_environment",
        classmethod(lambda cls, **kwargs: client),
    )
    monkeypatch.setattr(
        control_release,
        "verify_ssh_signature",
        lambda *args, **kwargs: next(verified_values),
    )
    calls = []
    monkeypatch.setattr(
        control_release,
        "execute_progressive_release",
        lambda *args: calls.append(args) or {"status": "completed", "release_id": "current"},
    )

    result = control_release.main([
        "--manifest", "current.json",
        "--apply",
        "--signature", "current.sig",
        "--rollback-manifest", "rollback.json",
        "--rollback-signature", "rollback.sig",
        "--allowed-signers", "allowed-signers",
        "--signer-identity", "owner",
        "--approval-id", "approval-current",
    ])

    assert result == 0
    assert len(calls) == 1
    assert calls[0][0] is client
    assert calls[0][4] == "approval-current"
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "completed"
    assert payload["authority"] == "home-only"


def test_canary_contract_gate_binds_dynamic_membership_and_release(monkeypatch, tmp_path):
    manifest = write_manifest(tmp_path / "peers.json")
    snapshot = MeshMembershipSource(manifest).load()
    ids = [item.node_id for item in snapshot.members]

    def fake_http(_base_url, path, **_kwargs):
        if path == "/v1/health":
            return {
                "status": "completed",
                "node": "home",
                "route_used": "/v1/health",
                "data": {
                    "redis": "PONG",
                    "fabric_api_version": "test",
                    "state_namespace": "kolibri_factory",
                    "active_release_id": "release-a",
                    "canary_read_only": True,
                },
            }
        if path.startswith("/v1/nodes"):
            return {
                "scope": "active",
                "nodes": [{"node_id": node_id} for node_id in ids],
                "membership": {
                    "authority": "replicated_mesh_manifest",
                    "digest": snapshot.digest,
                    "canonical_total": len(ids),
                    "registered_total": len(ids),
                    "missing_total": 0,
                    "schedulable_total": len(ids),
                },
            }
        return {
            "schema_version": canary.FLEET_PROOF_SCHEMA,
            "source": "control-plane/home",
            "membership": {"digest": snapshot.digest},
            "summary": {
                "canonical_total": len(ids),
                "fresh_total": len(ids),
                "strict_verified_total": len(ids),
                "missing_strict_verified_total": 0,
            },
            "nodes": [{"node_id": node_id} for node_id in ids],
        }

    monkeypatch.setattr(canary, "_http_json", fake_http)
    result = canary.validate_contracts(
        "http://127.0.0.1:19999",
        manifest,
        expected_release_id="release-a",
        expected_read_only=True,
    )
    assert result["status"] == "passed"
    assert result["canonical_total"] == 2
    assert result["membership_digest"] == snapshot.digest
    assert result["state_namespace"] == "kolibri_factory"
    assert result["legacy_contract_accepted"] is False


def test_signed_rollback_can_identify_a_legacy_runtime_without_false_release_claim(
    monkeypatch,
    tmp_path,
):
    manifest = write_manifest(tmp_path / "peers.json")
    snapshot = MeshMembershipSource(manifest).load()
    ids = [item.node_id for item in snapshot.members]

    def fake_http(_base_url, path, **_kwargs):
        if path == "/v1/health":
            # Exact pre-migration response: no active release or read-only
            # claim. It is accepted only by an explicit rollback gate.
            return {
                "status": "completed",
                "node": "home",
                "route_used": "/v1/health",
                "data": {"redis": "PONG", "fabric_api_version": "legacy"},
            }
        if path.startswith("/v1/nodes"):
            return {
                "scope": "active",
                "nodes": [{"node_id": node_id} for node_id in ids],
                "membership": {
                    "authority": "replicated_mesh_manifest",
                    "digest": snapshot.digest,
                    "canonical_total": len(ids),
                    "registered_total": len(ids),
                    "missing_total": 0,
                    "schedulable_total": len(ids),
                },
            }
        return {
            "schema_version": canary.FLEET_PROOF_SCHEMA,
            "source": "control-plane/home",
            "membership": {"digest": snapshot.digest},
            "summary": {
                "canonical_total": len(ids),
                "fresh_total": len(ids),
                "strict_verified_total": 0,
                "missing_strict_verified_total": len(ids),
            },
            "nodes": [{"node_id": node_id} for node_id in ids],
        }

    monkeypatch.setattr(canary, "_http_json", fake_http)
    result = canary.validate_contracts(
        "http://127.0.0.1:9101",
        manifest,
        expected_release_id="legacy-bootstrap",
        expected_read_only=False,
        allow_legacy_contract=True,
    )
    assert result["legacy_contract_accepted"] is True
    assert result["release_id"] is None


def test_explicit_legacy_baseline_accepts_only_missing_fleet_proof_on_legacy_shape(
    monkeypatch,
    tmp_path,
):
    manifest = write_manifest(tmp_path / "peers.json")
    snapshot = MeshMembershipSource(manifest).load()
    ids = [item.node_id for item in snapshot.members]

    def fake_http(_base_url, path, **_kwargs):
        if path == "/v1/health":
            return {
                "status": "completed",
                "node": "home",
                "route_used": "/v1/health",
                "data": {"redis": "PONG", "fabric_api_version": "legacy"},
            }
        if path.startswith("/v1/nodes"):
            return {
                "scope": "active",
                "nodes": [{"node_id": node_id} for node_id in ids],
                "membership": {
                    "authority": "replicated_mesh_manifest",
                    "digest": snapshot.digest,
                    "canonical_total": len(ids),
                    "registered_total": len(ids),
                    "missing_total": 0,
                    "schedulable_total": len(ids),
                },
            }
        raise canary.CanaryError("control_plane_contract_not_found")

    monkeypatch.setattr(canary, "_http_json", fake_http)

    with pytest.raises(canary.CanaryError, match="contract_not_found"):
        canary.validate_contracts("http://127.0.0.1:9101", manifest)

    result = canary.validate_contracts(
        "http://127.0.0.1:9101",
        manifest,
        allow_legacy_contract=True,
    )
    assert result["legacy_contract_accepted"] is True
    assert result["fleet_proof_status"] == "legacy_unavailable"
    assert result["fleet_proof_projection"] == {
        "fresh_total": None,
        "strict_verified_total": None,
        "missing_strict_verified_total": None,
    }
    assert result["legacy_compatibility_reasons"] == [
        "fleet_proof_endpoint_absent",
    ]


def test_legacy_flag_never_accepts_missing_fleet_proof_from_modern_health_shape(
    monkeypatch,
    tmp_path,
):
    manifest = write_manifest(tmp_path / "peers.json")

    def fake_http(_base_url, path, **_kwargs):
        if path == "/v1/health":
            return {
                "status": "completed",
                "node": "home",
                "route_used": "/v1/health",
                "data": {
                    "redis": "PONG",
                    "fabric_api_version": "modern",
                    "active_release_id": "release-a",
                    "canary_read_only": False,
                    "state_namespace": "kolibri_factory",
                },
            }
        if path.startswith("/v1/nodes"):
            snapshot = MeshMembershipSource(manifest).load()
            ids = [item.node_id for item in snapshot.members]
            return {
                "scope": "active",
                "nodes": [{"node_id": node_id} for node_id in ids],
                "membership": {
                    "authority": "replicated_mesh_manifest",
                    "digest": snapshot.digest,
                    "canonical_total": len(ids),
                    "registered_total": len(ids),
                    "missing_total": 0,
                    "schedulable_total": len(ids),
                },
            }
        raise canary.CanaryError("control_plane_contract_not_found")

    monkeypatch.setattr(canary, "_http_json", fake_http)
    with pytest.raises(canary.CanaryError, match="contract_not_found"):
        canary.validate_contracts(
            "http://127.0.0.1:9101",
            manifest,
            allow_legacy_contract=True,
        )


def test_live_cli_uses_distinct_exit_code_for_explicit_legacy_baseline(
    monkeypatch,
    tmp_path,
):
    manifest = write_manifest(tmp_path / "peers.json")
    calls = []
    monkeypatch.setattr(canary, "assert_local_home_control_plane", lambda **_kwargs: None)
    monkeypatch.setattr(
        canary,
        "validate_contracts",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {
            "status": "passed",
            "legacy_contract_accepted": True,
            "fleet_proof_status": "legacy_unavailable",
        },
    )

    result = canary.main([
        "live",
        "--manifest",
        str(manifest),
        "--allow-legacy-baseline",
    ])

    assert result == canary.LEGACY_BASELINE_EXIT_CODE
    assert calls[0][1]["allow_legacy_contract"] is True


def test_candidate_is_always_stopped_after_side_by_side_contract_gate(monkeypatch, tmp_path):
    manifest = write_manifest(tmp_path / "peers.json")
    release_root = tmp_path / "releases"
    release_dir = release_root / "release-a"
    release_dir.mkdir(parents=True)
    for relative in canary.REQUIRED_RUNTIME:
        target = release_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# test\n", encoding="utf-8")
        target.chmod(0o644)

    process = SimpleNamespace(pid=12345, poll=lambda: None)
    stopped = []
    calls = []
    process_calls = []
    monkeypatch.setattr(canary, "assert_local_home_control_plane", lambda **kwargs: "10.99.0.1")
    monkeypatch.setattr(canary, "_available_loopback_port", lambda: 19999)
    monkeypatch.setattr(
        canary.subprocess,
        "Popen",
        lambda *args, **kwargs: process_calls.append((args, kwargs)) or process,
    )
    monkeypatch.setattr(canary, "_stop_candidate", lambda value: stopped.append(value))
    monkeypatch.setattr(
        canary,
        "validate_contracts",
        lambda *args, **kwargs: calls.append((args, kwargs)) or (
            {
                "status": "passed",
                "release_id": None,
                "state_namespace": "kolibri_factory",
                "membership_projection": {"registered_total": 2},
                "fleet_proof_projection": {
                    "fresh_total": None,
                    "strict_verified_total": None,
                    "missing_strict_verified_total": None,
                },
                "fleet_proof_status": "legacy_unavailable",
                "legacy_contract_accepted": True,
            }
            if len(calls) == 1
            else {
                "status": "passed",
                "release_id": "release-a",
                "state_namespace": "kolibri_factory",
                "membership_projection": {"registered_total": 2},
                "fleet_proof_projection": {"fresh_total": 2},
                "fleet_proof_status": "verified",
                "legacy_contract_accepted": False,
            }
        ),
    )

    result = canary.run_candidate(
        release_dir,
        manifest,
        release_root=release_root,
    )

    assert result["status"] == "passed"
    assert len(calls) == 2  # current Home baseline, then isolated candidate
    assert calls[1][1]["expected_read_only"] is True
    assert calls[0][1]["allow_legacy_contract"] is True
    assert process_calls[0][1]["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert stopped == [process]


def test_candidate_is_stopped_when_contract_gate_fails(monkeypatch, tmp_path):
    manifest = write_manifest(tmp_path / "peers.json")
    release_root = tmp_path / "releases"
    release_dir = release_root / "release-a"
    release_dir.mkdir(parents=True)
    for relative in canary.REQUIRED_RUNTIME:
        target = release_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# test\n", encoding="utf-8")
        target.chmod(0o644)
    process = SimpleNamespace(pid=12345, poll=lambda: None)
    stopped = []
    calls = {"count": 0}

    def validate(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "status": "passed",
                "state_namespace": "kolibri_factory",
                "membership_projection": {"registered_total": 2},
                "fleet_proof_projection": {"fresh_total": 2},
            }
        raise canary.CanaryError("candidate_contract_failed")

    clock = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(canary, "assert_local_home_control_plane", lambda **kwargs: "10.99.0.1")
    monkeypatch.setattr(canary, "_available_loopback_port", lambda: 19999)
    monkeypatch.setattr(canary.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(canary, "_stop_candidate", lambda value: stopped.append(value))
    monkeypatch.setattr(canary, "validate_contracts", validate)
    monkeypatch.setattr(canary.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(canary.time, "sleep", lambda _seconds: None)

    with pytest.raises(canary.CanaryError, match="candidate_startup_timeout"):
        canary.run_candidate(
            release_dir,
            manifest,
            release_root=release_root,
            startup_timeout=1,
        )

    assert stopped == [process]


def test_post_gate_maps_incomplete_previous_release_to_honest_legacy_identity(tmp_path):
    release_root = tmp_path / "releases"
    previous = release_root / "previous"
    previous.mkdir(parents=True)
    assert canary.expected_live_release_id(previous, release_root) == "legacy-bootstrap"

    for relative in canary.REQUIRED_RUNTIME:
        target = previous / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# test\n", encoding="utf-8")
        target.chmod(0o644)
    assert canary.expected_live_release_id(previous, release_root) == "previous"


def test_launcher_prefers_complete_direct_child_immutable_release(monkeypatch, tmp_path):
    release_root = tmp_path / "releases"
    release_dir = release_root / "release-a"
    legacy = tmp_path / "legacy"
    release_dir.mkdir(parents=True)
    legacy.mkdir()
    current = tmp_path / "current"
    current.symlink_to(release_dir)
    for root in (release_dir, legacy):
        for relative in launcher.REQUIRED_RUNTIME:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# test\n", encoding="utf-8")
            target.chmod(0o644)
    records = []
    for relative in launcher.REQUIRED_RUNTIME:
        payload = (release_dir / relative).read_bytes()
        records.append({
            "path": relative,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "mode": "0644",
        })
    manifest_path = release_dir / ".kolibri-release/manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps(
        {"release_id": "release-a", "files": records},
        sort_keys=True,
        separators=(",", ":"),
    ), encoding="utf-8")
    manifest_path.chmod(0o644)
    monkeypatch.setattr(launcher, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(launcher, "CURRENT_LINK", current)
    monkeypatch.setattr(launcher, "LEGACY_ROOT", legacy)

    selected, release_id, source = launcher.select_runtime()
    assert selected == release_dir.resolve()
    assert release_id == "release-a"
    assert source == "immutable-release"


def test_launcher_uses_trusted_split_legacy_bootstrap_for_product_only_current(
    monkeypatch,
    tmp_path,
):
    release_root = tmp_path / "releases"
    release_dir = release_root / "product-only"
    release_dir.mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(release_dir)
    product = release_dir / "backend/main.py"
    product.parent.mkdir()
    product.write_text("app = object()\n", encoding="utf-8")
    product.chmod(0o644)
    payload = product.read_bytes()
    manifest_path = release_dir / ".kolibri-release/manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps({
        "release_id": release_dir.name,
        "files": [{
            "path": "backend/main.py",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
            "mode": "0644",
        }],
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    manifest_path.chmod(0o644)
    legacy_root = tmp_path / "absent-legacy-root"
    legacy_bin = tmp_path / "bin"
    legacy_lib = tmp_path / "lib"
    legacy_bin.mkdir()
    legacy_lib.mkdir()
    entrypoint = legacy_bin / "kolibri-factory-control"
    entrypoint.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    for relative in launcher.REQUIRED_RUNTIME:
        if relative == "ops/factory_control.py":
            continue
        target = legacy_lib / Path(relative).name
        target.write_text("# trusted legacy dependency\n", encoding="utf-8")
        target.chmod(0o644)

    monkeypatch.setattr(launcher, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(launcher, "CURRENT_LINK", current)
    monkeypatch.setattr(launcher, "LEGACY_ROOT", legacy_root)
    monkeypatch.setattr(launcher, "LEGACY_SPLIT_ENTRYPOINT", entrypoint)
    monkeypatch.setattr(launcher, "LEGACY_SPLIT_LIBRARY_ROOT", legacy_lib)

    selected, release_id, source = launcher.select_runtime()

    assert selected == legacy_lib
    assert release_id == "legacy-bootstrap"
    assert source == "legacy-split-bootstrap"


def test_launcher_split_legacy_bootstrap_fails_closed_on_unsafe_dependency(
    monkeypatch,
    tmp_path,
):
    legacy_bin = tmp_path / "bin"
    legacy_lib = tmp_path / "lib"
    legacy_bin.mkdir()
    legacy_lib.mkdir()
    entrypoint = legacy_bin / "kolibri-factory-control"
    entrypoint.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    for relative in launcher.REQUIRED_RUNTIME:
        if relative == "ops/factory_control.py":
            continue
        target = legacy_lib / Path(relative).name
        target.write_text("# dependency\n", encoding="utf-8")
        target.chmod(0o644)
    (legacy_lib / "fleet_membership.py").chmod(0o666)

    monkeypatch.setattr(launcher, "CURRENT_LINK", tmp_path / "missing-current")
    monkeypatch.setattr(launcher, "LEGACY_ROOT", tmp_path / "missing-legacy")
    monkeypatch.setattr(launcher, "LEGACY_SPLIT_ENTRYPOINT", entrypoint)
    monkeypatch.setattr(launcher, "LEGACY_SPLIT_LIBRARY_ROOT", legacy_lib)

    with pytest.raises(launcher.LauncherError, match="runtime_unavailable"):
        launcher.select_runtime()


def test_launcher_execs_split_bootstrap_without_writing_bytecode(monkeypatch, tmp_path):
    legacy_lib = tmp_path / "lib"
    legacy_lib.mkdir()
    entrypoint = tmp_path / "kolibri-factory-control"
    entrypoint.write_text("#!/usr/bin/python3\n", encoding="utf-8")
    entrypoint.chmod(0o755)
    python = tmp_path / "python3"
    python.write_text("#!/bin/sh\n", encoding="utf-8")
    python.chmod(0o755)
    observed = {}

    class ExecObserved(Exception):
        pass

    def fake_execve(executable, argv, environment):
        observed.update({"executable": executable, "argv": argv, "environment": environment})
        raise ExecObserved

    monkeypatch.setattr(launcher, "assert_local_home_control_plane", lambda: None)
    monkeypatch.setattr(
        launcher,
        "select_runtime",
        lambda: (legacy_lib, "legacy-bootstrap", "legacy-split-bootstrap"),
    )
    monkeypatch.setattr(launcher, "LEGACY_SPLIT_ENTRYPOINT", entrypoint)
    monkeypatch.setattr(launcher, "LEGACY_SPLIT_LIBRARY_ROOT", legacy_lib)
    monkeypatch.setattr(launcher, "PYTHON", python)
    monkeypatch.setattr(launcher.os, "execve", fake_execve)

    with pytest.raises(ExecObserved):
        launcher.main(["--example-flag"])

    assert observed["executable"] == str(python)
    assert observed["argv"] == [str(python), "-B", str(entrypoint), "--example-flag"]
    assert observed["environment"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert observed["environment"]["PYTHONPATH"] == str(legacy_lib)


def test_launcher_fails_closed_on_partial_declared_immutable_runtime(monkeypatch, tmp_path):
    release_root = tmp_path / "releases"
    release_dir = release_root / "release-a"
    release_dir.mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(release_dir)
    runtime = release_dir / "ops/factory_control.py"
    runtime.parent.mkdir()
    runtime.write_text("# partial\n", encoding="utf-8")
    payload = runtime.read_bytes()
    manifest_path = release_dir / ".kolibri-release/manifest.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(json.dumps({
        "release_id": "release-a",
        "files": [{
            "path": "ops/factory_control.py",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size_bytes": len(payload),
        }],
    }, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    monkeypatch.setattr(launcher, "RELEASE_ROOT", release_root)
    monkeypatch.setattr(launcher, "CURRENT_LINK", current)

    with pytest.raises(launcher.LauncherError, match="runtime_incomplete"):
        launcher._immutable_root()
