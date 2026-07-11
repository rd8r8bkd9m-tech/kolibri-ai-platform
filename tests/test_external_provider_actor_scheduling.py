from __future__ import annotations

import copy
import http.client
import importlib.util
import json
import sys
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_control(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ops" / "factory_control.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def passed_probe(control):
    return {
        "model": control.CODEX_PROVIDER_MODEL,
        "sandbox": "read-only",
        "status": "passed",
        "duration_ms": 1200,
        "output_sha256": "a" * 64,
    }


def external_codex_node(control, node_id: str) -> dict:
    control.configure_external_provider_actor_token_sha256(
        "b" * 64,
        node_id=node_id,
        credential_id="test-mac-provider-v1",
        epoch=1,
    )
    checked_at = datetime.now(timezone.utc).isoformat()
    return {
        "node_id": node_id,
        "hostname": "owner-mac",
        "agent_id": f"{node_id}-agent",
        "health": "online",
        "heartbeat_at": checked_at,
        "labels": {
            "provider": "codex",
            "runtime": "macos_launchagent",
            "physical_node_id": node_id,
        },
        "capabilities": ["codex_provider_broker", "runner:codex"],
        "runners": {
            "codex": {
                **control.CODEX_FACTORY_RUNNER_CONTRACT,
                "status": "available",
                "checked_at": checked_at,
                "readiness_contract": control.CODEX_READINESS_SCHEMA,
                "access_mode": "local_service_account",
                "login_status": "authenticated",
                "error_type": None,
                "probe": passed_probe(control),
            },
        },
        "runner_readiness": {
            "codex": {
                "schema_version": control.CODEX_READINESS_SCHEMA,
                "node_id": node_id,
                "checked_at": checked_at,
                "access_mode": "local_service_account",
                "status": "available",
                "login_status": "authenticated",
                "error_type": None,
                "probe": passed_probe(control),
            },
        },
        "external_provider_auth": {
            "actor_scope": "external_provider_actor",
            "bound_node_id": node_id,
            "credential_id": "test-mac-provider-v1",
            "epoch": 1,
        },
    }


def provider_envelope(node_id: str, *, response_id: str = "resp_dynamic") -> dict:
    return {
        "task_id": f"KOL-PROVIDER-{response_id}",
        "idempotency_key": f"factory-provider:{response_id}",
        "kind": "owner_remote_task",
        "target_node": node_id,
        "required_capability": "runner:codex",
        "runner": "codex",
        "objective": "Answer through the read-only provider contract.",
        "write_scope": [],
        "constraints": {
            "read_only": True,
            "max_wall_seconds": 45,
            "network": "provider_managed_only",
        },
        "max_retries": 0,
        "fallback_allowed": False,
        "source": {
            "kind": "kolibri_provider_gateway",
            "control_plane": "home",
            "response_id": response_id,
            "identity_contract": "kolibri.public-identity.v1",
        },
    }


def test_dynamic_non_mesh_mac_actor_is_eligible_only_with_complete_live_contract(monkeypatch):
    control = load_control("factory_control_external_provider_actor")
    node_id = f"owner-mac-provider-{uuid.uuid4().hex[:10]}"
    node = external_codex_node(control, node_id)
    monkeypatch.setattr(
        control,
        "node_membership_annotation",
        lambda _node_id: {"membership_scope": "audit", "schedulable": False},
    )
    monkeypatch.setattr(control, "get_json", lambda *_args, **_kwargs: copy.deepcopy(node))

    class Redis:
        def command(self, *parts):
            assert parts == ("GET", control.drain_key(node_id))
            return None

    monkeypatch.setattr(control, "redis", Redis())
    eligibility = control.lease_node_eligibility(node_id)

    assert eligibility["eligible"] is True
    assert eligibility["lease_scope"] == control.EXTERNAL_PROVIDER_ACTOR_SCOPE
    assert eligibility["provider"] == "codex"
    assert eligibility["node"]["freshness"] == "fresh"


def test_external_actor_fails_closed_for_identity_capability_runner_and_readiness_drift():
    control = load_control("factory_control_external_provider_rejections")
    node_id = "dynamic-mac-broker"
    baseline = external_codex_node(control, node_id)
    mutations = []

    wrong_physical = copy.deepcopy(baseline)
    wrong_physical["labels"]["physical_node_id"] = "another-node"
    mutations.append(wrong_physical)
    wrong_runtime = copy.deepcopy(baseline)
    wrong_runtime["labels"]["runtime"] = "manual_process"
    mutations.append(wrong_runtime)
    missing_broker = copy.deepcopy(baseline)
    missing_broker["capabilities"].remove("codex_provider_broker")
    mutations.append(missing_broker)
    unsafe_runner = copy.deepcopy(baseline)
    unsafe_runner["runners"]["codex"]["sandbox"] = "danger-full-access"
    mutations.append(unsafe_runner)
    auth_failed = copy.deepcopy(baseline)
    auth_failed["runner_readiness"]["codex"]["login_status"] = "unauthenticated"
    mutations.append(auth_failed)
    probe_failed = copy.deepcopy(baseline)
    probe_failed["runner_readiness"]["codex"]["probe"]["status"] = "failed"
    mutations.append(probe_failed)
    stale_readiness = copy.deepcopy(baseline)
    stale = (datetime.now(timezone.utc) - timedelta(seconds=301)).isoformat()
    stale_readiness["runner_readiness"]["codex"]["checked_at"] = stale
    stale_readiness["runners"]["codex"]["checked_at"] = stale
    mutations.append(stale_readiness)

    for node in mutations:
        assert control.external_provider_actor_eligibility(node_id, node)["eligible"] is False


def test_external_actor_can_lease_only_exact_home_read_only_provider_task():
    control = load_control("factory_control_external_provider_task_scope")
    node_id = "dynamic-owner-mac"
    node = external_codex_node(control, node_id)
    context = {
        "lease_scope": control.EXTERNAL_PROVIDER_ACTOR_SCOPE,
        "provider": "codex",
    }
    capabilities = node["capabilities"]
    envelope = provider_envelope(node_id)
    task = control.normalize_task(envelope)

    assert control.compatible(task, node_id, capabilities, node, context) is True

    invalid_envelopes = []
    for path, value in [
        (("kind",), "read_only_probe"),
        (("target_node",), "another-node"),
        (("runner",), "mimo"),
        (("required_capability",), "generic_implementation"),
        (("write_scope",), ["backend/**"]),
        (("fallback_allowed",), True),
        (("max_retries",), 1),
        (("constraints", "read_only"), False),
        (("constraints", "network"), "unrestricted"),
        (("source", "control_plane"), "main"),
        (("source", "kind"), "telegram_miniapp"),
    ]:
        candidate = copy.deepcopy(envelope)
        target = candidate
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        invalid_envelopes.append(candidate)
    with_extra_command = copy.deepcopy(envelope)
    with_extra_command["command"] = ["sh", "-c", "write somewhere"]
    invalid_envelopes.append(with_extra_command)

    for candidate in invalid_envelopes:
        assert control.compatible(
            control.normalize_task(candidate), node_id, capabilities, node, context,
        ) is False


def test_external_actor_stays_outside_canonical_21_counts(tmp_path):
    control = load_control("factory_control_external_provider_fleet_boundary")
    node_ids = ["home", *[f"worker-{index:02d}" for index in range(1, 21)]]
    manifest = tmp_path / "peers.json"
    manifest.write_text(json.dumps({
        "schema_version": 3,
        "peers": {
            f"10.99.0.{index}": {"node_id": node_id, "mesh_ip": f"10.99.0.{index}"}
            for index, node_id in enumerate(node_ids, start=1)
        },
    }), encoding="utf-8")
    control.configure_mesh_membership(manifest)
    observed_at = datetime.now(timezone.utc).isoformat()
    observed = [
        {
            "node_id": node_id,
            "health": "online",
            "heartbeat_at": observed_at,
            "capabilities": ["generic_implementation"],
        }
        for node_id in node_ids
    ]
    external_id = f"mac-broker-{uuid.uuid4().hex[:8]}"
    observed.append(external_codex_node(control, external_id))

    view = control.build_canonical_fleet_view(audit_nodes=observed)

    assert len(view["active"]) == 21
    assert view["membership"]["registered_total"] == 21
    assert view["membership"]["schedulable_total"] == 21
    assert [node["node_id"] for node in view["historical"]] == [external_id]
    assert view["historical"][0]["schedulable"] is False
    assert view["historical"][0]["membership_scope"] == "audit"


def provider_health_task(
    node_id: str,
    runner: str,
    task_id: str,
    observed_at: datetime,
    *,
    state: str,
    result_status: str = "blocked",
    error_type: str | None = None,
    cancel_reason: str | None = None,
) -> dict:
    return {
        "task_id": task_id,
        "state": state,
        "created_at": (observed_at - timedelta(seconds=27.4)).isoformat(),
        "updated_at": observed_at.isoformat(),
        "error_type": error_type,
        "error": "PRIVATE ERROR TEXT MUST NOT LEAK",
        "cancel_reason": cancel_reason,
        "envelope": {
            "runner": runner,
            "target_node": node_id,
            "objective": "PRIVATE PROMPT MUST NOT LEAK",
            "source": {"kind": "kolibri_provider_gateway", "control_plane": "home"},
        },
        "result": {
            "status": result_status,
            "error_type": error_type,
            "response": "PRIVATE RESPONSE MUST NOT LEAK",
            "artifacts": ["PRIVATE ARTIFACT MUST NOT LEAK"],
        },
    }


def test_provider_health_projection_uses_latest_timestamp_and_never_leaks_private_fields():
    control = load_control("factory_control_provider_health_projection")
    now = datetime.now(timezone.utc)
    tasks = [
        provider_health_task(
            "node-a", "codex", "KOL-PROVIDER-zzz-older", now - timedelta(seconds=30),
            state="completed", result_status="completed",
        ),
        provider_health_task(
            "node-b", "codex", "KOL-PROVIDER-aaa-newest", now,
            state="completed", result_status="completed",
        ),
        provider_health_task(
            "node-a", "codex", "KOL-PROVIDER-aaa-newer", now - timedelta(seconds=5),
            state="cancelled", cancel_reason="factory_provider_poll_timeout",
        ),
        provider_health_task(
            "node-c", "codex", "KOL-PROVIDER-owner-cancel", now + timedelta(seconds=1),
            state="cancelled", cancel_reason="owner_cancelled",
        ),
        {
            **provider_health_task(
                "node-x", "codex", "UNRELATED-TASK", now + timedelta(seconds=2),
                state="failed", error_type="runner_unavailable",
            ),
            "envelope": {"runner": "codex", "target_node": "node-x", "objective": "private"},
        },
    ]

    records = control.provider_health_projection(list(reversed(tasks)), "codex", limit=64)

    assert [(record["node_id"], record["status"], record["reason"]) for record in records] == [
        ("node-b", "healthy", "verified_completion"),
        ("node-a", "open", "provider_timeout"),
    ]
    assert records[0]["latency_seconds"] == 27.4
    assert all(set(record) == {
        "node_id", "status", "reason", "observed_at", "latency_seconds",
    } for record in records)
    serialized = json.dumps(records)
    assert "PRIVATE" not in serialized


def test_provider_health_index_is_nonfatal_and_has_bounded_retention(monkeypatch):
    control = load_control("factory_control_provider_health_index_nonfatal")
    task = provider_health_task(
        "node-a", "codex", "KOL-PROVIDER-index-test",
        datetime.now(timezone.utc), state="completed", result_status="completed",
    )

    class FailedIndex:
        def command(self, *_parts):
            raise control.RedisError("synthetic auxiliary index outage")

    monkeypatch.setattr(control, "redis", FailedIndex())
    control.index_provider_health_task(task)  # must not surface as task/API failure

    calls = []

    class RecordingIndex:
        def command(self, *parts):
            calls.append(parts)
            return 1

    monkeypatch.setattr(control, "redis", RecordingIndex())
    control.index_provider_health_task(task)
    assert calls[0][0] == "ZADD"
    assert calls[1] == (
        "ZREMRANGEBYRANK", control.provider_health_index_key(), 0,
        -(control.PROVIDER_HEALTH_INDEX_RETAIN + 1),
    )
    assert control.PROVIDER_HEALTH_SCAN_LIMIT <= control.PROVIDER_HEALTH_INDEX_RETAIN


def test_provider_health_http_endpoint_is_bounded_chronological_and_sanitized(monkeypatch):
    control = load_control("factory_control_provider_health_http")
    now = datetime.now(timezone.utc)
    tasks = {
        "KOL-PROVIDER-z-old": provider_health_task(
            "node-a", "codex", "KOL-PROVIDER-z-old", now - timedelta(seconds=20),
            state="completed", result_status="completed",
        ),
        "KOL-PROVIDER-a-new": provider_health_task(
            "node-a", "codex", "KOL-PROVIDER-a-new", now,
            state="failed", error_type="runner_unavailable",
        ),
    }

    class Redis:
        def command(self, *parts):
            if parts[0] == "ZREVRANGE":
                # Deliberately return reverse lexical order; projection must
                # compare parsed timestamps rather than trust this sequence.
                return ["KOL-PROVIDER-z-old", "KOL-PROVIDER-a-new"]
            if parts[0] == "MGET":
                prefix = f"{control.NAMESPACE}:task:"
                return [json.dumps(tasks[str(key)[len(prefix):]]) for key in parts[1:]]
            raise AssertionError(parts)

    monkeypatch.setattr(control, "redis", Redis())
    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/v1/runtime/provider-health?runner=codex&limit=999")
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert response.status == 200
    assert payload == {
        "runner": "codex",
        "records": [{
            "node_id": "node-a",
            "status": "open",
            "reason": "runner_unavailable",
            "observed_at": now.isoformat(),
            "latency_seconds": 27.4,
        }],
    }
    assert "PRIVATE" not in json.dumps(payload)


def test_external_actor_http_auth_replay_rotation_and_all_six_mutations(monkeypatch):
    """Exercise the real HTTP wire contract; rejected auth never mutates state."""

    control = load_control("factory_control_external_provider_http_auth")
    agent_spec = importlib.util.spec_from_file_location(
        "agent_host_external_provider_http_auth", ROOT / "ops" / "agent_host.py",
    )
    assert agent_spec is not None and agent_spec.loader is not None
    agent = importlib.util.module_from_spec(agent_spec)
    sys.modules[agent_spec.name] = agent
    agent_spec.loader.exec_module(agent)

    node_id = "mac-codex-audit-test"
    token = "test-only-" + "a" * 40
    credential = {
        "schema_version": agent.EXTERNAL_PROVIDER_CREDENTIAL_SCHEMA,
        "credential_id": "test-http-v1",
        "node_id": node_id,
        "epoch": 1,
        "token": token,
    }
    control.configure_external_provider_actor_token_sha256(
        __import__("hashlib").sha256(token.encode()).hexdigest(),
        node_id=node_id,
        credential_id=credential["credential_id"],
        epoch=credential["epoch"],
    )
    assert (
        control.EXTERNAL_PROVIDER_AUTH_NONCE_TTL_SECONDS
        > 2 * control.EXTERNAL_PROVIDER_AUTH_CLOCK_SKEW_SECONDS
    )

    nodes: dict[str, dict] = {}
    tasks: dict[str, dict] = {}

    class MemoryRedis:
        def __init__(self):
            self.nonces: set[str] = set()

        def command(self, *parts):
            command = parts[0]
            if command == "SET" and "NX" in parts:
                redis_key = str(parts[1])
                if redis_key in self.nonces:
                    return None
                self.nonces.add(redis_key)
                return "OK"
            if command in {"SADD", "DEL"}:
                return 1
            if command == "GET":
                return None
            raise AssertionError(parts)

    memory_redis = MemoryRedis()
    monkeypatch.setattr(control, "redis", memory_redis)

    def get_json(redis_key, default=None):
        marker = f"{control.NAMESPACE}:node:"
        if str(redis_key).startswith(marker):
            return copy.deepcopy(nodes.get(str(redis_key)[len(marker):], default))
        return copy.deepcopy(default)

    def set_json(redis_key, value, **_kwargs):
        marker = f"{control.NAMESPACE}:node:"
        if str(redis_key).startswith(marker):
            nodes[str(redis_key)[len(marker):]] = copy.deepcopy(value)

    monkeypatch.setattr(control, "get_json", get_json)
    monkeypatch.setattr(control, "set_json", set_json)
    monkeypatch.setattr(
        control, "node_membership_annotation",
        lambda _node_id: {"membership_scope": "audit", "schedulable": False},
    )
    monkeypatch.setattr(control, "requeue_expired_leases", lambda: [])
    monkeypatch.setattr(control, "queue_ids", lambda: [])
    monkeypatch.setattr(control, "load_task", lambda task_id: copy.deepcopy(tasks.get(task_id)))
    monkeypatch.setattr(
        control, "save_task",
        lambda task: tasks.__setitem__(task["task_id"], copy.deepcopy(task)) or task,
    )
    monkeypatch.setattr(
        control, "truth_gate_on_complete",
        lambda task, _result: {**task, "truth_gate": {"verdict": "true"}},
    )
    monkeypatch.setattr(
        control, "truth_gate_on_fail",
        lambda task, error_type, _error: {
            **task, "truth_gate": {"verdict": "false", "error_type": error_type},
        },
    )
    monkeypatch.setattr(control, "mark_node_runner_failure", lambda *_args: None)

    server = control.ThreadingHTTPServer(("127.0.0.1", 0), control.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address

    def post(path, body, *, auth=None, headers=None, wire_body=None):
        payload = wire_body if wire_body is not None else json.dumps(
            body, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode()
        request_headers = {"Content-Type": "application/json"}
        if auth is not None:
            request_headers.update(agent.external_provider_request_headers(
                auth, node_id, "POST", path, body,
            ))
        if headers:
            request_headers.update(headers)
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("POST", path, body=payload, headers=request_headers)
        http_response = connection.getresponse()
        raw = http_response.read()
        connection.close()
        return http_response.status, json.loads(raw) if raw else None, request_headers

    def assert_auth_gate(path, body, *, success_status):
        before = copy.deepcopy((nodes, tasks))
        assert post(path, body)[0] == 401
        assert (nodes, tasks) == before
        wrong = {**credential, "token": "test-only-" + "z" * 40}
        assert post(path, body, auth=wrong)[0] == 401
        assert (nodes, tasks) == before
        assert post(path, body, auth=credential)[0] == success_status

    register_body = external_codex_node(control, node_id)
    register_body.pop("external_provider_auth")
    control.configure_external_provider_actor_token_sha256(
        __import__("hashlib").sha256(token.encode()).hexdigest(),
        node_id=node_id, credential_id=credential["credential_id"], epoch=1,
    )
    assert_auth_gate("/v1/nodes/register", register_body, success_status=200)
    marker_v1 = copy.deepcopy(nodes[node_id]["external_provider_auth"])

    heartbeat_body = {
        key: copy.deepcopy(value) for key, value in register_body.items()
        if key in {
            "node_id", "hostname", "agent_id", "pid", "capabilities", "runners",
            "runner_readiness", "labels", "cpu", "ram", "disk",
        }
    }
    assert_auth_gate(f"/v1/nodes/{node_id}/heartbeat", heartbeat_body, success_status=200)
    assert nodes[node_id]["external_provider_auth"] == marker_v1

    lease_body = {
        "node_id": node_id,
        "agent_id": register_body["agent_id"],
        "capabilities": register_body["capabilities"],
    }
    assert_auth_gate("/v1/tasks/lease", lease_body, success_status=204)

    def leased_task(task_id):
        task = control.normalize_task(provider_envelope(node_id, response_id=task_id))
        task.update({
            "task_id": task_id,
            "state": control.STATE_LEASED,
            "attempt": 1,
            "attempt_id": f"{task_id}-attempt-1",
            "lease_owner": f"{node_id}:{register_body['agent_id']}",
            "lease_actor_scope": control.EXTERNAL_PROVIDER_ACTOR_SCOPE,
            "lease_external_auth": copy.deepcopy(marker_v1),
        })
        tasks[task_id] = task
        return task

    # Prove task-persisted auth survives disappearance of the mutable node card.
    nodes.clear()
    task = leased_task("auth-heartbeat")
    fence = {
        "attempt_id": task["attempt_id"], "node_id": node_id,
        "agent_id": register_body["agent_id"],
    }
    assert_auth_gate(
        "/v1/tasks/auth-heartbeat/heartbeat", {**fence, "state": "running"},
        success_status=200,
    )

    task = leased_task("auth-complete")
    complete = {
        "attempt_id": task["attempt_id"], "node_id": node_id,
        "agent_id": register_body["agent_id"],
        "result_reference": "/var/lib/kolibri-agent/auth-complete/result.json",
        "result": {
            "runner": "codex",
            "status": "completed",
            "result_path": "/var/lib/kolibri-agent/auth-complete/result.json",
        },
    }
    assert_auth_gate("/v1/tasks/auth-complete/complete", complete, success_status=200)

    task = leased_task("auth-fail")
    failed = {
        "attempt_id": task["attempt_id"], "node_id": node_id,
        "agent_id": register_body["agent_id"], "error_type": "runtime_error",
        "error": "synthetic failure", "retry": False,
        "result": {"runner": "codex", "status": "blocked"},
    }
    assert_auth_gate("/v1/tasks/auth-fail/fail", failed, success_status=200)

    # Exact-wire tampering is rejected before state mutation.
    nodes[node_id] = copy.deepcopy(register_body)
    nodes[node_id]["external_provider_auth"] = marker_v1
    _, _, signed_headers = post(
        f"/v1/nodes/{node_id}/heartbeat", heartbeat_body, auth=credential,
    )
    tampered = {**heartbeat_body, "pid": 999999}
    tampered_wire = json.dumps(tampered, sort_keys=True, separators=(",", ":")).encode()
    assert post(
        f"/v1/nodes/{node_id}/heartbeat", tampered,
        headers=signed_headers, wire_body=tampered_wire,
    )[0] == 401

    # Reusing an otherwise-valid signature is rejected by the Redis nonce fence.
    replay_headers = agent.external_provider_request_headers(
        credential, node_id, "POST", f"/v1/nodes/{node_id}/heartbeat", heartbeat_body,
    )
    assert post(f"/v1/nodes/{node_id}/heartbeat", heartbeat_body, headers=replay_headers)[0] == 200
    assert post(f"/v1/nodes/{node_id}/heartbeat", heartbeat_body, headers=replay_headers)[0] == 409

    # A valid signed heartbeat upgrades a legacy exact actor card to the server marker.
    nodes[node_id] = copy.deepcopy(register_body)
    assert "external_provider_auth" not in nodes[node_id]
    assert post(f"/v1/nodes/{node_id}/heartbeat", heartbeat_body, auth=credential)[0] == 200
    assert nodes[node_id]["external_provider_auth"] == marker_v1

    # Rotation is monotonic through register; the superseded token immediately fails.
    next_token = "test-only-" + "n" * 40
    next_credential = {**credential, "credential_id": "test-http-v2", "epoch": 2, "token": next_token}
    control.configure_external_provider_actor_token_sha256(
        __import__("hashlib").sha256(next_token.encode()).hexdigest(),
        node_id=node_id, credential_id=next_credential["credential_id"], epoch=2,
    )
    assert post("/v1/nodes/register", register_body, auth=next_credential)[0] == 200
    assert nodes[node_id]["external_provider_auth"]["epoch"] == 2
    assert post(f"/v1/nodes/{node_id}/heartbeat", heartbeat_body, auth=credential)[0] == 401

    serialized = json.dumps({"nodes": nodes, "tasks": tasks})
    assert token not in serialized
    assert next_token not in serialized

    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
