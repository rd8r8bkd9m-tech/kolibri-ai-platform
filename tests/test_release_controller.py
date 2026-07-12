import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_release_controller():
    path = ROOT / "ops" / "release_controller.py"
    spec = importlib.util.spec_from_file_location("release_controller_contract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def manifest(release):
    return release.ReleaseManifest(
        release_id="kolibri-2026.07.10",
        source_commit="0123456789abcdef",
        artifact_uri="artifact://releases/kolibri-2026.07.10.tar.zst",
        files=(
            release.ReleaseFile("bin/kolibri-agent", "a" * 64, 1024, "0755"),
            release.ReleaseFile("etc/kolibri/manifest.json", "b" * 64, 256),
        ),
        metadata={"contract": "kolibri-os-v1"},
    )


def node(release, name, stage="standard", physical=None, fresh=True):
    return release.FleetNode(
        node_id=name,
        physical_node_id=physical or name,
        freshness="fresh" if fresh else "stale",
        health="online" if fresh else "stale",
        draining=False,
        capabilities=(release.RELEASE_CAPABILITY,),
        agent_live=fresh,
        rollout_stage=stage,
    )


def rollout_plan(waves):
    return [{"name": wave.name, "nodes": [item.node_id for item in wave.nodes]} for wave in waves]


def approval_record(release, verified, rollback, plan):
    from ops.release_authority import (
        OWNER_APPROVAL_ATTESTATION_SCHEMA,
        approval_attestation_digest,
        canonical_owner_approval_payload,
    )

    payload = canonical_owner_approval_payload(
        {
            "approval_id": "approval-1",
            "release_id": verified.manifest.release_id,
            "manifest_digest": verified.manifest.digest,
            "release_signature_namespace": verified.namespace,
            "release_signer_identity": verified.signer_identity,
            "decision": "approved",
            "allow_rollback": True,
            "rollback": {
                "release_id": rollback.manifest.release_id,
                "manifest_digest": rollback.manifest.digest,
                "signature_namespace": rollback.namespace,
                "signer_identity": rollback.signer_identity,
            },
            "rollout_plan": plan,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            "nonce": "approval-nonce-1",
            "signer_identity": "owner",
        }
    )
    attestation = {
        "schema_version": OWNER_APPROVAL_ATTESTATION_SCHEMA,
        "payload": payload,
        "signature": "-----BEGIN SSH SIGNATURE-----\ntest\n-----END SSH SIGNATURE-----\n",
    }
    return {
        **payload,
        "status": "approved",
        "approved_by": {"role": "owner", "identity": "owner"},
        "attestation": attestation,
        "attestation_digest": approval_attestation_digest(attestation),
    }


def test_release_manifest_is_canonical_and_rejects_unsafe_paths():
    release = load_release_controller()
    value = manifest(release)
    value.validate()
    assert value.digest.startswith("sha256:")
    assert value.digest == release.ReleaseManifest.from_payload(value.payload()).digest

    unsafe = release.ReleaseManifest(
        release_id=value.release_id,
        source_commit=value.source_commit,
        artifact_uri=value.artifact_uri,
        files=(release.ReleaseFile("../escape", "a" * 64, 1),),
    )
    with pytest.raises(release.ReleaseError, match="unsafe release path"):
        unsafe.validate()


def test_signature_verification_uses_sshsig_namespace_without_private_key(tmp_path, monkeypatch):
    release = load_release_controller()
    signature = tmp_path / "release.sig"
    allowed = tmp_path / "allowed_signers"
    signature.write_text("signature", encoding="utf-8")
    allowed.write_text("owner ssh-ed25519 public-material", encoding="utf-8")
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(release.subprocess, "run", fake_run)
    verified = release.verify_ssh_signature(manifest(release), signature, allowed, "owner")

    command, kwargs = calls[0]
    assert command[:3] == ["ssh-keygen", "-Y", "verify"]
    assert command[command.index("-n") + 1] == "kolibri-release"
    assert kwargs["input"] == manifest(release).canonical_bytes()
    assert "-I" in command and command[command.index("-I") + 1] == "owner"
    assert verified.signer_identity == "owner"
    assert command[command.index("-Y") + 1] == "verify"
    assert "sign" not in command


def test_dynamic_21_node_rollout_assigns_each_physical_node_once():
    release = load_release_controller()
    fleet = [node(release, "node-canary", "canary")]
    fleet.extend(node(release, f"node-quorum-{index}", "quorum") for index in range(2))
    fleet.extend(node(release, f"worker-{index:02d}", "standard") for index in range(17))
    fleet.append(node(release, "control-primary", "last"))
    waves = release.plan_progressive_rollout(fleet, expected_nodes=21)

    assert [wave.name for wave in waves] == [
        "canary",
        "quorum",
        "workers-3",
        "workers-5",
        "workers-rest",
        "home-control-plane-last",
    ]
    assert [len(wave.nodes) for wave in waves] == [1, 2, 3, 5, 9, 1]
    assert [item.node_id for item in waves[-1].nodes] == ["control-primary"]
    planned = [item.physical_node_id for wave in waves for item in wave.nodes]
    assert len(planned) == len(set(planned)) == 21


def test_home_only_canary_checks_full_membership_but_targets_only_fresh_home():
    release = load_release_controller()
    fleet = [node(release, "home", "last")]
    for index in range(20):
        stale = node(release, f"worker-{index:02d}", "standard", fresh=False)
        stale = release.FleetNode(**{**stale.__dict__, "capabilities": ()})
        fleet.append(stale)

    waves = release.plan_home_canary(fleet, expected_nodes=21)

    assert [(wave.name, [item.node_id for item in wave.nodes]) for wave in waves] == [
        ("home-canary", ["home"]),
    ]
    with pytest.raises(release.ReleaseError, match="fleet size"):
        release.plan_home_canary(fleet, expected_nodes=20)
    with pytest.raises(release.ReleaseError, match="non-fresh Home"):
        release.plan_home_canary(
            [release.FleetNode(**{**fleet[0].__dict__, "freshness": "stale"})],
        )


def test_home_only_canary_requires_one_unambiguous_canonical_home():
    release = load_release_controller()
    with pytest.raises(release.ReleaseError, match="exactly one"):
        release.plan_home_canary([node(release, "worker-01")])
    with pytest.raises(release.ReleaseError, match="exactly one"):
        release.plan_home_canary([
            node(release, "home", "last"),
            node(release, "home-shadow", "standard", physical="home"),
        ])


def test_duplicate_cards_collapse_to_fresh_agent_and_stale_fleet_blocks_rollout():
    release = load_release_controller()
    values = [
        {
            "node_id": "mesh-worker-01",
            "physical_node_id": "worker-01",
            "freshness": "stale",
            "health": "stale",
            "capabilities": ["mesh"],
        },
        {
            "node_id": "worker-01",
            "physical_node_id": "worker-01",
            "freshness": "fresh",
            "health": "online",
            "agent_id": "agent-worker-01",
            "pid": 42,
            "capabilities": [release.RELEASE_CAPABILITY],
        },
    ]
    fleet = release.canonical_fleet(values)
    assert [item.node_id for item in fleet] == ["worker-01"]

    with pytest.raises(release.ReleaseError, match="non-fresh nodes"):
        release.plan_progressive_rollout([node(release, "worker-01", fresh=False)])


def test_release_submission_is_api_only_idempotent_and_approval_gated():
    release = load_release_controller()
    verified = release.VerifiedRelease(manifest(release), "owner")
    rollback = release.VerifiedRelease(
        release.ReleaseManifest(
            release_id="kolibri-2026.07.09",
            source_commit="abcdef0123456789",
            artifact_uri="artifact://releases/kolibri-2026.07.09.tar.zst",
            files=manifest(release).files,
        ),
        "owner",
    )
    plan = [{"name": "canary", "nodes": ["agent-09"]}]
    approved = approval_record(release, verified, rollback, plan)

    class RecordingClient(release.ControlPlaneClient):
        def __init__(self):
            super().__init__("http://control.invalid")
            self.calls = []

        def request(self, method, path, payload=None):
            self.calls.append((method, path, payload))
            if method == "GET" and path.startswith("/v1/approvals/"):
                return approved
            return {"task_id": "release-task-1", "state": "queued"}

    client = RecordingClient()
    target = node(release, "agent-09", "canary")
    with pytest.raises(release.ReleaseError, match="approval"):
        client.submit_release_task(verified, target, "canary", "", plan)

    result = client.submit_release_task(verified, target, "canary", "approval-1", plan)
    assert result["state"] == "queued"
    assert client.calls[0][:2] == ("GET", "/v1/approvals/approval-1")
    method, path, payload = client.calls[1]
    assert (method, path) == ("POST", "/v1/tasks")
    assert payload["kind"] == release.RELEASE_TASK_KIND
    assert payload["required_capability"] == release.RELEASE_CAPABILITY
    assert payload["idempotency_key"].endswith(":agent-09")
    assert ":approval-1:" in payload["idempotency_key"]
    assert payload["approval_id"] == "approval-1"
    assert payload["max_attempts"] == 2
    assert "max_retries" not in payload
    serialized = str(payload).lower()
    assert "password" not in serialized and "private_key" not in serialized


def test_rollback_submission_preserves_the_owner_approved_rollout_wave():
    release = load_release_controller()
    verified = release.VerifiedRelease(manifest(release), "owner")
    rollback = release.VerifiedRelease(
        release.ReleaseManifest(
            release_id="kolibri-2026.07.09",
            source_commit="abcdef0123456789",
            artifact_uri="artifact://releases/kolibri-2026.07.09.tar.zst",
            files=manifest(release).files,
        ),
        "owner",
    )
    plan = [{"name": "home-canary", "nodes": ["home"]}]
    approved = approval_record(release, verified, rollback, plan)

    class RecordingClient(release.ControlPlaneClient):
        def __init__(self):
            super().__init__("http://control.invalid")
            self.payload = None

        def request(self, method, path, payload=None):
            if method == "GET" and path.startswith("/v1/approvals/"):
                return approved
            if method == "POST" and path == "/v1/tasks":
                self.payload = payload
                return {"task_id": "rollback-task-1", "state": "queued"}
            raise AssertionError((method, path))

    client = RecordingClient()
    result = client.submit_rollback_task(
        verified,
        rollback,
        node(release, "home", "last"),
        "approval-1",
        "canary failed",
        plan,
    )

    assert result["task_id"] == "rollback-task-1"
    assert client.payload["kind"] == release.ROLLBACK_TASK_KIND
    assert client.payload["rollout_wave"] == "home-canary"


def test_owner_approval_must_match_release_role_and_decision():
    release = load_release_controller()

    class DeniedClient(release.ControlPlaneClient):
        def request(self, method, path, payload=None):
            return {"status": "approved", "release_id": "other", "approved_by": {"role": "operator"}}

    with pytest.raises(release.ReleaseError, match="approved owner"):
        DeniedClient("http://control.invalid").require_owner_approval("approval-1", "kolibri-2026.07.10")


def test_release_client_uses_only_canonical_home_control_plane(monkeypatch, tmp_path):
    release = load_release_controller()
    membership = tmp_path / "peers.json"
    membership.write_text(
        json.dumps({"peers": {"home": {"node_id": "home", "mesh_ip": "10.99.0.1"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("KOLIBRI_MESH_MEMBERSHIP_MANIFEST", str(membership))
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    assert release.ControlPlaneClient.from_environment().base_url == "http://10.99.0.1:9101"
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", "http://10.99.0.1:9101")
    assert release.ControlPlaneClient.from_environment().base_url == "http://10.99.0.1:9101"
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", "http://user:pass@legacy.invalid:9101")
    with pytest.raises(release.ReleaseError, match="canonical Home"):
        release.ControlPlaneClient.from_environment()


def test_release_client_rejects_multiple_or_non_home_authorities(monkeypatch, tmp_path):
    release = load_release_controller()
    membership = tmp_path / "peers.json"
    membership.write_text(
        json.dumps({"peers": {"home": {"node_id": "home", "mesh_ip": "10.99.0.1"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("KOLIBRI_MESH_MEMBERSHIP_MANIFEST", str(membership))
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URL", raising=False)
    monkeypatch.setenv(
        "KOLIBRI_FACTORY_CONTROL_URLS",
        "http://home.internal:9101,http://standby.internal:9101",
    )
    with pytest.raises(release.ReleaseError, match="multiple_control_plane_authorities_forbidden"):
        release.ControlPlaneClient.from_environment()
    monkeypatch.delenv("KOLIBRI_FACTORY_CONTROL_URLS", raising=False)
    monkeypatch.setenv("KOLIBRI_FACTORY_CONTROL_URL", "http://main:9101")
    with pytest.raises(release.ReleaseError, match="control_plane_authority_not_home"):
        release.ControlPlaneClient.from_environment()


def test_manifest_rejects_secret_metadata_and_credential_uri():
    release = load_release_controller()
    base = manifest(release)
    for artifact_uri, metadata in [
        ("https://user:pass@example.invalid/release", {}),
        ("s3://release-bucket/kolibri.tar.zst", {}),
        (base.artifact_uri, {"nested": {"api-key": "must-not-ship"}}),
    ]:
        invalid = release.ReleaseManifest(
            release_id=base.release_id, source_commit=base.source_commit,
            artifact_uri=artifact_uri, files=base.files, metadata=metadata,
        )
        with pytest.raises(release.ReleaseError):
            invalid.validate()


def test_rollout_requires_live_capable_nodes_and_all_safety_stages():
    release = load_release_controller()
    incapable = node(release, "agent-09")
    incapable = release.FleetNode(**{**incapable.__dict__, "capabilities": ()})
    with pytest.raises(release.ReleaseError, match="non-fresh"):
        release.plan_progressive_rollout([incapable])
    with pytest.raises(release.ReleaseError, match="no quorum"):
        release.plan_progressive_rollout([
            node(release, "agent-09", "canary"), node(release, "home", "last"),
        ])


def test_release_controller_validate_cli_is_offline_and_machine_readable(tmp_path, capsys):
    release = load_release_controller()
    manifest_path = tmp_path / "release.json"
    manifest_path.write_text(json.dumps(manifest(release).payload()), encoding="utf-8")

    assert release.main(["validate", "--manifest", str(manifest_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "valid"
    assert payload["release_id"] == "kolibri-2026.07.10"
    assert payload["manifest_digest"].startswith("sha256:")


def test_wait_for_task_tolerates_bounded_control_plane_self_restart(monkeypatch):
    release = load_release_controller()
    client = release.ControlPlaneClient("http://control.invalid")
    responses = iter((
        release.ReleaseError("listener restarting"),
        {"state": "running"},
        {"state": "completed", "task_id": "release-home"},
    ))

    def request(*_args, **_kwargs):
        value = next(responses)
        if isinstance(value, Exception):
            raise value
        return value

    clock = {"value": 0.0}
    monkeypatch.setattr(client, "request", request)
    monkeypatch.setattr(release.time, "monotonic", lambda: clock["value"])
    monkeypatch.setattr(
        release.time,
        "sleep",
        lambda seconds: clock.__setitem__("value", clock["value"] + seconds),
    )

    result = client.wait_for_task("release-home", timeout=10, poll_interval=1)
    assert result["state"] == "completed"


def test_failed_wave_rolls_back_attempted_nodes_in_reverse_order():
    release = load_release_controller()
    current = release.VerifiedRelease(manifest(release), "owner")
    old_manifest = release.ReleaseManifest(
        release_id="kolibri-2026.07.09", source_commit="abcdef0123456789",
        artifact_uri="artifact://releases/kolibri-2026.07.09.tar.zst",
        files=manifest(release).files,
    )
    rollback = release.VerifiedRelease(old_manifest, "owner")

    class FakeClient(release.ControlPlaneClient):
        def __init__(self):
            super().__init__("http://control.invalid")
            self.rolled_back = []
            self.cancelled = []

        def require_owner_approval(self, *args, **kwargs):
            return {"status": "approved", "allow_rollback": True}

        def submit_release_task(self, verified, target, wave, approval_id, rollout_plan):
            return {"task_id": f"release-{target.node_id}"}

        def wait_for_task(self, task_id, **kwargs):
            if task_id == "release-quorum":
                return {
                    "state": "failed",
                    "result": {
                        "rollback": {
                            "status": "not_required",
                            "reason": "activation_not_started",
                        },
                    },
                }
            return {"state": "completed"}

        def require_release_health(self, verified, target):
            return {"status": "healthy", "manifest_digest": verified.manifest.digest}

        def cancel_and_fence_release_tasks(self, task_ids, reason):
            self.cancelled.extend(task_ids)
            return list(task_ids)

        def submit_rollback_task(
            self, failed, target, node_value, approval_id, reason, rollout_plan
        ):
            self.rolled_back.append(node_value.node_id)
            return {"task_id": f"rollback-{node_value.node_id}"}

    client = FakeClient()
    waves = [
        release.RolloutWave("canary", (node(release, "canary", "canary"),)),
        release.RolloutWave("quorum", (node(release, "quorum", "quorum"),)),
    ]
    result = release.execute_progressive_release(client, current, rollback, waves, "approval-1")
    assert result["status"] == "rolled_back"
    assert client.rolled_back == ["canary"]
    assert client.cancelled == ["release-canary", "release-quorum"]
    assert result["rollback"]["skipped"] == [
        {"node": "quorum", "reason": "activation_not_started"},
    ]


def test_candidate_failure_before_atomic_switch_never_submits_rollback_task():
    release = load_release_controller()
    current = release.VerifiedRelease(manifest(release), "owner")
    rollback = release.VerifiedRelease(
        release.ReleaseManifest(
            release_id="kolibri-2026.07.09",
            source_commit="abcdef0123456789",
            artifact_uri="artifact://releases/kolibri-2026.07.09.tar.zst",
            files=manifest(release).files,
        ),
        "owner",
    )

    class FakeClient(release.ControlPlaneClient):
        def __init__(self):
            super().__init__("http://control.invalid")
            self.rollback_calls = 0

        def require_owner_approval(self, *args, **kwargs):
            return {"status": "approved", "allow_rollback": True}

        def submit_release_task(self, *args, **kwargs):
            return {"task_id": "candidate-task"}

        def wait_for_task(self, task_id, **kwargs):
            assert task_id == "candidate-task"
            return {
                "state": "failed",
                "result": {
                    "error_type": "release_candidate_health_failed",
                    "rollback": {
                        "status": "not_required",
                        "reason": "activation_not_started",
                    },
                },
            }

        def cancel_and_fence_release_tasks(self, task_ids, reason):
            return list(task_ids)

        def submit_rollback_task(self, *args, **kwargs):
            self.rollback_calls += 1
            raise AssertionError("pre-activation failure must not create rollback task")

    client = FakeClient()
    waves = [release.RolloutWave("canary", (node(release, "canary", "canary"),))]
    result = release.execute_progressive_release(
        client,
        current,
        rollback,
        waves,
        "approval-1",
    )

    assert result["status"] == "failed_before_activation"
    assert result["rollback"]["status"] == "not_required"
    assert result["rollback"]["nodes"] == []
    assert client.rollback_calls == 0


def test_missing_activation_evidence_is_never_guessed():
    release = load_release_controller()
    assert release.release_task_activation_outcome({"state": "failed"}) == "unknown"
    assert release.release_task_activation_outcome({
        "state": "failed",
        "result": {
            "rollback": {"status": "completed", "atomic_switch": "completed"},
        },
    }) == "already_restored"
