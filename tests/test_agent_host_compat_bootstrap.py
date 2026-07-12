import argparse
import json
from pathlib import Path

import pytest

from ops import agent_host as agent_host_module
from ops import agent_host_compat_bootstrap as compat


ROOT = Path(__file__).resolve().parents[1]


def write_manifest(path: Path, worker_count: int = 20) -> Path:
    peers = {"10.88.0.1": {"node_id": "home", "mesh_ip": "10.88.0.1"}}
    for index in range(worker_count):
        ip = f"10.88.1.{index + 1}"
        peers[ip] = {"node_id": f"worker-{index:02d}", "mesh_ip": ip}
    path.write_text(
        json.dumps({"schema_version": 1, "epoch": 7, "peers": peers}),
        encoding="utf-8",
    )
    return path


class FakeRunner:
    def __init__(self):
        self.commands = []

    def run(self, command, *, check=False, timeout=30):
        del check, timeout
        self.commands.append(tuple(command))
        if "show" in command and "NRestarts" in command:
            return compat.CommandResult(0, "0\n", "")
        return compat.CommandResult(0, "", "")


def prepare_fake_root(root: Path) -> None:
    values = {
        "/etc/kolibri-agent-host.env": b"KOLIBRI_NODE_ID=worker-00\n",
        "/var/lib/kolibri-mesh/peers.json": b'{"preserved":true}\n',
        "/usr/local/bin/kolibri-agent-host": b"old-agent-host\n",
    }
    for logical, payload in values.items():
        path = root / logical.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        path.chmod(0o600)


def test_dynamic_plan_excludes_home_and_uses_digest_seeded_waves(tmp_path):
    manifest = write_manifest(tmp_path / "peers.json")

    first = compat.compatibility_plan(
        source_root=ROOT,
        manifest_path=manifest,
        minimum_workers=20,
    )
    second = compat.compatibility_plan(
        source_root=ROOT,
        manifest_path=manifest,
        minimum_workers=20,
    )

    assert first == second
    assert [len(wave["nodes"]) for wave in first["waves"]] == [1, 2, 3, 5, 9]
    assert "home" not in {node for wave in first["waves"] for node in wave["nodes"]}
    assert first["canonical_worker_total"] == 20
    assert first["selected_worker_total"] == 20
    assert first["mode"] == "dry-run"


def test_canary_only_plan_selects_exactly_one_dynamic_worker(tmp_path):
    manifest = write_manifest(tmp_path / "peers.json")

    plan = compat.compatibility_plan(
        source_root=ROOT,
        manifest_path=manifest,
        minimum_workers=20,
        canary_only=True,
    )

    assert plan["canary_only"] is True
    assert plan["selected_worker_total"] == 1
    assert plan["waves"] == [
        {"name": "compat-canary", "nodes": plan["waves"][0]["nodes"]}
    ]
    assert len(plan["waves"][0]["nodes"]) == 1


def test_home_is_rejected_by_default_and_explicit_mode_has_distinct_exact_plan(
    tmp_path,
):
    manifest = write_manifest(tmp_path / "peers.json")
    worker_plan = compat.compatibility_plan(
        source_root=ROOT,
        manifest_path=manifest,
    )
    home_plan = compat.compatibility_plan(
        source_root=ROOT,
        manifest_path=manifest,
        home_node_mode=True,
    )

    assert worker_plan["home_excluded"] is True
    assert worker_plan["home_node_mode"] is False
    assert "home" not in {
        node for wave in worker_plan["waves"] for node in wave["nodes"]
    }
    assert home_plan["home_excluded"] is False
    assert home_plan["home_node_mode"] is True
    assert home_plan["waves"] == [
        {"name": "compat-home-worker", "nodes": ["home"]}
    ]
    assert home_plan["selected_node_total"] == 1
    assert home_plan["selected_worker_total"] == 0
    assert home_plan["plan_digest"] != worker_plan["plan_digest"]

    fake_root = tmp_path / "default-root"
    prepare_fake_root(fake_root)
    bootstrap = compat.NodeBootstrap(
        source_root=ROOT,
        manifest_path=manifest,
        node_id="home",
        run_id="home-default-rejected",
        approved_plan_digest=worker_plan["plan_digest"],
        root=fake_root,
        runner=FakeRunner(),
        local_addresses=["10.88.0.1"],
        stability_seconds=0,
    )
    with pytest.raises(
        compat.BootstrapError, match="agent_host_compat_home_opt_in_required"
    ):
        bootstrap.plan()

    wrong_digest = compat.NodeBootstrap(
        source_root=ROOT,
        manifest_path=manifest,
        node_id="home",
        run_id="home-wrong-plan-rejected",
        approved_plan_digest=worker_plan["plan_digest"],
        root=fake_root,
        runner=FakeRunner(),
        local_addresses=["10.88.0.1"],
        stability_seconds=0,
        home_node_mode=True,
    )
    with pytest.raises(compat.BootstrapError, match="agent_host_compat_plan_changed"):
        wrong_digest.plan()

    worker_in_home_mode = compat.NodeBootstrap(
        source_root=ROOT,
        manifest_path=manifest,
        node_id="worker-00",
        run_id="worker-home-mode-rejected",
        approved_plan_digest=home_plan["plan_digest"],
        root=fake_root,
        runner=FakeRunner(),
        local_addresses=["10.88.1.1"],
        stability_seconds=0,
        home_node_mode=True,
    )
    with pytest.raises(
        compat.BootstrapError, match="agent_host_compat_home_mode_requires_home"
    ):
        worker_in_home_mode.plan()


