import argparse
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_agent_host():
    spec = importlib.util.spec_from_file_location("agent_host", ROOT / "ops" / "agent_host.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def make_args(tmp_path, control_url):
    return argparse.Namespace(
        control_url=control_url,
        node_id="server-node-1",
        agent_id="agent-host-server-node-1",
        capabilities="generic_implementation,read_only_probe",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
    )


class RecordingHost:
    def post(self, path, body):
        self.posts.append((path, body))
        return body


def test_gomesh_read_only_permission_pack_evidence_is_classified(
    tmp_path, canonical_home_control_plane
):
    agent_host = load_agent_host()

    class Host(RecordingHost, agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []

    host = Host(make_args(tmp_path, canonical_home_control_plane))
    task = {
        "task_id": "GOMESH-RO-1",
        "kind": "read_only_probe",
        "attempt": 1,
        "attempt_id": "GOMESH-RO-1-attempt-1",
        "envelope": {
            "kind": "read_only_probe",
            "permission_pack": "gomesh_read_only_no_push",
            "permissions": {"read_only": True},
        },
    }

    result = host.run_read_only_probe(task)

    classification = result["permission_pack_classification"]
    assert classification["contract"] == "agent_host_permission_pack_runtime_gate"
    assert classification["domain"] == "gomesh"
    assert classification["read_only_no_push"] is True
    assert classification["decision"] == "allowed"
    assert "gomesh_read_only_no_push" in classification["permission_packs"]
    assert {"field": "permission_pack", "value": "gomesh_read_only_no_push"} in classification["evidence"]

    result_path = Path(result["result_path"])
    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert persisted["permission_pack_classification"] == classification


def test_read_only_no_push_envelope_blocks_write_worktree_and_git_push_runtime(
    tmp_path, canonical_home_control_plane
):
    agent_host = load_agent_host()

    class Host(RecordingHost, agent_host.AgentHost):
        def __init__(self, args):
            super().__init__(args)
            self.posts = []
            self.impl_called = False

        def run_impl_factory_smoke(self, task):
            del task
            self.impl_called = True
            raise AssertionError("write-capable runner must not execute")

    host = Host(make_args(tmp_path, canonical_home_control_plane))
    task = {
        "task_id": "GOMESH-RO-BLOCK-1",
        "kind": "impl_factory_smoke",
        "attempt": 1,
        "attempt_id": "GOMESH-RO-BLOCK-1-attempt-1",
        "max_retries": 3,
        "envelope": {
            "kind": "impl_factory_smoke",
            "permission_pack": "gomesh_read_only_no_push",
            "permissions": ["full_autonomy", "git_push", "write_worktree"],
        },
    }

    host.run_task(task)

    assert host.impl_called is False
    fail_posts = [(path, body) for path, body in host.posts if path.endswith("/fail")]
    assert len(fail_posts) == 1
    _, fail_body = fail_posts[0]
    assert fail_body["error_type"] == "permission_contract_violation"
    assert fail_body["retry"] is False
    classification = fail_body["result"]["permission_pack_classification"]
    assert classification["domain"] == "gomesh"
    assert classification["decision"] == "blocked"
    assert classification["read_only_no_push"] is True
    assert classification["forbidden_permissions"] == ["full_autonomy", "git_push", "write_worktree"]

    result_path = Path(fail_body["result_reference"])
    persisted = json.loads(result_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "blocked"
    assert persisted["permission_pack_classification"] == classification
