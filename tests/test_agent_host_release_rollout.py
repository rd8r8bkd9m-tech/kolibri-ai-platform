import argparse
import hashlib
import json
from pathlib import Path

import pytest

from ops import agent_host as agent_host_module
from ops import agent_host_release_rollout as rollout
from ops import release_controller as release


def manifest(release_id="agent-host-v2", byte="a"):
    return release.ReleaseManifest(
        release_id=release_id,
        source_commit="0123456789abcdef",
        artifact_uri=f"artifact://releases/{release_id}.tar.gz",
        files=(
            release.ReleaseFile("ops/agent_host.py", byte * 64, 4096, "0755"),
            release.ReleaseFile(
                "ops/mimo/kolibri-response-only.md", "d" * 64, 512, "0644"
            ),
            release.ReleaseFile("ops/release_installer.py", "c" * 64, 2048, "0644"),
        ),
        metadata={"component": "agent-host"},
    )


def verified(release_id="agent-host-v2", byte="a"):
    return release.VerifiedRelease(manifest(release_id, byte), "owner")


def node(name, *, role="worker", domain=None):
    return release.FleetNode(
        node_id=name,
        physical_node_id=f"physical-{name}",
        freshness="fresh",
        health="online",
        draining=False,
        capabilities=(release.RELEASE_CAPABILITY, rollout.HANDSHAKE_CAPABILITY),
        agent_live=True,
        role=role,
        failure_domain=domain,
        agent_id=f"agent-{name}",
    )


def raw_handshake(target, target_release, *, task_id=None):
    task_id = task_id or f"probe-{target.node_id}"
    attempt_id = f"{task_id}-attempt-1"
    reference = f"/artifacts/{task_id}/result.json"
    runtime_path, runtime_sha256 = rollout._runtime_record(target_release)
    profile_path, profile_sha256 = rollout._response_profile_record(target_release)
    result = {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "node_id": target.node_id,
        "agent_id": f"agent-{target.node_id}",
        "status": "completed",
        "kind": "read_only_probe",
        "result_path": reference,
        "agent_host_runtime": {
            "schema_version": rollout.AGENT_HOST_RUNTIME_SCHEMA,
            "status": "release_bound",
            "release_id": target_release.manifest.release_id,
            "manifest_digest": target_release.manifest.digest,
            "runtime_path": runtime_path,
            "runtime_sha256": runtime_sha256,
            "response_profile_path": profile_path,
            "response_profile_sha256": profile_sha256,
        },
    }
    return {
        "task_id": task_id,
        "attempt_id": attempt_id,
        "lease_owner": f"{target.node_id}:agent-{target.node_id}",
        "state": "completed",
        "envelope": {"target_node": target.node_id},
        "result_reference": reference,
        "result": result,
    }


def add_strict_proof(task):
    result_sha256 = rollout._canonical_json_sha256(task["result"])
    binding_sha256 = rollout._binding_sha256(
        task, task["result_reference"], result_sha256
    )
    node_id, _, agent_id = task["lease_owner"].partition(":")
    task["completion_evidence"] = {
        "schema_version": rollout.COMPLETION_EVIDENCE_SCHEMA,
        "task_id": task["task_id"],
        "attempt_id": task["attempt_id"],
        "lease_owner": task["lease_owner"],
        "node_id": node_id,
        "agent_id": agent_id,
        "result_reference": task["result_reference"],
        "result_sha256": result_sha256,
        "binding_sha256": binding_sha256,
    }
    task["completion_verifier"] = {
        "schema_version": rollout.COMPLETION_VERIFIER_SCHEMA,
        "verifier": "control-plane/home",
        "independent": True,
        "verdict": "passed",
        "node_id": node_id,
        "agent_id": agent_id,
        "result_sha256": result_sha256,
        "binding_sha256": binding_sha256,
        "checks": {
            "task": True,
            "attempt": True,
            "node": True,
            "agent": True,
            "status": True,
            "result_reference": True,
            "result_sha256": True,
            "binding_sha256": True,
        },
        "failed_checks": [],
    }
    return task


