import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import create_access_token
from app.control_plane import ControlPlaneUnavailable, HomeControlPlaneAdapter
from app.database import Base, get_db
from app.main import app
from app.models import UserDB


class _FakeControlPlane:
    last_envelope = None

    async def list_agents(self, **_kwargs):
        return {"items": [], "total": 0, "page": 1, "page_size": 20, "truth": {"availability": "live"}}

    async def get_agent(self, agent_id: str):
        return {"id": agent_id, "name": "Agent Host", "role": "agent_host", "status": "idle"}

    async def list_nodes(self, **_kwargs):
        return {"items": [], "total": 0, "page": 1, "page_size": 50, "truth": {"availability": "live"}}

    async def list_tasks(self, **_kwargs):
        return {
            "items": [{
                "id": "task-1",
                "workflow_id": "Safe title",
                "state": "running",
                "priority": 1,
                "owner_agent_id": "worker",
                "node_id": "node-1",
                "budget_limit": None,
                "attempts": 1,
                "max_retries": 2,
                "result": {"private": "must-not-leak", "_truth": {"result_reference": "/private/result"}},
                "created_at": "2026-07-14T00:00:00Z",
                "updated_at": "2026-07-14T00:00:00Z",
            }],
            "total": 1,
            "page": 1,
            "page_size": 20,
            "truth": {"availability": "live", "source": "home_control_plane", "internal": "must-not-leak"},
        }

    async def cluster_stats(self):
        return {
            "nodes": {
                "membership_total": 21,
                "connected": 20,
                "fresh": 19,
                "capability_executable": 17,
                "active": 4,
                "verified": 15,
                "blocked": 2,
                "quarantined": 1,
                "stale": 2,
            },
            "agents": {
                "membership_total": 21,
                "active": 4,
                "idle": 16,
                "paused": 1,
                "executable": 17,
                "verified": 15,
            },
            "tasks": {"total": 0, "running": 0, "queued": 0, "completed": 0, "failed": 0, "cancelled": 0},
            "resources": {"avg_cpu": None, "avg_ram": None, "avg_disk": None},
            "truth": {
                "availability": "live",
                "source": "home_control_plane",
                "as_of": "2026-07-14T00:00:00Z",
                "task_pages": 1,
                "membership": {"canonical_total": 21, "mesh": "must-not-leak"},
                "verification": {
                    "availability": "live",
                    "as_of": "2026-07-14T00:00:00Z",
                    "status": "incomplete",
                    "summary": {"must_not_leak": True},
                },
            },
        }

    async def task_summary(self):
        return {
            "total": 1, "queued": 0, "running": 1, "waiting_review": 0,
            "completed": 0, "failed": 0, "cancelled": 0, "dead_letter": 0,
            "as_of": "2026-07-16T08:00:00Z", "source": "home_control_plane",
        }

    async def provider_routes(self):
        return {
            "public_model": "kolibri",
            "routes": [],
            "routing_status": "unavailable",
            "as_of": "2026-07-16T08:00:00Z",
            "source": "home_control_plane",
        }

    async def local_model_admission(self):
        return {
            "items": [], "admitted_total": 0, "candidate_total": 0,
            "as_of": "2026-07-16T08:00:00Z",
            "generation_id": "generation-test",
            "index_sha256": "sha256:" + "a" * 64,
            "source": "home_control_plane",
        }

    async def formulalm_admission(self):
        return {
            "status": "ready", "mode": "candidate_only", "candidate_only": True,
            "active_model": None, "candidate_model": None, "gates": [],
            "candidates": [], "as_of": "2026-07-16T08:00:00Z",
            "generation_id": "generation-test",
            "index_sha256": "sha256:" + "a" * 64,
            "source": "home_control_plane",
        }

    async def list_events(self, **_kwargs):
        return {
            "items": [], "total": 0, "next_cursor": None,
            "as_of": "2026-07-16T08:00:00Z", "source": "home_control_plane",
        }

    async def submit_owner_task(self, envelope):
        type(self).last_envelope = envelope
        return {
            "id": envelope["task_id"],
            "workflow_id": envelope["kind"],
            "state": "queued",
            "priority": 1,
            "owner_agent_id": None,
            "node_id": None,
            "budget_limit": None,
            "attempts": 0,
            "max_retries": 0,
            "created_at": "2026-07-16T08:00:00Z",
            "updated_at": "2026-07-16T08:00:00Z",
        }

    async def get_task_detail(self, task_id):
        return {
            "id": task_id,
            "workflow_id": "Safe title",
            "state": "running",
            "priority": 1,
            "owner_agent_id": "agent",
            "node_id": "home",
            "budget_limit": None,
            "attempts": 1,
            "max_retries": 0,
            "created_at": "2026-07-16T08:00:00Z",
            "updated_at": "2026-07-16T08:00:01Z",
            "kind": "owner_remote_task",
            "objective": "Safe title",
            "runner": "codex",
            "required_capability": "runner:codex",
            "attempt_id": "attempt-1",
            "fencing_token": 1,
            "result_reference": None,
            "verification": {
                "verdict": None, "failed_checks": [],
                "result_sha256": None, "binding_sha256": None,
            },
        }

    async def list_task_events(self, task_id, **_kwargs):
        return {
            "items": [], "total": 0, "next_sequence": 0,
            "as_of": "2026-07-16T08:00:01Z", "source": "home_control_plane",
        }

    async def cancel_task(self, task_id, *, reason):
        return {
            "id": task_id,
            "workflow_id": "owner_remote_task",
            "state": "cancelled",
            "priority": 1,
            "owner_agent_id": None,
            "node_id": None,
            "budget_limit": None,
            "attempts": 0,
            "max_retries": 0,
            "created_at": "2026-07-16T08:00:00Z",
            "updated_at": "2026-07-16T08:00:01Z",
        }


