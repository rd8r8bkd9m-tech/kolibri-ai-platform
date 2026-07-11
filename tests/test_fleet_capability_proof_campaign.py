from __future__ import annotations

import copy
import http.client
import importlib.util
import json
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_manifest(path: Path, count: int = 21) -> list[str]:
    node_ids = ["home", "agent09", *[f"worker-{index:02d}" for index in range(1, count - 1)]]
    peers = {
        f"10.99.0.{index}": {"node_id": node_id, "mesh_ip": f"10.99.0.{index}"}
        for index, node_id in enumerate(node_ids, start=1)
    }
    path.write_text(json.dumps({
        "schema_version": 3,
        "cluster_id": "kolibri-test",
        "epoch": 7,
        "peers": peers,
    }), encoding="utf-8")
    return node_ids


class MemoryRedis:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.lists: dict[str, list[str]] = {}
        self.lock = threading.Lock()

    def command(self, name, *args):
        name = name.upper()
        if name == "GET":
            return self.values.get(args[0])
        if name == "SET":
            self.values[args[0]] = args[1]
            return "OK"
        if name == "MGET":
            return [self.values.get(key) for key in args]
        if name == "SADD":
            target = self.sets.setdefault(args[0], set())
            before = len(target)
            target.update(str(value) for value in args[1:])
            return len(target) - before
        if name == "SREM":
            target = self.sets.setdefault(args[0], set())
            for value in args[1:]:
                target.discard(str(value))
            return 1
        if name == "SMEMBERS":
            return sorted(self.sets.get(args[0], set()))
        if name == "RPUSH":
            target = self.lists.setdefault(args[0], [])
            target.extend(str(value) for value in args[1:])
            return len(target)
        if name == "LRANGE":
            return list(self.lists.get(args[0], []))
        if name == "LREM":
            values = self.lists.setdefault(args[0], [])
            self.lists[args[0]] = [value for value in values if value != args[2]]
            return 1
        if name == "EVAL":
            _script, key_count, *values = args
            keys = values[:key_count]
            argv = values[key_count:]
            with self.lock:
                existing = self.values.get(keys[0])
                if existing is not None:
                    return [0, existing]
                self.values[keys[0]] = argv[0]
                self.values[keys[1]] = argv[1]
                self.sets.setdefault(keys[2], set()).add(argv[2])
                self.lists.setdefault(keys[3], []).append(argv[2])
                if argv[3] == "1":
                    self.sets.setdefault(keys[4], set()).add(argv[2])
                return [1, argv[1]]
        raise AssertionError((name, args))


def fresh_runtime_nodes(node_ids: list[str], at: str) -> list[dict]:
    return [{
        "node_id": node_id,
        "hostname": node_id,
        "health": "online",
        "heartbeat_at": at,
        "capabilities": ["generic_implementation", "read_only_probe"],
        "draining": False,
    } for node_id in node_ids]


def leased_task(control, node_id: str = "agent09") -> tuple[dict, dict, dict]:
    task = control.normalize_task({
        "task_id": "KOL-PROOF-1",
        "idempotency_key": "proof-1",
        "kind": "read_only_probe",
        "target_node": node_id,
        "required_capability": "read_only_probe",
    })
    task.update({
        "state": control.STATE_LEASED,
        "attempt": 1,
        "attempt_id": "KOL-PROOF-1-attempt-1",
        "lease_owner": f"{node_id}:agent-host-{node_id}",
    })
    result_reference = f"/var/lib/kolibri-agent/{task['task_id']}/result.json"
    result = {
        "status": "completed",
        "kind": "read_only_probe",
        "task_id": task["task_id"],
        "attempt_id": task["attempt_id"],
        "node_id": node_id,
        "agent_id": f"agent-host-{node_id}",
        "result_path": result_reference,
        "message": "read-only probe completed",
    }
    body = {
        "attempt_id": task["attempt_id"],
        "node_id": node_id,
        "agent_id": f"agent-host-{node_id}",
        "result_reference": result_reference,
        "result": result,
    }
    return task, result, body