@pytest.mark.parametrize("fleet_size,rest_size", [(21, 9), (22, 10)])
def test_dynamic_rollout_assigns_21_or_more_without_static_stage_labels(
    fleet_size, rest_size
):
    target_release = verified()
    fleet = [node("authority", role="control_plane")]
    fleet.extend(
        node(f"worker-{index:02d}", domain=f"rack-{index % 4}")
        for index in range(fleet_size - 1)
    )

    waves = rollout.plan_dynamic_agent_host_rollout(
        fleet,
        release_digest=target_release.manifest.digest,
        minimum_nodes=21,
    )

    assert [wave.name for wave in waves] == [
        "agent-host-canary",
        "agent-host-quorum",
        "agent-host-workers-3",
        "agent-host-workers-5",
        "agent-host-workers-rest",
        "agent-host-control-plane-last",
    ]
    assert [len(wave.nodes) for wave in waves] == [1, 2, 3, 5, rest_size, 1]
    assert waves[-1].nodes[0].role == "control_plane"
    planned = [item.physical_node_id for wave in waves for item in wave.nodes]
    assert len(planned) == len(set(planned)) == fleet_size
    assert rollout.plan_dynamic_agent_host_rollout(
        list(reversed(fleet)),
        release_digest=target_release.manifest.digest,
        minimum_nodes=21,
    ) == waves


def test_dynamic_rollout_fails_closed_on_missing_role_capability_or_minimum():
    target_release = verified()
    fleet = [node("authority", role="control_plane")]
    fleet.extend(node(f"worker-{index:02d}") for index in range(20))
    with pytest.raises(release.ReleaseError, match="minimum"):
        rollout.plan_dynamic_agent_host_rollout(
            fleet[:-1], release_digest=target_release.manifest.digest, minimum_nodes=21
        )
    with pytest.raises(release.ReleaseError, match="exactly one"):
        rollout.plan_dynamic_agent_host_rollout(
            [release.FleetNode(**{**item.__dict__, "role": "worker"}) for item in fleet],
            release_digest=target_release.manifest.digest,
            minimum_nodes=21,
        )
    incapable = release.FleetNode(**{**fleet[4].__dict__, "capabilities": (release.RELEASE_CAPABILITY,)})
    blocked = [incapable if item == fleet[4] else item for item in fleet]
    with pytest.raises(release.ReleaseError, match="incapable"):
        rollout.plan_dynamic_agent_host_rollout(
            blocked, release_digest=target_release.manifest.digest, minimum_nodes=21
        )


def test_discovery_joins_dynamic_membership_to_semantic_roles():
    active = [node("dynamic-a"), node("dynamic-b")]

    class Client:
        def fleet(self):
            return active

        def request(self, method, path, payload=None):
            assert (method, path, payload) == ("GET", "/v1/fleet/nodes", None)
            return {
                "data": {
                    "nodes": [
                        {"node_id": "dynamic-a", "role": "worker"},
                        {"node_id": "dynamic-b", "role": "control_plane"},
                    ]
                }
            }

    discovered = rollout.discover_agent_host_fleet(Client())
    assert [(item.node_id, item.role) for item in discovered] == [
        ("dynamic-a", "worker"),
        ("dynamic-b", "control_plane"),
    ]