@pytest.fixture()
def operator_client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with testing_session() as db:
            yield db

    with testing_session() as db:
        for role in ("user", "owner", "admin", "superadmin"):
            db.add(UserDB(
                id=f"user-{role}",
                email=f"{role}@example.test",
                name=role,
                hashed_password="not-used",
                role=role,
                is_active=True,
            ))
        db.add(UserDB(
            id="user-inactive-owner",
            email="inactive-owner@example.test",
            name="inactive owner",
            hashed_password="not-used",
            role="owner",
            is_active=False,
        ))
        db.commit()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(HomeControlPlaneAdapter, "from_environment", staticmethod(lambda: _FakeControlPlane()))
    with TestClient(app) as client:
        client.auth_for = lambda role: {
            "Authorization": f"Bearer {create_access_token({'sub': f'user-{role}'})}"
        }
        yield client
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


OPERATOR_READ_ROUTES = (
    "/api/v1/agents",
    "/api/v1/agents/agent-1",
    "/api/v1/nodes",
    "/api/v1/tasks",
    "/api/v1/tasks/task-1",
    "/api/v1/tasks/task-1/events",
    "/api/v1/cluster/stats",
    "/api/v1/control/tasks/summary",
    "/api/v1/control/events",
    "/api/v1/control/models",
    "/api/v1/control/local-models",
    "/api/v1/control/learning",
    "/api/v1/analytics",
    "/api/v1/providers",
    "/api/v1/providers/codex_cli",
)


@pytest.mark.parametrize("path", OPERATOR_READ_ROUTES)
def test_operator_reads_require_bearer_and_owner_role(operator_client: TestClient, path: str):
    anonymous = operator_client.get(path)
    assert anonymous.status_code == 401
    assert anonymous.headers["Cache-Control"] == "private, no-store"

    non_owner = operator_client.get(path, headers=operator_client.auth_for("user"))
    assert non_owner.status_code == 403
    assert non_owner.headers["Cache-Control"] == "private, no-store"

    owner = operator_client.get(path, headers=operator_client.auth_for("owner"))
    assert owner.status_code == 200, owner.text
    assert owner.headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize("role", ("owner", "superadmin"))
def test_all_operator_roles_are_allowed(operator_client: TestClient, role: str):
    response = operator_client.get("/api/v1/cluster/stats", headers=operator_client.auth_for(role))
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"


def test_company_admin_is_not_a_platform_factory_owner(operator_client: TestClient):
    response = operator_client.get(
        "/api/v1/control/models",
        headers=operator_client.auth_for("admin"),
    )
    assert response.status_code == 403


def test_platform_owner_cookie_auth_is_http_only_session_compatible(operator_client: TestClient):
    token = create_access_token({"sub": "user-owner"})
    operator_client.cookies.set("kolibri_auth", token)
    response = operator_client.get("/api/v1/control/models")
    assert response.status_code == 200
    operator_client.cookies.clear()


def test_inactive_owner_is_forbidden(operator_client: TestClient):
    response = operator_client.get(
        "/api/v1/cluster/stats",
        headers=operator_client.auth_for("inactive-owner"),
    )
    assert response.status_code == 403
    assert response.headers["Cache-Control"] == "private, no-store"