def test_create_task_rejects_alias_and_http_maps_typed_error_to_422(tmp_path, monkeypatch):
    control = load_module(
        "factory_control_fleet_proof_target",
        ROOT / "ops" / "factory_control.py",
    )
    manifest = tmp_path / "peers.json"
    write_manifest(manifest)
    control.configure_mesh_membership(manifest)
    memory = MemoryRedis()
    monkeypatch.setattr(control, "redis", memory)

    created = control.create_task({
        "task_id": "valid-target",
        "idempotency_key": "valid-target",
        "kind": "read_only_probe",
        "target_node": "agent09",
    })
    assert created["envelope"]["target_node"] == "agent09"
    with pytest.raises(control.TaskTargetValidationError) as rejected:
        control.create_task({
            "task_id": "invalid-alias",
            "idempotency_key": "invalid-alias",
            "kind": "read_only_probe",
            "target_node": "agent-09",
        })
    assert rejected.value.as_dict() == {
        "error": "task_target_not_canonical",
        "target_node": "agent-09",
        "reason": "external_provider_actor_not_registered",
        "membership_authority": "replicated_mesh_manifest",
        "normalization_performed": False,
    }

    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request(
            "POST",
            "/v1/tasks",
            body=json.dumps({
                "task_id": "http-invalid-alias",
                "idempotency_key": "http-invalid-alias",
                "kind": "read_only_probe",
                "target_node": "agent-09",
            }),
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        assert response.status == 422
        assert payload["error"] == "task_target_not_canonical"
        assert payload["normalization_performed"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_completion_verifier_rejects_forged_hash_binding_and_fence():
    control = load_module(
        "factory_control_fleet_proof_verifier",
        ROOT / "ops" / "factory_control.py",
    )
    task, result, body = leased_task(control)
    evidence, verifier = control.verify_task_completion(
        task, result, body, body["result_reference"],
    )
    assert verifier["verdict"] == "passed"
    assert evidence["result_sha256"].startswith("sha256:")
    assert evidence["binding_sha256"].startswith("sha256:")

    forged_result = {**body, "result_sha256": "sha256:" + "0" * 64}
    _, result_verifier = control.verify_task_completion(
        task, result, forged_result, body["result_reference"],
    )
    assert result_verifier["verdict"] == "failed"
    assert "result_sha256" in result_verifier["failed_checks"]

    forged_binding = {**body, "binding_sha256": "sha256:" + "f" * 64}
    _, binding_verifier = control.verify_task_completion(
        task, result, forged_binding, body["result_reference"],
    )
    assert binding_verifier["verdict"] == "failed"
    assert "binding_sha256" in binding_verifier["failed_checks"]

    stale_fence = {**body, "attempt_id": "KOL-PROOF-1-attempt-0"}
    _, fence_verifier = control.verify_task_completion(
        task, result, stale_fence, body["result_reference"],
    )
    assert fence_verifier["verdict"] == "failed"
    assert "attempt" in fence_verifier["failed_checks"]
    assert control.lease_fence_error(task, stale_fence) == "attempt_id_mismatch"

    task["result"] = result
    task["result_reference"] = body["result_reference"]
    task["completion_evidence"] = evidence
    task["completion_verifier"] = verifier
    task["state"] = control.STATE_COMPLETED
    assert control.strict_completion_proof(task) is True
    tampered = copy.deepcopy(task)
    tampered["result"]["message"] = "tampered"
    assert control.strict_completion_proof(tampered) is False


def test_http_completion_persists_failed_then_passed_independent_verifier(monkeypatch):
    control = load_module(
        "factory_control_fleet_proof_http_verifier",
        ROOT / "ops" / "factory_control.py",
    )
    task, result, body = leased_task(control)
    tasks = {task["task_id"]: copy.deepcopy(task)}
    memory = MemoryRedis()
    monkeypatch.setattr(control, "redis", memory)
    monkeypatch.setattr(control, "load_task", lambda task_id: copy.deepcopy(tasks.get(task_id)))
    monkeypatch.setattr(
        control,
        "save_task",
        lambda value: tasks.__setitem__(value["task_id"], copy.deepcopy(value)),
    )
    monkeypatch.setattr(control, "get_json", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(
        control,
        "require_external_provider_actor_auth",
        lambda *_args, **_kwargs: True,
    )

    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address

        def post(value):
            connection = http.client.HTTPConnection(host, port, timeout=2)
            connection.request(
                "POST",
                f"/v1/tasks/{task['task_id']}/complete",
                body=json.dumps(value),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            return response.status, payload

        status, rejected = post({**body, "binding_sha256": "sha256:" + "0" * 64})
        assert status == 409
        assert rejected["error"] == "completion_verification_failed"
        assert tasks[task["task_id"]]["state"] == control.STATE_LEASED
        assert tasks[task["task_id"]]["completion_verifier"]["verdict"] == "failed"

        status, accepted = post(body)
        assert status == 200
        stored = tasks[task["task_id"]]
        assert accepted["task"]["state"] == control.STATE_COMPLETED
        assert stored["completion_verifier"]["verdict"] == "passed"
        assert control.strict_completion_proof(stored) is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_fleet_proof_has_dynamic_21_rows_and_unroutable_aged_queue(tmp_path, monkeypatch):
    control = load_module(
        "factory_control_fleet_proof_matrix",
        ROOT / "ops" / "factory_control.py",
    )
    manifest = tmp_path / "peers.json"
    node_ids = write_manifest(manifest, 21)
    control.configure_mesh_membership(manifest)
    current = datetime(2026, 7, 11, 4, 0, tzinfo=timezone.utc).timestamp()
    at = datetime.fromtimestamp(current, timezone.utc).isoformat()
    view = control.build_canonical_fleet_view(
        audit_nodes=fresh_runtime_nodes(node_ids, at),
        current=current,
    )
    task, result, body = leased_task(control)
    evidence, verifier = control.verify_task_completion(
        task, result, body, body["result_reference"],
    )
    task.update({
        "state": control.STATE_COMPLETED,
        "result": result,
        "result_reference": body["result_reference"],
        "completion_evidence": evidence,
        "completion_verifier": verifier,
        "updated_at": at,
    })
    stale = control.normalize_task({
        "task_id": "legacy-target",
        "idempotency_key": "legacy-target",
        "kind": "read_only_probe",
        "target_node": "agent-09",
        "required_capability": "read_only_probe",
    })
    stale["updated_at"] = "2026-07-10T12:00:00+00:00"
    monkeypatch.setattr(control, "get_json", lambda *_args, **_kwargs: {})

    payload = control.fleet_proof_payload(
        aged_after_seconds=3600,
        current=current,
        fleet_view=view,
        tasks=[task, stale],
        queued_task_ids=[stale["task_id"]],
    )

    assert len(payload["nodes"]) == 21
    assert payload["summary"]["fresh_total"] == 21
    assert payload["summary"]["strict_verified_total"] == 1
    assert payload["summary"]["missing_strict_verified_total"] == 20
    assert payload["summary"]["queued_issue_total"] == 1
    assert payload["queued_issues"][0]["target_node"] == "agent-09"
    assert payload["queued_issues"][0]["aged"] is True
    assert payload["queued_issues"][0]["routable"] is False
    assert payload["queued_issues"][0]["reason"] == "target_not_in_canonical_membership"


def fleet_payload(count: int) -> dict:
    nodes = [
        {
            "node_id": "home" if index == 0 else f"worker-{index:02d}",
            "freshness": "fresh",
            "schedulable": True,
            "capabilities": ["read_only_probe"],
        }
        for index in range(count)
    ]
    digest = "a" * 64 if count == 21 else "b" * 64
    return {
        "nodes": nodes,
        "membership": {
            "authority": "replicated_mesh_manifest",
            "digest": digest,
            "canonical_total": count,
            "epoch": 11,
        },
    }


@pytest.mark.parametrize("count", [21, 22])
def test_controller_plan_is_dynamic_for_21_and_new_22nd_node(count):
    campaign = load_module(
        f"fleet_capability_proof_controller_{count}",
        ROOT / "ops" / "fleet_capability_proof.py",
    )
    plan = campaign.build_campaign_plan(fleet_payload(count))
    assert plan["status"] == "ready"
    assert plan["summary"]["canonical_total"] == count
    assert len(plan["nodes"]) == count
    assert campaign.build_parser().parse_args([]).command == "plan"
    with pytest.raises(campaign.CampaignError, match="operator_expected"):
        campaign.build_campaign_plan(fleet_payload(count), expected_nodes=count + 1)


def test_controller_campaign_identity_is_fresh_or_explicitly_reproducible():
    campaign = load_module(
        "fleet_capability_proof_controller_identity",
        ROOT / "ops" / "fleet_capability_proof.py",
    )
    payload = fleet_payload(21)
    first = campaign.build_campaign_plan(payload)
    second = campaign.build_campaign_plan(payload)
    assert first["campaign_id"] != second["campaign_id"]
    assert {row["task_id"] for row in first["nodes"]}.isdisjoint(
        {row["task_id"] for row in second["nodes"]}
    )

    fixed_a = campaign.build_campaign_plan(payload, campaign_id="fleet-proof-fixed-001")
    fixed_b = campaign.build_campaign_plan(payload, campaign_id="fleet-proof-fixed-001")
    assert [row["task_id"] for row in fixed_a["nodes"]] == [
        row["task_id"] for row in fixed_b["nodes"]
    ]

    task = {
        "task_id": fixed_a["nodes"][0]["task_id"],
        "state": "failed",
        "envelope": {
            **fixed_a["nodes"][0]["envelope"],
            "source": {
                "kind": "fleet_capability_proof_campaign",
                "campaign_id": "fleet-proof-stale-000",
                "membership_digest": "f" * 64,
            },
        },
    }
    rejected = campaign.validate_completed_task(
        task,
        fixed_a["nodes"][0]["node_id"],
        campaign_id=fixed_a["campaign_id"],
        membership_digest=fixed_a["membership"]["digest"],
    )
    assert "campaign_id_mismatch" in rejected["reasons"]
    assert "campaign_membership_digest_mismatch" in rejected["reasons"]


def test_controller_run_submits_dynamic_tasks_and_validates_every_proof():
    campaign = load_module(
        "fleet_capability_proof_controller_run",
        ROOT / "ops" / "fleet_capability_proof.py",
    )
    plan = campaign.build_campaign_plan(fleet_payload(21))

    class FakeClient:
        def __init__(self):
            self.tasks = {}
            self.posts = []

        def request(self, method, path, payload=None):
            if method == "POST":
                self.posts.append((path, payload))
                node_id = payload["target_node"]
                task = {
                    "task_id": payload["task_id"],
                    "attempt_id": f"{payload['task_id']}-attempt-1",
                    "lease_owner": f"{node_id}:agent-host-{node_id}",
                    "result_reference": f"/proof/{payload['task_id']}/result.json",
                    "state": "completed",
                    "envelope": payload,
                }
                task["result"] = {
                    "status": "completed",
                    "task_id": task["task_id"],
                    "attempt_id": task["attempt_id"],
                    "node_id": node_id,
                    "agent_id": f"agent-host-{node_id}",
                    "result_path": task["result_reference"],
                }
                result_sha = campaign.canonical_json_sha256(task["result"])
                binding_sha = campaign.completion_binding_sha256(task, result_sha)
                task["completion_evidence"] = {
                    "schema_version": campaign.EVIDENCE_SCHEMA,
                    "task_id": task["task_id"],
                    "attempt_id": task["attempt_id"],
                    "lease_owner": task["lease_owner"],
                    "result_reference": task["result_reference"],
                    "result_sha256": result_sha,
                    "binding_sha256": binding_sha,
                }
                task["completion_verifier"] = {
                    "schema_version": campaign.VERIFIER_SCHEMA,
                    "verifier": "control-plane/home",
                    "independent": True,
                    "verdict": "passed",
                    "node_id": node_id,
                    "result_sha256": result_sha,
                    "binding_sha256": binding_sha,
                    "checks": {"task": True, "result": True, "attempt": True},
                }
                self.tasks[task["task_id"]] = task
                return {"task_id": task["task_id"], "state": "queued"}
            task_id = path.rsplit("/", 1)[-1]
            return self.tasks[task_id]

    client = FakeClient()
    report = campaign.execute_campaign(
        client,
        plan,
        timeout_seconds=1,
        poll_interval_seconds=0.01,
    )
    assert report["status"] == "completed"
    assert report["summary"] == {
        "canonical_total": 21,
        "verified_total": 21,
        "failed_total": 0,
    }
    assert len(client.posts) == 21
    assert {row["node_id"] for row in report["nodes"]} == {
        row["node_id"] for row in plan["nodes"]
    }


def test_controller_run_auth_token_requires_private_file(tmp_path):
    campaign = load_module(
        "fleet_capability_proof_controller_auth",
        ROOT / "ops" / "fleet_capability_proof.py",
    )
    with pytest.raises(campaign.CampaignError, match="required"):
        campaign.read_bearer_token(None, required=True)
    token_file = tmp_path / "factory.token"
    token_file.write_text("x" * 32, encoding="utf-8")
    token_file.chmod(0o644)
    with pytest.raises(campaign.CampaignError, match="permissions"):
        campaign.read_bearer_token(str(token_file), required=True)
    token_file.chmod(0o600)
    assert campaign.read_bearer_token(str(token_file), required=True) == "x" * 32