def test_pre_switch_raw_proof_and_strict_proof_are_separate_campaigns():
    target_release = verified()
    target = node("worker-x")
    task = raw_handshake(target, target_release)

    pre = rollout.validate_handshake(
        task, target, target_release, phase=rollout.PRE_SWITCH_PHASE
    )
    assert pre["control_plane_verifier"] == "not_required_pre_switch"
    with pytest.raises(release.ReleaseError, match="proof is absent"):
        rollout.validate_handshake(
            task, target, target_release, phase=rollout.STRICT_PHASE
        )

    strict = rollout.validate_handshake(
        add_strict_proof(task), target, target_release, phase=rollout.STRICT_PHASE
    )
    assert strict["control_plane_verifier"]["verdict"] == "passed"
    task["completion_evidence"]["binding_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(release.ReleaseError, match="binding_hash"):
        rollout.validate_handshake(
            task, target, target_release, phase=rollout.STRICT_PHASE
        )


def test_handshake_submission_is_targeted_read_only_and_phase_idempotent():
    target_release = verified()
    target = node("worker-y")

    class Client:
        def __init__(self):
            self.payloads = []

        def request(self, method, path, payload=None):
            assert (method, path) == ("POST", "/v1/tasks")
            self.payloads.append(payload)
            return {"task_id": f"probe-{len(self.payloads)}"}

    client = Client()
    rollout.submit_handshake_task(
        client,
        target_release,
        target,
        phase=rollout.PRE_SWITCH_PHASE,
        campaign_id="campaign-a",
    )
    rollout.submit_handshake_task(
        client,
        target_release,
        target,
        phase=rollout.STRICT_PHASE,
        campaign_id="campaign-b",
    )

    first, second = client.payloads
    assert first["target_node"] == target.node_id
    assert first["kind"] == "read_only_probe"
    assert first["permission_pack"] == "read_only"
    assert first["write_scope"] == [] and first["no_push"] is True
    assert first["idempotency_key"] != second["idempotency_key"]
    assert first["expected_agent_host_runtime"]["manifest_digest"] == target_release.manifest.digest
    assert first["expected_agent_host_runtime"]["response_profile_path"] == (
        "ops/mimo/kolibri-response-only.md"
    )
    assert first["expected_agent_host_runtime"]["response_profile_sha256"] == "d" * 64


def test_agent_host_campaign_rejects_signed_runtime_without_response_profile():
    incomplete = release.VerifiedRelease(
        release.ReleaseManifest(
            release_id="agent-host-incomplete",
            source_commit="0123456789abcdef",
            artifact_uri="artifact://releases/agent-host-incomplete.tar.gz",
            files=(
                release.ReleaseFile("ops/agent_host.py", "a" * 64, 4096, "0755"),
            ),
            metadata={"component": "agent-host"},
        ),
        "owner",
    )
    with pytest.raises(release.ReleaseError, match="kolibri-response-only"):
        rollout._response_profile_record(incomplete)


class FakeRolloutClient:
    def __init__(self, target_release, rollback_release, fail_probe_node=None):
        self.target_release = target_release
        self.rollback_release = rollback_release
        self.fail_probe_node = fail_probe_node
        self.tasks = {}
        self.rolled_back = []
        self.cancelled = []

    def require_owner_approval(self, *args, **kwargs):
        return {"status": "approved", "allow_rollback": True}

    def _release_task(self, task_id, target, selected_release):
        runtime_path, runtime_sha256 = rollout._runtime_record(selected_release)
        profile_path, profile_sha256 = rollout._response_profile_record(selected_release)
        return {
            "task_id": task_id,
            "state": "completed",
            "result": {
                "status": "completed",
                "agent_host_runtime": {
                    "included": True,
                    "runtime_path": runtime_path,
                    "runtime_sha256": runtime_sha256,
                    "response_profile_included": True,
                    "response_profile_path": profile_path,
                    "response_profile_sha256": profile_sha256,
                    "release_id": selected_release.manifest.release_id,
                    "manifest_digest": selected_release.manifest.digest,
                },
            },
        }

    def submit_release_task(self, target_release, target, wave, approval_id, plan):
        task_id = f"release:{target.node_id}"
        self.tasks[task_id] = self._release_task(task_id, target, target_release)
        return {"task_id": task_id}

    def submit_rollback_task(
        self, failed_release, rollback_release, target, approval_id, reason, plan
    ):
        self.rolled_back.append(target.node_id)
        task_id = f"rollback:{target.node_id}"
        self.tasks[task_id] = self._release_task(task_id, target, rollback_release)
        return {"task_id": task_id}

    def request(self, method, path, payload=None):
        assert (method, path) == ("POST", "/v1/tasks")
        target = node(payload["target_node"])
        selected = (
            self.target_release
            if payload["expected_agent_host_runtime"]["release_id"]
            == self.target_release.manifest.release_id
            else self.rollback_release
        )
        task_id = f"probe:{payload['proof_phase']}:{selected.manifest.release_id}:{target.node_id}"
        task = raw_handshake(target, selected, task_id=task_id)
        if payload["proof_phase"] == rollout.STRICT_PHASE:
            add_strict_proof(task)
        if (
            target.node_id == self.fail_probe_node
            and selected.manifest.release_id == self.target_release.manifest.release_id
        ):
            task["result"]["agent_host_runtime"]["manifest_digest"] = "sha256:" + "0" * 64
        self.tasks[task_id] = task
        return {"task_id": task_id}

    def wait_for_task(self, task_id, **kwargs):
        return self.tasks[task_id]

    def require_release_health(self, selected_release, target):
        return {
            "status": "healthy",
            "manifest_digest": selected_release.manifest.digest,
        }

    def cancel_and_fence_release_tasks(self, task_ids, reason):
        self.cancelled.extend(task_ids)
        return list(task_ids)


def test_failed_pre_switch_wave_rolls_back_every_attempted_node_in_reverse():
    target_release = verified()
    known_good = verified("agent-host-v1", "b")
    first, second = node("worker-a"), node("worker-b")
    client = FakeRolloutClient(target_release, known_good, fail_probe_node="worker-b")

    result = rollout.execute_pre_switch_rollout(
        client,
        target_release,
        known_good,
        [release.RolloutWave("agent-host-canary", (first, second))],
        "approval-1",
        campaign_id="campaign-pre",
        enforce_membership_snapshot=False,
    )

    assert result["status"] == "rolled_back"
    assert result["strict_completion_proven"] is False
    assert client.rolled_back == ["worker-b", "worker-a"]
    assert [item["status"] for item in result["rollback"]["nodes"]] == [
        "completed",
        "completed",
    ]


def test_strict_campaign_reproves_every_planned_node_with_home_verifier():
    target_release = verified()
    known_good = verified("agent-host-v1", "b")
    first, second, authority = (
        node("worker-a"),
        node("worker-b"),
        node("authority", role="control_plane"),
    )
    waves = [
        release.RolloutWave("workers", (first, second)),
        release.RolloutWave("control-plane-last", (authority,)),
    ]
    client = FakeRolloutClient(target_release, known_good)

    result = rollout.execute_strict_handshake_campaign(
        client,
        target_release,
        waves,
        campaign_id="campaign-strict",
        enforce_membership_snapshot=False,
    )

    assert result["status"] == "completed"
    assert result["strict_completion_proven"] is True
    assert result["summary"] == {
        "canonical_total": 3,
        "raw_verified_total": 3,
        "strict_verified_total": 3,
    }
    assert [item["wave"] for item in result["waves"]] == [
        "workers",
        "control-plane-last",
    ]
    assert all(
        proof["control_plane_verifier"]["verdict"] == "passed"
        for wave in result["waves"]
        for proof in wave["proofs"]
    )


def test_release_bound_runtime_identity_matches_canonical_manifest(tmp_path, monkeypatch):
    release_root = tmp_path / "releases"
    selected = release_root / "agent-host-v2"
    runtime = selected / "ops" / "agent_host.py"
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b"#!/usr/bin/python3\nprint('runtime')\n")
    runtime.chmod(0o755)
    response_profile = selected / "ops" / "mimo" / "kolibri-response-only.md"
    response_profile.parent.mkdir(parents=True)
    response_profile.write_bytes(
        (Path(agent_host_module.__file__).parent / "mimo" / "kolibri-response-only.md").read_bytes()
    )
    response_profile.chmod(0o644)
    manifest_payload = {
        "schema_version": release.RELEASE_SCHEMA,
        "release_id": "agent-host-v2",
        "source_commit": "0123456789abcdef",
        "artifact_uri": "artifact://releases/agent-host-v2.tar.gz",
        "compatibility_epoch": "kolibri-os-v1",
        "files": [
            {
                "path": "ops/agent_host.py",
                "sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
                "size_bytes": runtime.stat().st_size,
                "mode": "0755",
            },
            {
                "path": "ops/mimo/kolibri-response-only.md",
                "sha256": hashlib.sha256(response_profile.read_bytes()).hexdigest(),
                "size_bytes": response_profile.stat().st_size,
                "mode": "0644",
            },
        ],
        "metadata": {"component": "agent-host"},
    }
    manifest_bytes = json.dumps(
        manifest_payload, sort_keys=True, separators=(",", ":")
    ).encode()
    metadata = selected / ".kolibri-release"
    metadata.mkdir()
    (metadata / "manifest.json").write_bytes(manifest_bytes)
    current = tmp_path / "current"
    current.symlink_to(selected)
    monkeypatch.setenv("KOLIBRI_RELEASE_ROOT", str(release_root))
    monkeypatch.setenv("KOLIBRI_RELEASE_CURRENT_LINK", str(current))

    identity = agent_host_module.agent_host_runtime_identity(runtime)

    assert identity["status"] == "release_bound"
    assert identity["release_id"] == "agent-host-v2"
    assert identity["manifest_digest"] == f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}"
    assert identity["response_profile_path"] == "ops/mimo/kolibri-response-only.md"
    assert identity["response_profile_sha256"] == hashlib.sha256(response_profile.read_bytes()).hexdigest()

    class ReexecObserved(Exception):
        pass

    observed = {}

    def fake_execve(executable, argv, environment):
        observed.update({
            "executable": executable,
            "argv": argv,
            "environment": environment,
        })
        raise ReexecObserved

    monkeypatch.setattr(agent_host_module.os, "execve", fake_execve)
    with pytest.raises(ReexecObserved):
        agent_host_module.maybe_reexec_release_agent_host()
    assert observed["executable"] == agent_host_module.sys.executable
    assert observed["argv"][:2] == [
        agent_host_module.sys.executable,
        str(runtime),
    ]
    assert observed["environment"]["PYTHONPATH"].split(agent_host_module.os.pathsep)[0] == str(selected)

    runtime.write_bytes(b"corrupted")
    with pytest.raises(RuntimeError, match="digest_mismatch"):
        agent_host_module.agent_host_runtime_identity(runtime)
    runtime.write_bytes(b"#!/usr/bin/python3\nprint('runtime')\n")
    response_profile.write_bytes(b"corrupted profile")
    with pytest.raises(RuntimeError, match="profile_digest_mismatch"):
        agent_host_module.agent_host_runtime_identity(runtime)
    manifest_payload["files"][1]["sha256"] = hashlib.sha256(
        response_profile.read_bytes()
    ).hexdigest()
    manifest_payload["files"][1]["size_bytes"] = response_profile.stat().st_size
    (metadata / "manifest.json").write_bytes(
        json.dumps(manifest_payload, sort_keys=True, separators=(",", ":")).encode()
    )
    with pytest.raises(RuntimeError, match="profile_contract_invalid"):
        agent_host_module.agent_host_runtime_identity(runtime)