def test_operator_portal_drops_internal_task_results_and_membership(operator_client: TestClient):
    headers = operator_client.auth_for("owner")
    task_response = operator_client.get("/api/v1/tasks", headers=headers)
    assert task_response.status_code == 200
    assert "result" not in task_response.json()["items"][0]
    assert "internal" not in task_response.json()["truth"]

    cluster_response = operator_client.get("/api/v1/cluster/stats", headers=headers)
    assert cluster_response.status_code == 200
    cluster_payload = cluster_response.json()
    assert "membership" not in cluster_payload["truth"]
    assert "healthy" not in cluster_payload["nodes"]
    assert cluster_payload["nodes"]["membership_total"] == 21
    assert cluster_payload["nodes"]["verified"] == 15
    assert "summary" not in cluster_payload["truth"]["verification"]


def test_owner_can_submit_one_policy_bound_factory_task(operator_client: TestClient):
    headers = {
        **operator_client.auth_for("owner"),
        "Idempotency-Key": "portal-test-0001",
    }
    response = operator_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"objective": "Проверь экспорт сметы и приложи доказательства тестов"},
    )

    assert response.status_code == 201, response.text
    envelope = _FakeControlPlane.last_envelope
    assert envelope["kind"] == "orchestrator_chat_response"
    assert envelope["runner"] == "codex"
    assert envelope["required_capability"] == "runner:codex"
    assert envelope["max_attempts"] == 1
    assert len(envelope["request_sha256"]) == 64
    assert envelope["source"]["kind"] == "kolibri_provider_gateway"
    assert "email" not in envelope["source"]


@pytest.mark.parametrize(
    "method,path,payload,owner_status,extra_headers",
    [
        ("POST", "/api/v1/agents", {}, 405, {}),
        ("DELETE", "/api/v1/agents/agent-1", None, 405, {}),
        ("PATCH", "/api/v1/agents/agent-1", {}, 405, {}),
        ("PATCH", "/api/v1/nodes/node-1", {}, 405, {}),
        ("PATCH", "/api/v1/tasks/task-1", {}, 405, {}),
        ("POST", "/api/v1/tasks/task-1/cancel", {"reason": "owner requested"}, 200, {}),
        (
            "POST",
            "/api/v1/tasks",
            {"objective": "Проверить полный auth-before-handler inventory"},
            201,
            {"Idempotency-Key": "operator-inventory-0001"},
        ),
    ],
)
def test_all_operator_mutations_authenticate_before_handler(
    operator_client: TestClient,
    method: str,
    path: str,
    payload,
    owner_status: int,
    extra_headers: dict,
):
    anonymous = operator_client.request(method, path, json=payload, headers=extra_headers)
    non_owner = operator_client.request(
        method,
        path,
        json=payload,
        headers={**extra_headers, **operator_client.auth_for("user")},
    )
    owner = operator_client.request(
        method,
        path,
        json=payload,
        headers={**extra_headers, **operator_client.auth_for("owner")},
    )

    assert anonymous.status_code == 401
    assert non_owner.status_code == 403
    assert owner.status_code == owner_status, owner.text
    assert anonymous.headers["Cache-Control"] == "private, no-store"
    assert non_owner.headers["Cache-Control"] == "private, no-store"
    assert owner.headers["Cache-Control"] == "private, no-store"


def test_cookie_factory_mutations_require_exact_same_origin(operator_client: TestClient):
    token = create_access_token({"sub": "user-owner"})
    operator_client.cookies.set("kolibri_auth", token)
    operator_client.headers.pop("sec-fetch-site", None)
    headers = {"Idempotency-Key": "portal-cookie-csrf-0001"}

    missing_origin = operator_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"objective": "Проверить безопасную cookie-сессию"},
    )
    cross_origin = operator_client.post(
        "/api/v1/tasks",
        headers={**headers, "Origin": "https://evil.example"},
        json={"objective": "Проверить безопасную cookie-сессию"},
    )
    spoofed_authorization = operator_client.post(
        "/api/v1/tasks",
        headers={
            **headers,
            "Origin": "https://www.kolibriai.ru",
            "Authorization": "Basic not-a-bearer-token",
        },
        json={"objective": "Проверить безопасную cookie-сессию"},
    )
    same_origin = operator_client.post(
        "/api/v1/tasks",
        headers={**headers, "Origin": "http://testserver"},
        json={"objective": "Проверить безопасную cookie-сессию"},
    )
    cancel_cross_origin = operator_client.post(
        "/api/v1/tasks/task-1/cancel",
        headers={"Origin": "https://evil.example"},
        json={"reason": "csrf attempt"},
    )
    cancel_same_origin = operator_client.post(
        "/api/v1/tasks/task-1/cancel",
        headers={"Origin": "http://testserver"},
        json={"reason": "owner requested"},
    )

    assert missing_origin.status_code == 403
    assert missing_origin.json()["error"]["code"] == "csrf_origin_forbidden"
    assert cross_origin.status_code == 403
    assert spoofed_authorization.status_code == 403
    assert same_origin.status_code == 201
    assert cancel_cross_origin.status_code == 403
    assert cancel_same_origin.status_code == 200
    operator_client.cookies.clear()


