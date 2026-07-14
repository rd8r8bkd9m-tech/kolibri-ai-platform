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
    "/api/v1/cluster/stats",
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


@pytest.mark.parametrize("role", ("owner", "admin", "superadmin"))
def test_all_operator_roles_are_allowed(operator_client: TestClient, role: str):
    response = operator_client.get("/api/v1/cluster/stats", headers=operator_client.auth_for(role))
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"


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