def test_agent_host_exits_only_after_completed_release_bound_runtime_task(
    tmp_path, canonical_home_control_plane
):
    args = argparse.Namespace(
        control_url=canonical_home_control_plane,
        control_urls=None,
        mesh_membership_manifest=None,
        node_id="worker-reexec",
        agent_id="agent-worker-reexec",
        capabilities="read_only_probe",
        repo_url="https://example.invalid/repo.git",
        work_root=str(tmp_path / "work"),
        artifact_root=str(tmp_path / "artifacts"),
        heartbeat_interval=10,
        lease_refresh=20,
        max_inflight=1,
        labels_json="{}",
        codex_readiness_refresh_seconds=0,
        external_provider_credential_file="",
    )

    class Host(agent_host_module.AgentHost):
        def __init__(self):
            super().__init__(args)
            self.capabilities.append(release.RELEASE_CAPABILITY)
            self.completed = []

        def run_release_bundle_task(self, task):
            artifact_dir = Path(args.artifact_root) / task["task_id"] / task["attempt_id"]
            artifact_dir.mkdir(parents=True, exist_ok=True)
            return {
                "task_id": task["task_id"],
                "attempt_id": task["attempt_id"],
                "node_id": self.node_id,
                "agent_id": self.agent_id,
                "status": "completed",
                "changed_files": [],
                "worktree": str(Path(args.work_root) / task["task_id"]),
                "result_path": str(artifact_dir / "result.json"),
                "agent_host_runtime": {
                    "included": True,
                    "runtime_path": "ops/agent_host.py",
                    "runtime_sha256": "a" * 64,
                    "response_profile_included": True,
                    "response_profile_path": "ops/mimo/kolibri-response-only.md",
                    "response_profile_sha256": "d" * 64,
                    "release_id": "agent-host-v2",
                    "manifest_digest": "sha256:" + "b" * 64,
                },
            }

        def complete(self, task, result, result_path):
            self.completed.append((task, result, result_path))

    host = Host()
    task = {
        "task_id": "release-worker-reexec",
        "attempt": 1,
        "attempt_id": "release-worker-reexec-attempt-1",
        "kind": "release_bundle_apply",
        "max_retries": 1,
        "envelope": {
            "kind": "release_bundle_apply",
            "required_capability": release.RELEASE_CAPABILITY,
        },
    }

    host.run_task(task)

    assert len(host.completed) == 1
    assert host._runtime_restart_requested is True