def test_explicit_home_mode_applies_only_agent_host_paths_and_rolls_back(tmp_path):
    manifest = write_manifest(tmp_path / "peers.json")
    fake_root = tmp_path / "home-root"
    prepare_fake_root(fake_root)
    control = fake_root / "usr/local/bin/kolibri-factory-control"
    control.parent.mkdir(parents=True, exist_ok=True)
    control.write_bytes(b"control-plane-stable\n")
    control.chmod(0o755)
    control_before = control.read_bytes()
    membership_runtime = fake_root / "usr/local/lib/kolibri/fleet_membership.py"
    membership_runtime.parent.mkdir(parents=True, exist_ok=True)
    membership_runtime.write_bytes(b"old-membership-runtime\n")
    membership_runtime.chmod(0o644)
    membership_before = membership_runtime.read_bytes()
    plan = compat.compatibility_plan(
        source_root=ROOT,
        manifest_path=manifest,
        home_node_mode=True,
    )
    runner = FakeRunner()
    bootstrap = compat.NodeBootstrap(
        source_root=ROOT,
        manifest_path=manifest,
        node_id="home",
        run_id="home-agent-host-opt-in",
        approved_plan_digest=plan["plan_digest"],
        root=fake_root,
        runner=runner,
        local_addresses=["10.88.0.1"],
        stability_seconds=0,
        home_node_mode=True,
    )

    planned = bootstrap.plan()
    applied = bootstrap.apply()

    assert planned["home_node_mode"] is True
    assert planned["plan_digest"] == plan["plan_digest"]
    assert "/usr/local/lib/kolibri/fleet_membership.py" in planned["changed_paths"]
    assert all("factory-control" not in path for path in planned["changed_paths"])
    assert applied["status"] == "applied"
    assert control.read_bytes() == control_before
    assert membership_runtime.read_bytes() == (ROOT / "ops/fleet_membership.py").read_bytes()
    touched_services = {
        argument
        for command in runner.commands
        if command and command[0] == "/usr/bin/systemctl"
        for argument in command
        if argument.endswith(".service")
    }
    assert touched_services == {"kolibri-agent-host.service"}

    rolled_back = bootstrap.rollback()
    assert rolled_back["status"] == "rolled_back"
    assert control.read_bytes() == control_before
    assert membership_runtime.read_bytes() == membership_before


def test_node_bootstrap_is_idempotent_preserves_runtime_inputs_and_rolls_back(tmp_path):
    manifest = write_manifest(tmp_path / "peers.json")
    fake_root = tmp_path / "root"
    prepare_fake_root(fake_root)
    before_preserved = {
        path: (fake_root / path.lstrip("/")).read_bytes()
        for path in compat.PRESERVED_PATHS
    }
    plan = compat.compatibility_plan(source_root=ROOT, manifest_path=manifest)
    runner = FakeRunner()
    bootstrap = compat.NodeBootstrap(
        source_root=ROOT,
        manifest_path=manifest,
        node_id="worker-00",
        run_id="compat-test-1",
        approved_plan_digest=plan["plan_digest"],
        root=fake_root,
        runner=runner,
        local_addresses=["10.88.1.1"],
        stability_seconds=0,
    )

    applied = bootstrap.apply()

    assert applied["status"] == "applied"
    assert applied["service"]["stability_seconds"] == 0
    assert (fake_root / "usr/local/bin/kolibri-agent-host").read_bytes() == (
        ROOT / "ops/agent_host.py"
    ).read_bytes()
    assert (fake_root / "etc/kolibri/runner-access.json").read_bytes() == (
        ROOT / "ops/runner-access.default.json"
    ).read_bytes()
    assert {
        path: (fake_root / path.lstrip("/")).read_bytes()
        for path in compat.PRESERVED_PATHS
    } == before_preserved
    touched_services = {
        argument
        for command in runner.commands
        if command and command[0] == "/usr/bin/systemctl"
        for argument in command
        if argument.endswith(".service")
    }
    assert touched_services == {"kolibri-agent-host.service"}

    second = bootstrap.apply()
    assert second["status"] == "already_converged"
    assert second["restarted"] is False

    rolled_back = bootstrap.rollback()
    assert rolled_back["status"] == "rolled_back"
    assert (fake_root / "usr/local/bin/kolibri-agent-host").read_bytes() == b"old-agent-host\n"
    assert not (fake_root / "etc/kolibri/runner-access.json").exists()
    assert not (fake_root / "usr/local/lib/kolibri/release_helper.py").exists()
    assert not (fake_root / "usr/local/lib/kolibri/fleet_membership.py").exists()


