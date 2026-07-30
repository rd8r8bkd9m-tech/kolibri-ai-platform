import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def browsers():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as owner, TestClient(app) as foreign:
        assert owner.post("/api/v1/shell/bootstrap").status_code == 200
        assert foreign.post("/api/v1/shell/bootstrap").status_code == 200
        yield owner, foreign
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def estimate_payload(
    *,
    client: str = "ООО «Ромашка»",
    object_name: str = "Жилой дом 123 м²",
    region: str = "Татарстан",
) -> dict:
    return {
        "title": "Смета на строительство дома",
        "client": client,
        "object_name": object_name,
        "region": region,
        "sections": [
            {
                "title": "Работы",
                "positions": [
                    {
                        "code": "W-1",
                        "name": "Подготовительные работы",
                        "unit": "компл.",
                        "quantity": "1",
                        "price": "1000",
                    }
                ],
            }
        ],
    }


def test_estimate_create_and_update_upsert_tenant_directory(browsers):
    owner, _foreign = browsers

    first_response = owner.post("/api/v1/estimates", json=estimate_payload())
    assert first_response.status_code == 201, first_response.text
    first = first_response.json()
    assert first["client_record_id"]
    assert first["object_record_id"]

    # Formatting differences resolve to the same tenant-scoped records.
    second_response = owner.post(
        "/api/v1/estimates",
        json=estimate_payload(client=" ооо ромашка ", object_name="Жилой дом 123 м² "),
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()
    assert second["client_record_id"] == first["client_record_id"]
    assert second["object_record_id"] == first["object_record_id"]

    clients = owner.get("/api/v1/clients")
    assert clients.status_code == 200, clients.text
    assert clients.json()["total"] == 1
    assert clients.json()["items"][0]["name"] == "ооо ромашка"

    objects = owner.get("/api/v1/construction-objects?search=123")
    assert objects.status_code == 200, objects.text
    assert objects.json()["total"] == 1
    assert objects.json()["items"][0]["client_id"] == first["client_record_id"]
    assert objects.json()["items"][0]["region"] == "Татарстан"

    changed_response = owner.put(
        f"/api/v1/estimates/{first['id']}",
        headers={"If-Match": '"1"'},
        json={
            "client": "ИП Иванов",
            "object_name": "Склад готовой продукции",
            "region": "Казань",
        },
    )
    assert changed_response.status_code == 200, changed_response.text
    changed = changed_response.json()
    assert changed["client_record_id"] != first["client_record_id"]
    assert changed["object_record_id"] != first["object_record_id"]
    assert owner.get("/api/v1/clients?page_size=1").json()["total"] == 2
    assert owner.get("/api/v1/construction-objects?page_size=1").json()["total"] == 2

    cleared_response = owner.put(
        f"/api/v1/estimates/{first['id']}",
        headers={"If-Match": '"2"'},
        json={"client": "", "object_name": ""},
    )
    assert cleared_response.status_code == 200, cleared_response.text
    cleared = cleared_response.json()
    assert cleared["client_record_id"] is None
    assert cleared["object_record_id"] is None
    # Empty names unlink the estimate but never create blank directory rows.
    assert owner.get("/api/v1/clients").json()["total"] == 2
    assert owner.get("/api/v1/construction-objects").json()["total"] == 2


def test_client_and_object_lists_are_isolated_by_browser_scope(browsers):
    owner, foreign = browsers
    created = owner.post("/api/v1/estimates", json=estimate_payload()).json()

    assert owner.get("/api/v1/clients").json()["total"] == 1
    assert owner.get("/api/v1/construction-objects").json()["total"] == 1
    assert foreign.get("/api/v1/clients").json()["total"] == 0
    assert foreign.get("/api/v1/construction-objects").json()["total"] == 0
    assert foreign.get(f"/api/v1/estimates/{created['id']}").status_code == 404

    foreign_created = foreign.post(
        "/api/v1/estimates",
        json=estimate_payload(),
    )
    assert foreign_created.status_code == 201, foreign_created.text
    assert foreign_created.json()["client_record_id"] != created["client_record_id"]
    assert foreign_created.json()["object_record_id"] != created["object_record_id"]
    assert foreign.get("/api/v1/clients").json()["total"] == 1
    assert foreign.get("/api/v1/construction-objects").json()["total"] == 1