def test_portal_task_idempotency_replays_and_conflicts_on_changed_objective(
    operator_client: TestClient,
    monkeypatch,
):
    class _ConflictAwareControlPlane(_FakeControlPlane):
        claims: dict[str, tuple[str, dict]] = {}

        async def submit_owner_task(self, envelope):
            key = envelope["idempotency_key"]
            digest = envelope["request_sha256"]
            existing = type(self).claims.get(key)
            if existing and existing[0] != digest:
                raise ControlPlaneUnavailable("control_plane_conflict")
            if existing:
                return existing[1]
            created = await super().submit_owner_task(envelope)
            type(self).claims[key] = (digest, created)
            return created

    _ConflictAwareControlPlane.claims = {}
    monkeypatch.setattr(
        HomeControlPlaneAdapter,
        "from_environment",
        staticmethod(lambda: _ConflictAwareControlPlane()),
    )
    headers = {
        **operator_client.auth_for("owner"),
        "Idempotency-Key": "portal-contract-0001",
    }

    first = operator_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"objective": "Проверить экспорт сметы"},
    )
    replay = operator_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"objective": "Проверить экспорт сметы"},
    )
    conflict = operator_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"objective": "Удалить экспорт сметы"},
    )

    assert first.status_code == 201
    assert replay.status_code == 201
    assert replay.json()["id"] == first.json()["id"]
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["reason"] == "control_plane_conflict"


def test_factory_task_mutations_require_owner_role(operator_client: TestClient):
    headers = {
        **operator_client.auth_for("user"),
        "Idempotency-Key": "portal-test-0002",
    }
    submit = operator_client.post(
        "/api/v1/tasks",
        headers=headers,
        json={"objective": "test"},
    )
    cancel = operator_client.post(
        "/api/v1/tasks/task-1/cancel",
        headers=operator_client.auth_for("user"),
        json={"reason": "test"},
    )

    assert submit.status_code == 403
    assert cancel.status_code == 403


def test_operator_upstream_errors_are_not_shared_cacheable(operator_client: TestClient, monkeypatch):
    class _UnavailableControlPlane:
        async def list_nodes(self, **_kwargs):
            raise ControlPlaneUnavailable("test_unavailable")

    monkeypatch.setattr(
        HomeControlPlaneAdapter,
        "from_environment",
        staticmethod(lambda: _UnavailableControlPlane()),
    )
    response = operator_client.get(
        "/api/v1/nodes",
        headers=operator_client.auth_for("owner"),
    )
    assert response.status_code == 503
    assert response.headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize(
    ("path", "method"),
    (
        ("/api/v1/providers/codex_cli/healthcheck", "post"),
        ("/api/v1/providers/test-all", "post"),
    ),
)
def test_provider_probes_require_owner_before_using_server_credentials(
    operator_client: TestClient,
    monkeypatch,
    path: str,
    method: str,
):
    calls: list[str] = []

    async def fake_probe(provider_id: str):
        calls.append(provider_id)
        return {"provider": provider_id, "status": "live"}

    monkeypatch.setattr("app.healthcheck.probe_provider", fake_probe)

    anonymous = operator_client.request(method, path)
    assert anonymous.status_code == 401
    assert anonymous.headers["Cache-Control"] == "private, no-store"
    assert calls == []

    non_owner = operator_client.request(
        method,
        path,
        headers=operator_client.auth_for("user"),
    )
    assert non_owner.status_code == 403
    assert non_owner.headers["Cache-Control"] == "private, no-store"
    assert calls == []

    owner = operator_client.request(
        method,
        path,
        headers=operator_client.auth_for("owner"),
    )
    assert owner.status_code == 200, owner.text
    assert owner.headers["Cache-Control"] == "private, no-store"
    assert calls
