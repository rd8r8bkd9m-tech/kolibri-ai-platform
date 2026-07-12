import importlib.util
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def load_execution_api():
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("execution_api_contract", BACKEND / "execution_api.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_client(tmp_path):
    execution = load_execution_api()
    execution.configure_execution_store(tmp_path / "execution.db")
    execution.configure_execution_auth(["test-execution-key"])
    class VerifiedTestGateway:
        def generate(self, input_value, instructions, response_id):
            del instructions, response_id
            text = "4" if "2+2" in str(input_value) else "Verified Kolibri response"
            evidence = [{
                "type": "provider_execution", "provider": "local", "provider_model": "test-runner",
                "exit_code": 0, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "output_bytes": len(text.encode()),
                "completion_signal": "non_empty_assistant_output",
            }]
            return SimpleNamespace(status="completed", text=text, technical={
                "selected_provider": "local",
                "fallback_candidates": ["mimo", "openai-compatible"],
                "attempts": [{"attempt": 1, "provider": "local", "status": "succeeded", "evidence": evidence}],
                "fallback_used": False,
                "evidence": evidence,
            })
    import provider_gateway
    import capability_gateway
    provider_gateway.configure_provider_gateway(VerifiedTestGateway())
    capability_gateway.configure_capability_gateway(
        capability_gateway.CapabilityGateway([], cache_ttl=0, include_packaged_registry=False)
    )
    app = FastAPI()
    app.include_router(execution.router)
    return execution, TestClient(
        app, headers={"Authorization": "Bearer test-execution-key"},
    )


def create_project_and_stream(client, suffix="x", binding=None):
    project = client.post("/v1/projects", json={
        "idempotency_key": f"project-{suffix}", "name": f"Project {suffix}", "binding": binding,
    }).json()
    stream = client.post(f"/v1/projects/{project['id']}/workstreams", json={
        "idempotency_key": f"stream-{suffix}", "name": f"Stream {suffix}", "binding": binding,
    }).json()
    return project, stream


def test_execution_router_requires_bearer_auth(tmp_path):
    execution = load_execution_api()
    execution.configure_execution_store(tmp_path / "auth.db")
    execution.configure_execution_auth(["expected-key"])
    app = FastAPI()
    app.include_router(execution.router)
    anonymous = TestClient(app)

    assert anonymous.get("/v1/projects").status_code == 401
    assert anonymous.get(
        "/v1/projects", headers={"Authorization": "Bearer wrong-key"},
    ).status_code == 401
    assert anonymous.get(
        "/v1/projects", headers={"Authorization": "Bearer expected-key"},
    ).status_code == 200


def test_project_workstream_backlog_checkpoint_resume_is_durable(tmp_path):
    execution, client = make_client(tmp_path)
    project = client.post("/v1/projects", json={"idempotency_key": "project-1", "name": "Kolibri OS", "objective": "Universal AI OS"}).json()
    stream = client.post(
        f"/v1/projects/{project['id']}/workstreams",
        json={"idempotency_key": "stream-1", "name": "Execution core", "objective": "Ship compatibility contracts"},
    ).json()
    backlog = client.post(
        f"/v1/workstreams/{stream['id']}/backlog",
        json={"idempotency_key": "backlog-1", "title": "Rust core handoff", "priority": "high", "acceptance": ["versioned API"]},
    ).json()
    checkpoint = client.post(
        f"/v1/workstreams/{stream['id']}/checkpoints",
        json={"idempotency_key": "checkpoint-1", "label": "API slice", "summary": "Contracts created", "next_actions": ["Rust core"]},
    ).json()

    execution.configure_execution_store(tmp_path / "execution.db")
    resumed = client.post("/v1/resume", json={"project_id": project["id"], "workstream_id": stream["id"]}).json()

    assert resumed["schema_version"] == "kolibri.execution.v1"
    assert resumed["project"]["id"] == project["id"]
    assert resumed["workstreams"][0]["backlog"][0]["id"] == backlog["id"]
    assert resumed["workstreams"][0]["checkpoints"][0]["id"] == checkpoint["id"]


def test_openai_like_response_lifecycle_records_provider_fallback(tmp_path):
    _, client = make_client(tmp_path)
    created = client.post(
        "/v1/responses",
        json={
            "idempotency_key": "response-1",
            "input": "Build the execution loop",
            "model": "kolibri",
            "technical": {"provider_preferences": ["local", "mimo", "openai-compatible"]},
            "metadata": {"trace": "T-1"},
        },
    )
    assert created.status_code == 201
    response = created.json()
    assert response["object"] == "response"
    assert response["status"] == "completed"
    assert response["output_text"] == "Verified Kolibri response"
    assert response["technical"]["provider_routing"]["selected_provider"] == "local"
    assert response["technical"]["provider_routing"]["fallback_candidates"] == ["mimo", "openai-compatible"]
    assert response["technical"]["provider_routing"]["attempts"][0]["status"] == "succeeded"

    fallback = client.post(
        f"/v1/responses/{response['id']}/provider-attempts",
        json={
            "idempotency_key": "provider-fallback-1",
            "provider": "mimo",
            "model": "kolibri",
            "status": "running",
            "reason": "local failed without credentials",
        },
    )
    assert fallback.status_code == 201
    assert fallback.json()["provider_attempt"]["attempt"] == 2
    assert fallback.json()["technical"]["provider_routing"]["selected_provider"] == "mimo"
    assert fallback.json()["technical"]["provider_routing"]["fallback_candidates"] == ["openai-compatible"]
    fallback_duplicate = client.post(
        f"/v1/responses/{response['id']}/provider-attempts",
        json={
            "idempotency_key": "provider-fallback-1", "provider": "mimo", "model": "kolibri",
            "status": "running", "reason": "local failed without credentials",
        },
    )
    assert fallback_duplicate.json()["provider_attempt"]["attempt"] == 2

    fetched = client.get(f"/v1/responses/{response['id']}").json()
    assert len(fetched["technical"]["provider_routing"]["attempts"]) == 2
    streamed_events = client.get(
        f"/v1/responses/{response['id']}/events",
        headers={"Accept": "text/event-stream", "Last-Event-ID": "0"},
    )
    assert streamed_events.status_code == 200
    assert streamed_events.headers["content-type"].startswith("text/event-stream")
    assert "event: response.created" in streamed_events.text
    assert "event: done" in streamed_events.text
    cancelled = client.post(f"/v1/responses/{response['id']}/cancel").json()
    assert cancelled["status"] == "completed"


def test_openai_compatible_response_accepts_header_or_server_generated_idempotency(tmp_path):
    _, client = make_client(tmp_path)
    without_key = client.post("/v1/responses", json={"model": "kolibri", "input": "hello"})
    assert without_key.status_code == 201
    assert without_key.json()["status"] == "completed"

    payload = {"model": "kolibri", "input": "same retry"}
    first = client.post("/v1/responses", headers={"Idempotency-Key": "header-retry-1"}, json=payload)
    second = client.post("/v1/responses", headers={"Idempotency-Key": "header-retry-1"}, json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


def test_chat_completions_compatibility_uses_public_kolibri_and_streams_sse(tmp_path):
    _, client = make_client(tmp_path)
    request = {
        "model": "kolibri",
        "messages": [{"role": "user", "content": "2+2"}],
    }
    completion = client.post("/v1/chat/completions", json=request)
    assert completion.status_code == 200
    payload = completion.json()
    assert payload["object"] == "chat.completion"
    assert payload["model"] == "kolibri"
    assert payload["choices"][0]["message"] == {"role": "assistant", "content": "4"}
    assert "provider" not in payload

    streamed = client.post("/v1/chat/completions", json={**request, "stream": True})
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "chat.completion.chunk" in streamed.text
    assert streamed.text.rstrip().endswith("data: [DONE]")


def test_models_and_1000_logical_actor_runtime_summary(tmp_path):
    execution, client = make_client(tmp_path)
    models = client.get("/v1/models").json()
    assert {item["id"] for item in models["data"]} == {"kolibri"}
    assert "formulalm" not in {item["id"] for item in models["data"]}

    summary = client.get("/v1/runtime/swarm").json()
    assert summary["logical_actors"] == 1000
    assert summary["actors_by_status"] == {"idle": 1000}
    assert summary["representation"] == "durable_state_records"
    assert summary["os_processes_spawned"] == 0

    execution.configure_execution_store(tmp_path / "execution.db")
    assert client.get("/v1/swarm/runtime/status").json()["logical_actors"] == 1000


def test_formulalm_learning_candidate_is_sanitized_and_never_auto_promoted(tmp_path):
    execution, client = make_client(tmp_path)
    response = client.post("/v1/responses", json={"idempotency_key": "learn-response", "input": "learn safely"}).json()
    raw_secret = "sk-super-secret-value-123456789"
    candidate = client.post(
        "/v1/learning/candidates",
        json={
            "source_response_id": response["id"],
            "idempotency_key": "learning-1",
            "kind": "procedural",
            "summary": f"Never persist {raw_secret}",
            "examples": [{"input": "safe", "authorization": "Bearer abcdefghijklmnop"}],
            "metadata": {"api_key": raw_secret, "nested": {"token": "plain-secret"}},
            "consent": True,
            "license": "owned",
            "data_classification": "private",
        },
    ).json()

    serialized = json.dumps(candidate)
    assert raw_secret not in serialized
    assert "abcdefghijklmnop" not in serialized
    assert candidate["metadata"]["api_key"] == "[REDACTED]"
    assert candidate["metadata"]["nested"]["token"] == "[REDACTED]"
    assert candidate["requires_eval"] is True
    assert candidate["auto_promote"] is False
    assert candidate["promotion_status"] == "candidate"
    assert candidate["schema_version"] == "kolibri.learning-candidate.v1"
    assert candidate["consent"] == "explicit"
    assert candidate["license"] == "permitted"
    assert candidate["quality_verdict"] == "pending"
    assert candidate["sanitization"]["status"] == "passed"
    assert candidate["sanitization_report"]["secret_material_persisted"] is False

    with execution.get_store().connect() as conn:
        persisted = conn.execute("SELECT payload FROM execution_records WHERE record_id = ?", (candidate["id"],)).fetchone()[0]
    assert raw_secret not in persisted


def test_typed_artifacts_validate_canvas_preview_automation_and_file(tmp_path):
    _, client = make_client(tmp_path)
    response = client.post("/v1/responses", json={"idempotency_key": "artifact-response", "input": "produce artifacts"}).json()
    artifacts = [
        ("canvas", {"title": "Execution DAG", "nodes": [{"id": "n1", "kind": "task"}], "edges": []}),
        ("preview", {"url": "https://preview.invalid", "status": "ready"}),
        ("automation", {"name": "Nightly eval", "trigger": {"cron": "0 0 * * *"}, "action": {"kind": "eval"}}),
        ("file", {"name": "result.json", "uri": "artifact://result.json", "media_type": "application/json"}),
    ]
    for index, (kind, payload) in enumerate(artifacts):
        result = client.post("/v1/artifacts", json={"idempotency_key": f"artifact-{index}", "response_id": response["id"], "kind": kind, "payload": payload})
        assert result.status_code == 201
        assert result.json()["payload"]["schema_version"].startswith("kolibri.")

    invalid = client.post("/v1/artifacts", json={"kind": "preview", "payload": {"status": "ready"}})
    assert invalid.status_code == 422


def test_main_mounts_new_router_without_removing_legacy_routes(tmp_path, monkeypatch):
    source = (BACKEND / "main.py").read_text(encoding="utf-8")
    assert "app.include_router(v1_router)" in source
    assert "app.include_router(execution_router)" in source
    assert '@app.post("/api/chat")' in source
    assert '@app.get("/api/models")' in source
    assert "PROXY_ROUTES" not in source
    assert "10.99.0." not in source

    monkeypatch.setenv("KOLIBRI_DATA_DIR", str(tmp_path / "kolibri-data"))
    monkeypatch.setenv("KOLIBRI_EXECUTION_DB_PATH", str(tmp_path / "kolibri-data" / "execution.db"))
    for module_name in ("data_paths", "execution_api", "tts"):
        monkeypatch.delitem(sys.modules, module_name, raising=False)
    spec = importlib.util.spec_from_file_location("backend_main_mounted_contract", BACKEND / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    paths = set(module.app.openapi()["paths"])
    assert {
        "/api/chat", "/api/models", "/v1/models", "/v1/responses", "/v1/resume",
        "/v1/plans", "/v1/tasks/{task_id}/events",
    } <= paths
    assert "/{prefix}/{path}" not in paths
    assert (tmp_path / "kolibri-data" / "kolibri.db").is_file()


def test_mutating_create_routes_are_idempotent_and_conflicts_are_rejected(tmp_path):
    execution, client = make_client(tmp_path)
    payload = {"idempotency_key": "stable-project", "name": "Stable"}
    first = client.post("/v1/projects", json=payload)
    second = client.post("/v1/projects", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]

    conflict = client.post("/v1/projects", json={**payload, "name": "Different"})
    assert conflict.status_code == 409
    with execution.get_store().connect() as conn:
        mapping = conn.execute(
            "SELECT record_id FROM execution_idempotency WHERE scope='projects' AND idempotency_key='stable-project'"
        ).fetchall()
    assert [row[0] for row in mapping] == [first.json()["id"]]


def test_response_events_are_monotonic_deduplicated_and_transactionally_outboxed(tmp_path):
    execution, client = make_client(tmp_path)
    response = client.post("/v1/responses", json={"idempotency_key": "events-response", "input": "observe"}).json()
    first = client.post(f"/v1/responses/{response['id']}/events", json={
        "idempotency_key": "worker-start", "event_type": "response.worker_started", "payload": {"worker": "logical-1"},
    })
    duplicate = client.post(f"/v1/responses/{response['id']}/events", json={
        "idempotency_key": "worker-start", "event_type": "response.worker_started", "payload": {"worker": "logical-1"},
    })
    second = client.post(f"/v1/responses/{response['id']}/events", json={
        "idempotency_key": "worker-stop", "event_type": "response.worker_stopped", "payload": {},
    })
    assert first.status_code == duplicate.status_code == second.status_code == 201
    assert first.json()["id"] == duplicate.json()["id"]

    events = client.get(f"/v1/responses/{response['id']}/events").json()["data"]
    assert [event["sequence"] for event in events] == [1, 2, 3, 4, 5]
    assert [event["event_type"] for event in events] == [
        "response.created", "response.provider_gateway_started", "response.completed",
        "response.worker_started", "response.worker_stopped",
    ]
    with execution.get_store().connect() as conn:
        outbox = conn.execute("SELECT event_id, status FROM execution_outbox ORDER BY created_at, outbox_id").fetchall()
    assert len(outbox) == 5
    assert {row[1] for row in outbox} == {"pending"}

    changed_duplicate = client.post(f"/v1/responses/{response['id']}/events", json={
        "idempotency_key": "worker-start", "event_type": "response.worker_started", "payload": {"worker": "other"},
    })
    assert changed_duplicate.status_code == 409


def test_resume_selects_latest_active_records_and_creates_only_when_explicit(tmp_path):
    _, client = make_client(tmp_path)
    project, first_stream = create_project_and_stream(client, "resume-a", binding="customer-a")
    second_stream = client.post(f"/v1/projects/{project['id']}/workstreams", json={
        "idempotency_key": "stream-resume-b", "name": "Latest", "binding": "customer-a",
    }).json()
    old_checkpoint = client.post(f"/v1/workstreams/{second_stream['id']}/checkpoints", json={
        "idempotency_key": "cp-old", "label": "Old",
    }).json()
    new_checkpoint = client.post(f"/v1/workstreams/{second_stream['id']}/checkpoints", json={
        "idempotency_key": "cp-new", "label": "New",
    }).json()
    old_backlog = client.post(f"/v1/workstreams/{second_stream['id']}/backlog", json={
        "idempotency_key": "bl-old", "title": "Old backlog",
    }).json()
    new_backlog = client.post(f"/v1/workstreams/{second_stream['id']}/backlog", json={
        "idempotency_key": "bl-new", "title": "New backlog", "state": "ready",
    }).json()

    resumed = client.post("/v1/resume", json={"binding": "customer-a"})
    assert resumed.status_code == 200
    selected = resumed.json()["selected"]
    assert selected["project"]["id"] == project["id"]
    assert selected["workstream"]["id"] == second_stream["id"] != first_stream["id"]
    assert selected["checkpoint"]["id"] == new_checkpoint["id"] != old_checkpoint["id"]
    assert selected["backlog_item"]["id"] == new_backlog["id"] != old_backlog["id"]

    missing = client.post("/v1/resume", json={"binding": "missing"})
    assert missing.status_code == 404
    without_key = client.post("/v1/resume", json={"binding": "new", "create_new": True})
    assert without_key.status_code == 422
    created = client.post("/v1/resume", json={
        "binding": "new", "create_new": True, "idempotency_key": "resume-create",
        "project_name": "Created", "workstream_name": "Created stream",
    })
    assert created.status_code == 200
    assert created.json()["selected"]["project"]["name"] == "Created"


def test_list_read_and_project_workstream_referential_contracts(tmp_path):
    _, client = make_client(tmp_path)
    project_a, stream_a = create_project_and_stream(client, "ref-a")
    project_b, stream_b = create_project_and_stream(client, "ref-b")
    assert len(client.get("/v1/projects").json()["data"]) == 2
    assert client.get(f"/v1/projects/{project_a['id']}").json()["id"] == project_a["id"]
    assert client.get(f"/v1/projects/{project_a['id']}/workstreams").json()["data"][0]["id"] == stream_a["id"]
    assert client.get(f"/v1/workstreams/{stream_a['id']}").json()["project_id"] == project_a["id"]

    mismatch = client.post("/v1/responses", json={
        "idempotency_key": "bad-binding", "input": "must reject",
        "project_id": project_a["id"], "workstream_id": stream_b["id"],
    })
    assert mismatch.status_code == 409
    assert client.get(f"/v1/projects/{project_b['id']}").status_code == 200


def test_plan_task_dag_resource_slots_and_legal_transitions(tmp_path):
    execution, client = make_client(tmp_path)
    project, stream = create_project_and_stream(client, "dag")
    plan = client.post("/v1/plans", json={
        "idempotency_key": "plan-dag", "project_id": project["id"], "workstream_id": stream["id"],
        "goal": "Build DAG", "resource_slot_limit": 3,
    }).json()
    task_a = client.post(f"/v1/plans/{plan['id']}/tasks", json={
        "idempotency_key": "task-a", "title": "A", "resource_slots": 1,
    }).json()
    task_b = client.post(f"/v1/plans/{plan['id']}/tasks", json={
        "idempotency_key": "task-b", "title": "B", "resource_slots": 2, "dependencies": [task_a["id"]],
    }).json()
    task_b_retry = client.post(f"/v1/plans/{plan['id']}/tasks", json={
        "idempotency_key": "task-b", "title": "B", "resource_slots": 2, "dependencies": [task_a["id"]],
    })
    assert task_b_retry.status_code == 201
    assert task_b_retry.json()["id"] == task_b["id"]
    overflow = client.post(f"/v1/plans/{plan['id']}/tasks", json={
        "idempotency_key": "task-overflow", "title": "Overflow", "resource_slots": 1,
    })
    assert overflow.status_code == 409
    unknown_dependency = client.post(f"/v1/plans/{plan['id']}/tasks", json={
        "idempotency_key": "task-unknown", "title": "Unknown", "dependencies": ["task_missing"],
    })
    assert unknown_dependency.status_code == 422

    dag = client.get(f"/v1/plans/{plan['id']}").json()
    assert dag["allocated_resource_slots"] == 3
    assert dag["os_processes_spawned"] == 0
    assert {tuple(edge.values()) for edge in dag["dag"]["edges"]} == {(task_a["id"], task_b["id"])}

    assert client.post(f"/v1/tasks/{task_a['id']}/transition", json={
        "idempotency_key": "a-ready", "to_state": "ready",
    }).json()["status"] == "ready"
    illegal = client.post(f"/v1/tasks/{task_a['id']}/transition", json={
        "idempotency_key": "a-complete-too-soon", "to_state": "completed",
    })
    assert illegal.status_code == 409
    attempt_id = "attempt-task-a-0001"
    lease_owner = "worker:test-agent"
    for index, state in enumerate(["queued", "leased", "running"]):
        transition = {
            "idempotency_key": f"a-{index}-{state}", "to_state": state,
        }
        if state in {"leased", "running"}:
            transition.update({"attempt_id": attempt_id, "lease_owner": lease_owner})
        result = client.post(f"/v1/tasks/{task_a['id']}/transition", json=transition)
        assert result.status_code == 200
    unverified = client.post(f"/v1/tasks/{task_a['id']}/transition", json={
        "idempotency_key": "a-unverified-completed", "to_state": "completed",
        "attempt_id": attempt_id, "lease_owner": lease_owner,
    })
    assert unverified.status_code == 409
    stale_attempt = client.post(f"/v1/tasks/{task_a['id']}/transition", json={
        "idempotency_key": "a-stale-completed", "to_state": "completed",
        "attempt_id": "attempt-stale-0001", "lease_owner": lease_owner,
        "evidence": [{"type": "task_output", "sha256": "a" * 64}],
        "verifier": {"verdict": "passed", "attempt_id": "attempt-stale-0001"},
    })
    assert stale_attempt.status_code == 409
    completed = client.post(f"/v1/tasks/{task_a['id']}/transition", json={
        "idempotency_key": "a-verified-completed", "to_state": "completed",
        "attempt_id": attempt_id, "lease_owner": lease_owner,
        "evidence": [{"type": "task_output", "sha256": "a" * 64}],
        "verifier": {"verdict": "passed", "attempt_id": attempt_id},
    })
    assert completed.status_code == 200
    assert client.get(f"/v1/tasks/{task_a['id']}").json()["status"] == "completed"
    assert client.get(f"/v1/tasks/{task_a['id']}/events").json()["data"][-1]["payload"]["to_state"] == "completed"
    with execution.get_store().connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM logical_actors").fetchone()[0] == 0


def test_learning_candidate_consent_license_and_extended_sanitization_gate(tmp_path):
    _, client = make_client(tmp_path)
    response = client.post("/v1/responses", json={"idempotency_key": "learning-gate-response", "input": "candidate"}).json()
    base = {
        "source_response_id": response["id"], "kind": "semantic", "summary": "candidate",
        "data_classification": "private", "license": "owned",
    }
    no_consent = client.post("/v1/learning/candidates", json={**base, "idempotency_key": "no-consent", "consent": False})
    assert no_consent.status_code == 422
    prohibited = client.post("/v1/learning/candidates", json={
        **base, "idempotency_key": "bad-license", "consent": True, "license": "prohibited",
    })
    assert prohibited.status_code == 422

    jwt = "eyJabcdefghijk.abcdefghijklmnop.qrstuvwxyz12345"
    accepted = client.post("/v1/learning/candidates", json={
        **base,
        "idempotency_key": "sanitized-extended", "consent": True,
        "summary": f"candidate {jwt}",
        "metadata": {
            "client_secret": "hidden",
            "session_cookie": "cookie-value",
            "headers": {"X-API-Key": "header-secret", "safe": "kept"},
            "safe": "kept",
        },
    })
    assert accepted.status_code == 201
    candidate = accepted.json()
    assert jwt not in json.dumps(candidate)
    assert candidate["metadata"]["client_secret"] == "[REDACTED]"
    assert candidate["metadata"]["session_cookie"] == "[REDACTED]"
    assert candidate["metadata"]["headers"]["X-API-Key"] == "[REDACTED]"
    assert candidate["metadata"]["safe"] == "kept"
    assert candidate["sanitization_report"]["redacted_fields"] == 3
    assert candidate["sanitization_report"]["redacted_value_patterns"] >= 1


def test_canonical_learning_candidate_contract_rejects_denied_negative_and_bad_hash(tmp_path):
    _, client = make_client(tmp_path)
    response = client.post(
        "/v1/responses",
        json={"idempotency_key": "canonical-learning-response", "input": "candidate"},
    ).json()
    base = {
        "source_response_id": response["id"],
        "source_trace_id": response["id"],
        "kind": "procedural",
        "capability": "code.review",
        "summary": "sanitized candidate",
        "data_classification": "private",
        "retention_class": "training-approved",
        "quality_verdict": "pending",
    }

    denied = client.post("/v1/learning/candidates", json={
        **base, "idempotency_key": "canonical-denied", "consent": "denied", "license": "permitted",
    })
    negative = client.post("/v1/learning/candidates", json={
        **base, "idempotency_key": "canonical-negative", "consent": "explicit", "license": "negative",
    })
    bad_hash = client.post("/v1/learning/candidates", json={
        **base, "idempotency_key": "canonical-bad-hash", "consent": "explicit", "license": "permitted",
        "artifact_hashes": ["sha256:not-a-digest"],
    })
    accepted = client.post("/v1/learning/candidates", json={
        **base, "idempotency_key": "canonical-accepted", "consent": "explicit", "license": "permitted",
        "artifact_hashes": ["sha256:" + "a" * 64],
        "credit_assignment": {"verifier": 1.0},
    })

    assert denied.status_code == 422
    assert negative.status_code == 422
    assert bad_hash.status_code == 422
    assert accepted.status_code == 201
    candidate = accepted.json()
    assert candidate["training_eligible"] is True
    assert candidate["artifact_hashes"] == ["sha256:" + "a" * 64]
    assert candidate["promotion_status"] == "candidate"

    status = client.get("/v1/learning/status")
    assert status.status_code == 200
    plane = status.json()
    assert plane["mode"] == "candidate-only"
    assert plane["candidate_count"] == 1
    assert plane["training_eligible_count"] == 1
    assert plane["by_promotion_status"] == {"candidate": 1}
    assert plane["request_path_training"] is False
    assert plane["production_weight_mutation"] is False
    assert plane["auto_promote"] is False


def test_public_model_is_strictly_kolibri_and_router_openapi_is_mounted_shape(tmp_path):
    execution, client = make_client(tmp_path)
    assert client.get("/v1/models").json()["data"][0]["id"] == "kolibri"
    assert client.get("/v1/models/formulalm").status_code == 404
    assert client.post("/v1/responses", json={
        "idempotency_key": "wrong-model", "model": "formulalm", "input": "no",
    }).status_code == 422
    response = client.post("/v1/responses", json={
        "idempotency_key": "public-kolibri", "model": "kolibri", "input": "yes",
    }).json()
    assert response["model"] == "kolibri"
    assert "provider_routing" not in response
    assert "provider_routing" in response["technical"]

    schema = client.app.openapi()
    required = {
        "/v1/resume", "/v1/responses", "/v1/responses/{response_id}/events",
        "/v1/plans", "/v1/plans/{plan_id}/tasks", "/v1/tasks/{task_id}/transition",
        "/v1/tasks/{task_id}/events", "/v1/artifacts", "/v1/learning/candidates",
    }
    assert required <= set(schema["paths"])
    assert execution.API_VERSION == "kolibri.execution.v1"


def test_capability_endpoints_validate_tools_and_ignore_client_provider_preferences(tmp_path, monkeypatch):
    execution, client = make_client(tmp_path)
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex.chmod(0o755)
    manifest = tmp_path / "kolibri-tools.json"
    manifest.write_text(json.dumps({
        "tools": [{
            "id": "tool:search", "name": "search", "status": "available",
            "providers": ["codex"], "aliases": ["web_search"],
        }]
    }), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", str(codex))

    import capability_gateway
    import provider_gateway
    capability_gateway.configure_capability_gateway(
        capability_gateway.CapabilityGateway([manifest], cache_ttl=0, include_packaged_registry=False)
    )

    calls = []

    class ToolGateway:
        def generate(self, input_value, instructions, response_id, requested_tools=None, planned_skills=None):
            del instructions, response_id, planned_skills
            calls.append({"input": input_value, "tools": requested_tools})
            text = "Source-backed answer"
            evidence = [{
                "type": "provider_execution", "provider": "codex", "provider_model": "internal-test-route",
                "exit_code": 0, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "output_bytes": len(text.encode()), "completion_signal": "non_empty_assistant_output",
            }]
            return SimpleNamespace(status="completed", text=text, technical={
                "selected_provider": "codex", "attempts": [], "fallback_used": False,
                "tool_calls": [{
                    "call_id": "call-search", "provider": "codex", "tool": "search",
                    "event_type": "mcp_tool_call", "status": "succeeded", "event_sha256": "c" * 64,
                }],
                "artifact_refs": [], "evidence": evidence,
            })

    provider_gateway.configure_provider_gateway(ToolGateway())
    capabilities = client.get("/v1/capabilities?refresh=true").json()
    tools = client.get("/v1/tools?refresh=true").json()
    assert capabilities["schema_version"] == "kolibri.capabilities.v1"
    assert tools["data"][0]["id"] == "tool:search"
    assert tools["data"][0]["status"] == "available"

    unknown = client.post("/v1/responses", json={
        "idempotency_key": "unknown-tool", "input": "use it",
        "tools": [{"type": "function", "function": {"name": "not-installed"}}],
    })
    assert unknown.status_code == 422
    assert unknown.json()["detail"]["code"] == "requested_tool_not_installed"
    assert calls == []

    response = client.post("/v1/responses", json={
        "idempotency_key": "verified-tool", "model": "kolibri", "input": "search",
        "tools": [{"type": "web_search"}],
        "technical": {"provider_preferences": ["mimo", "untrusted-client-route"]},
    })
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["tools"][0]["id"] == "tool:search"
    assert payload["technical"]["provider_routing"]["selected_provider"] == "codex"
    assert payload["technical"]["provider_routing"]["verifier_evidence"]["verdict"] == "passed"
    assert calls[0]["tools"][0]["id"] == "tool:search"
    assert "untrusted-client-route" not in json.dumps(payload)
    assert client.get("/v1/models").json()["data"] == [{
        "id": "kolibri", "object": "model", "created": 0, "owned_by": "kolibri-ai-os",
    }]


def test_tool_response_fails_when_verifier_has_no_tool_call(tmp_path, monkeypatch):
    _, client = make_client(tmp_path)
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex.chmod(0o755)
    manifest = tmp_path / "kolibri-tools.json"
    manifest.write_text(json.dumps({
        "tools": [{"id": "tool:search", "name": "search", "status": "available", "providers": ["codex"]}]
    }), encoding="utf-8")
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", str(codex))
    import capability_gateway
    import provider_gateway
    capability_gateway.configure_capability_gateway(
        capability_gateway.CapabilityGateway([manifest], cache_ttl=0, include_packaged_registry=False)
    )

    class NoToolEvidenceGateway:
        def generate(self, input_value, instructions, response_id, requested_tools=None, planned_skills=None):
            del input_value, instructions, response_id, requested_tools, planned_skills
            text = "Claim without a tool event"
            return SimpleNamespace(status="completed", text=text, technical={
                "tool_calls": [],
                "evidence": [{
                    "type": "provider_execution", "provider": "codex", "provider_model": "internal-test-route",
                    "exit_code": 0, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "output_bytes": len(text.encode()), "completion_signal": "non_empty_assistant_output",
                }],
            })

    provider_gateway.configure_provider_gateway(NoToolEvidenceGateway())
    payload = client.post("/v1/responses", json={
        "idempotency_key": "missing-tool-proof", "input": "search", "tools": [{"name": "search"}],
    }).json()
    assert payload["status"] == "failed"
    assert payload["output"] == []
    verifier = payload["technical"]["provider_routing"]["verifier_evidence"]
    assert verifier["verdict"] == "failed"
    assert verifier["checks"]["requested_tools_executed"] is False


def test_response_without_client_tools_routes_installed_skill_in_prompt_layer(tmp_path, monkeypatch):
    _, client = make_client(tmp_path)
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    codex.chmod(0o755)
    skill = tmp_path / "pdf" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: pdf\ndescription: Create and inspect PDF documents with rendered verification.\n---\nbody",
        encoding="utf-8",
    )
    monkeypatch.setenv("KOLIBRI_CODEX_BIN", str(codex))
    import capability_gateway
    import provider_gateway
    capability_gateway.configure_capability_gateway(
        capability_gateway.CapabilityGateway([skill], cache_ttl=0, include_packaged_registry=False)
    )
    calls = []

    class SkillAwareGateway:
        def generate(self, input_value, instructions, response_id, requested_tools=None, planned_skills=None):
            del input_value, instructions, response_id
            calls.append({"requested_tools": requested_tools, "planned_skills": planned_skills})
            text = "PDF workflow selected"
            evidence = [{
                "type": "provider_execution", "provider": "codex", "provider_model": "internal-test-route",
                "exit_code": 0, "output_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "output_bytes": len(text.encode()), "completion_signal": "non_empty_assistant_output",
            }]
            return SimpleNamespace(status="completed", text=text, technical={
                "tool_calls": [], "evidence": evidence,
                "skill_routing": provider_gateway.skill_routing_evidence(planned_skills),
            })

    provider_gateway.configure_provider_gateway(SkillAwareGateway())
    payload = client.post("/v1/responses", json={
        "idempotency_key": "internal-pdf-skill", "input": "Use the PDF skill to inspect a document",
        "tools": [],
    }).json()
    assert payload["status"] == "completed"
    assert calls[0]["requested_tools"] == []
    assert calls[0]["planned_skills"][0]["id"] == "skill:pdf"
    routing = payload["technical"]["provider_routing"]["skill_routing"]
    assert routing["selected"][0]["id"] == "skill:pdf"
    assert routing["evidence"][0]["type"] == "skill_manifest_binding"
