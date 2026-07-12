import argparse
import base64
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_agent_host_generates_telegram_image_with_configured_command(
    tmp_path, monkeypatch, canonical_home_control_plane
):
    agent_host = load_agent_host()
    command = (
        "python3 -c \"import base64, os, pathlib; "
        "pathlib.Path(os.environ['KOLIBRI_IMAGE_OUTPUT_PATH']).write_bytes("
        f"base64.b64decode('{TINY_PNG_B64}'))\""
    )
    monkeypatch.setenv("KOLIBRI_IMAGE_GENERATOR_CMD", command)

    class Host(agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return body

    args = argparse.Namespace(
        control_url=canonical_home_control_plane,
        node_id="primary-candidate",
        agent_id="agent-host-primary",
        capabilities="image_generation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )
    host = Host(args)
    task = {
        "task_id": "TGIMG-1",
        "attempt": 1,
        "attempt_id": "TGIMG-1-attempt-1",
        "envelope": {
            "kind": "telegram_image_generation",
            "prompt": "Нарисуй птичку Колибри",
            "caption": "Готово.",
        },
    }

    result = host.run_telegram_image_generation(task)

    image_path = Path(result["image_path"])
    assert image_path.exists()
    assert image_path.read_bytes() == base64.b64decode(TINY_PNG_B64)
    assert result["kind"] == "telegram_image_generation"
    assert result["image_mime_type"] == "image/png"
    assert result["caption"] == "Готово."
    assert result["image_b64"] == TINY_PNG_B64
    assert result["image_evidence"]["schema_version"] == agent_host.IMAGE_EVIDENCE_SCHEMA
    assert result["image_evidence"]["verdict"] == "passed"
    assert result["image_evidence"]["content_sha256"] == agent_host.sha256_file(image_path)
    assert result["image_evidence"]["size_bytes"] == image_path.stat().st_size
    assert len(result["image_evidence"]["binding_sha256"]) == 64
    assert "OPENAI_API_KEY" not in result
    assert any(path.endswith("/heartbeat") for path, _ in host.posts)


def test_agent_host_rejects_extension_only_fake_image(
    tmp_path, monkeypatch, canonical_home_control_plane
):
    agent_host = load_agent_host()
    command = (
        "python3 -c \"import os, pathlib; "
        "pathlib.Path(os.environ['KOLIBRI_IMAGE_OUTPUT_PATH']).write_text('not an image')\""
    )
    monkeypatch.setenv("KOLIBRI_IMAGE_GENERATOR_CMD", command)

    class Host(agent_host.AgentHost):
        def post(self, _path, body):
            return body

    host = Host(argparse.Namespace(
        control_url=canonical_home_control_plane,
        node_id="image-worker",
        agent_id="agent-host-image",
        capabilities="image_generation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    ))
    task = {
        "task_id": "IMG-FAKE",
        "attempt": 1,
        "attempt_id": "IMG-FAKE-attempt-1",
        "fencing_token": 1,
        "envelope": {"kind": "image_generation", "prompt": "Нарисуй дом"},
    }
    with pytest.raises(RuntimeError, match="unsupported image container"):
        host.run_telegram_image_generation(task)


def test_agent_host_rejects_legacy_control_plane_failover(tmp_path):
    agent_host = load_agent_host()
    args = argparse.Namespace(
        control_url="http://home-control:9101",
        control_urls="http://home-control:9101,http://legacy-control:9101",
        node_id="primary-candidate",
        agent_id="agent-host-primary",
        capabilities="generic_implementation",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )

    with pytest.raises(RuntimeError, match="multiple_control_plane_authorities_forbidden"):
        agent_host.AgentHost(args)


def test_image_capability_is_derived_from_runtime_configuration(
    tmp_path, monkeypatch, canonical_home_control_plane
):
    agent_host = load_agent_host()
    monkeypatch.delenv("KOLIBRI_IMAGE_GENERATOR_CMD", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def host():
        return agent_host.AgentHost(argparse.Namespace(
            control_url=canonical_home_control_plane,
            node_id="image-capability-worker",
            agent_id="agent-host-image-capability",
            capabilities="read_only_probe,image_generation",
            repo_url="https://example.invalid/repo.git",
            work_root=str(tmp_path / "work"),
            artifact_root=str(tmp_path / "artifacts"),
            heartbeat_interval=10,
            lease_refresh=20,
            max_inflight=1,
        ))

    unavailable = host()
    assert "image_generation" not in unavailable.configured_capabilities
    assert "image_generation" not in unavailable.capabilities

    monkeypatch.setenv("KOLIBRI_IMAGE_GENERATOR_CMD", "true")
    available = host()
    assert "image_generation" not in available.configured_capabilities
    assert "image_generation" in available.capabilities
