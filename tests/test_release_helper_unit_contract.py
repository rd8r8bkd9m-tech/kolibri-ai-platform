import socket
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from ops.release_helper import ReleaseHelperProtocolError, ReleaseHelperServer


ROOT = Path(__file__).resolve().parents[1]


def test_release_helper_uses_a_root_owned_dedicated_artifact_boundary():
    unit = (ROOT / "ops" / "systemd" / "kolibri-release-helper.service").read_text(
        encoding="utf-8"
    )

    assert "KOLIBRI_ARTIFACT_ROOT=/var/lib/kolibri-release/artifacts" in unit
    assert "/var/lib/kolibri-release/artifacts" in unit
    assert "KOLIBRI_ARTIFACT_ROOT=/var/lib/kolibri-agent/artifacts" not in unit
    assert "ReadWritePaths=/opt/kolibri-ai /var/lib/kolibri-release/artifacts" in unit


class RecordingInstaller:
    def __init__(self, artifact_root: Path):
        self.config = SimpleNamespace(artifact_root=artifact_root)
        self.evidence_dir: Path | None = None

    def execute(self, kind, envelope, evidence_dir, *, progress_callback=None):
        self.evidence_dir = evidence_dir
        assert kind == "release_bundle_apply"
        assert envelope["task_id"] == "release-task-1"
        assert progress_callback is not None
        progress_callback()
        (evidence_dir / "release-installer.jsonl").write_text(
            "sanitized\n", encoding="utf-8"
        )
        return {"status": "completed"}


def release_request(**envelope_overrides):
    envelope = {
        "task_id": "release-task-1",
        "attempt_id": "release-task-1-attempt-1",
    }
    envelope.update(envelope_overrides)
    return {
        "protocol_version": "kolibri.release-helper.v1",
        "operation": "execute",
        "kind": "release_bundle_apply",
        "envelope": envelope,
        "evidence_dir": "/var/lib/kolibri-agent/artifacts/untrusted-attempt",
    }


def test_release_helper_maps_agent_evidence_to_private_root_namespace(tmp_path):
    artifact_root = tmp_path / "release-artifacts"
    artifact_root.mkdir(mode=0o700)
    installer = RecordingInstaller(artifact_root)
    server = ReleaseHelperServer(installer, allowed_uid=1234)
    server_socket, client_socket = socket.socketpair()
    try:
        result = server._dispatch(release_request(), server_socket)
    finally:
        server_socket.close()
        client_socket.close()

    expected = (
        artifact_root
        / ".evidence"
        / "release-task-1"
        / "release-task-1-attempt-1"
    )
    assert installer.evidence_dir == expected
    assert result["status"] == "ok"
    assert result["result"]["status"] == "completed"
    evidence = result["result"]["release_evidence"]
    assert evidence["scope"] == "privileged_helper"
    assert evidence["retention"] == "root_only"
    assert evidence["ref"].startswith("sha256:")
    assert str(expected) not in str(result)
    assert (expected / "release-installer.jsonl").read_text(encoding="utf-8") == "sanitized\n"
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o700
        for path in (artifact_root / ".evidence", expected.parent, expected)
    )
    assert not (tmp_path / "var/lib/kolibri-agent/artifacts/untrusted-attempt").exists()


def test_release_helper_rejects_invalid_identity_and_unsafe_evidence_namespace(
    tmp_path,
):
    artifact_root = tmp_path / "release-artifacts"
    artifact_root.mkdir(mode=0o700)
    installer = RecordingInstaller(artifact_root)
    server = ReleaseHelperServer(installer, allowed_uid=1234)
    server_socket, client_socket = socket.socketpair()
    try:
        with pytest.raises(
            ReleaseHelperProtocolError,
            match="release_helper_evidence_identity_invalid",
        ):
            server._dispatch(release_request(task_id="../escape"), server_socket)
    finally:
        server_socket.close()
        client_socket.close()

    outside = tmp_path / "outside"
    outside.mkdir(mode=0o700)
    (artifact_root / ".evidence").symlink_to(outside, target_is_directory=True)
    server_socket, client_socket = socket.socketpair()
    try:
        with pytest.raises(
            ReleaseHelperProtocolError,
            match="release_helper_evidence_boundary_invalid",
        ):
            server._dispatch(release_request(), server_socket)
    finally:
        server_socket.close()
        client_socket.close()