class FakeControlPlane:
    def __init__(self):
        self.requests = []

    def request(self, method, path, payload=None):
        self.requests.append((method, path, payload))
        if path.startswith("/v1/nodes/"):
            return {
                "node_id": "worker-00",
                "capabilities": [compat.LONG_PROBE_KIND, compat.RELEASE_CAPABILITY],
            }
        if method == "POST":
            return {"task_id": "LONG-PROOF-1"}
        return {
            "task_id": "LONG-PROOF-1",
            "state": "completed",
            "attempt_id": "LONG-PROOF-1-attempt-1",
            "fencing_token": 9,
            "lease_owner": "worker-00:worker-00-agent-host",
            "result_reference": "/artifacts/LONG-PROOF-1/result.json",
            "result": {
                "task_id": "LONG-PROOF-1",
                "attempt_id": "LONG-PROOF-1-attempt-1",
                "fencing_token": 9,
                "node_id": "worker-00",
                "result_path": "/artifacts/LONG-PROOF-1/result.json",
                "lease_heartbeat_probe": {
                    "observed_duration_seconds": 65.1,
                    "heartbeat_count": 14,
                },
            },
            "completion_verifier": {
                "verdict": "passed",
                "independent": True,
                "verifier": "control-plane/home",
            },
        }


def test_long_probe_requires_attempt_fence_result_and_home_verifier():
    client = FakeControlPlane()

    proof = compat.submit_long_probe(
        client=client,
        node_id="worker-00",
        campaign_id="compat-campaign-1",
        duration_seconds=65,
        poll_seconds=0,
    )

    assert proof["status"] == "completed"
    assert all(proof["checks"].values())
    payload = next(payload for method, _path, payload in client.requests if method == "POST")
    assert payload["kind"] == compat.LONG_PROBE_KIND
    assert payload["proof_duration_seconds"] == 65
    assert payload["max_attempts"] == 2
    assert "max_retries" not in payload


def test_agent_host_runs_bounded_long_probe_with_repeated_authoritative_heartbeats(
    tmp_path, monkeypatch
):
    manifest = tmp_path / "mesh.json"
    manifest.write_text(
        json.dumps({"peers": [{"node_id": "home", "mesh_ip": "10.88.0.1"}]}),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        control_url="http://10.88.0.1:9101",
        control_urls=None,
        mesh_membership_manifest=str(manifest),
        node_id="worker-test",
        agent_id="worker-test-agent-host",
        capabilities="read_only_probe",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=5,
        max_inflight=1,
    )

    class Host(agent_host_module.AgentHost):
        def __init__(self):
            super().__init__(args)
            self.posts = []

        def post(self, path, body):
            self.posts.append((path, body))
            return {"state": "running"}

    clock = [0.0]
    monkeypatch.setattr(agent_host_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        agent_host_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )
    host = Host()
    task = {
        "task_id": "LEASE-PROOF-1",
        "kind": agent_host_module.LEASE_HEARTBEAT_PROBE_KIND,
        "attempt_id": "LEASE-PROOF-1-attempt-1",
        "fencing_token": 4,
        "envelope": {
            "kind": agent_host_module.LEASE_HEARTBEAT_PROBE_KIND,
            "proof_duration_seconds": 61,
            "permission_pack": "read_only",
            "read_only": True,
            "no_push": True,
        },
    }

    result = host.run_lease_heartbeat_probe(task)

    assert result["status"] == "completed"
    assert result["lease_heartbeat_probe"]["observed_duration_seconds"] >= 61
    assert result["lease_heartbeat_probe"]["heartbeat_count"] >= 13
    task_heartbeats = [path for path, _body in host.posts if path.endswith("/heartbeat")]
    assert len(task_heartbeats) >= 13
    assert agent_host_module.LEASE_HEARTBEAT_PROBE_KIND in host.capabilities


def test_bootstrap_source_contains_no_remote_transport_or_legacy_authority():
    source = (ROOT / "ops/agent_host_compat_bootstrap.py").read_text(encoding="utf-8")

    assert "subprocess.run" in source
    assert "scp" not in source
    assert '"ssh"' not in source
    assert "10.99." not in source
    assert 'node_id == "home"' in source
    assert "--home-node-mode" in source
    assert '"ops/fleet_membership.py"' in source
    assert "kolibri-factory-control.service" not in source
    assert "/etc/kolibri-agent-host.env" in source
    assert "_atomic_write(self._path(preserved" not in source
