import io
import zipfile

import pytest
from openpyxl import load_workbook
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


@pytest.fixture()
def client():
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
    with TestClient(app) as test_client:
        bootstrap = test_client.post("/api/v1/shell/bootstrap")
        assert bootstrap.status_code == 200, bootstrap.text
        yield test_client
    app.dependency_overrides.pop(get_db, None)
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def estimate_payload(quantity: str = "2.5") -> dict:
    return {
        "title": "Смета на отделочные работы",
        "client": "ООО Заказчик",
        "object_name": "Дом 100 м²",
        "region": "Татарстан",
        "currency": "RUB",
        "overhead_rate": "10",
        "vat_rate": "22",
        "sections": [
            {
                "title": "Работы",
                "positions": [
                    {
                        "code": "W-001",
                        "name": "Подготовка стен",
                        "unit": "м²",
                        "quantity": quantity,
                        "price": "100",
                        "source": "Прайс 2026",
                        "comment": "",
                    }
                ],
            }
        ],
    }


def test_estimate_save_recalc_reload_and_immutable_revisions(client: TestClient):
    created_response = client.post("/api/v1/estimates", json=estimate_payload())
    assert created_response.status_code == 201
    assert created_response.headers["etag"] == '"1"'
    created = created_response.json()
    estimate_id = created["id"]
    assert created["version"] == 1
    assert created["subtotal"] == "250.00"
    assert created["overhead_amount"] == "25.00"
    assert created["vat_amount"] == "60.50"
    assert created["total"] == "335.50"
    assert created["sections"][0]["positions"][0]["sum"] == "250.00"

    revisions = client.get(f"/api/v1/estimates/{estimate_id}/revisions")
    assert revisions.status_code == 200
    assert revisions.json()["total"] == 1
    assert [item["version"] for item in revisions.json()["items"]] == [1]

    missing_precondition = client.put(
        f"/api/v1/estimates/{estimate_id}",
        json={"title": "Blind overwrite"},
    )
    assert missing_precondition.status_code == 428
    assert missing_precondition.json()["detail"]["code"] == "estimate_version_required"

    updated_response = client.put(
        f"/api/v1/estimates/{estimate_id}",
        json={"version": 1, "sections": estimate_payload("3")["sections"]},
    )
    assert updated_response.status_code == 200
    assert updated_response.headers["etag"] == '"2"'
    updated = updated_response.json()
    assert updated["version"] == 2
    assert updated["subtotal"] == "300.00"
    assert updated["overhead_amount"] == "30.00"
    assert updated["vat_amount"] == "72.60"
    assert updated["total"] == "402.60"

    stale = client.put(
        f"/api/v1/estimates/{estimate_id}",
        headers={"If-Match": '"1"'},
        json={"title": "Stale title"},
    )
    assert stale.status_code == 409
    assert stale.headers["etag"] == '"2"'
    assert stale.json()["detail"] == {
        "code": "estimate_version_conflict",
        "message": "Estimate was changed by another save; reload before retrying",
        "expected_version": 1,
        "current_version": 2,
    }

    reloaded = client.get(f"/api/v1/estimates/{estimate_id}")
    assert reloaded.status_code == 200
    assert reloaded.headers["etag"] == '"2"'
    assert reloaded.json() == updated

    missing_recalc_precondition = client.post(
        f"/api/v1/estimates/{estimate_id}/calculate"
    )
    assert missing_recalc_precondition.status_code == 428

    recalculated_response = client.post(
        f"/api/v1/estimates/{estimate_id}/calculate",
        headers={"If-Match": 'W/"2"'},
    )
    assert recalculated_response.status_code == 200
    assert recalculated_response.headers["etag"] == '"3"'
    recalculated = recalculated_response.json()
    assert recalculated["version"] == 3
    assert recalculated["total"] == updated["total"]
    assert recalculated["sections"] == updated["sections"]

    revisions = client.get(f"/api/v1/estimates/{estimate_id}/revisions").json()
    assert revisions["total"] == 3
    assert [item["version"] for item in revisions["items"]] == [3, 2, 1]

    first_revision = client.get(
        f"/api/v1/estimates/{estimate_id}/revisions/1"
    )
    assert first_revision.status_code == 200
    assert first_revision.headers["etag"] == '"1"'
    first_snapshot = first_revision.json()["snapshot"]
    assert first_snapshot["version"] == 1
    assert first_snapshot["total"] == "335.50"
    assert first_snapshot["sections"][0]["positions"][0]["quantity"] == "2.5"

    second_revision = client.get(
        f"/api/v1/estimates/{estimate_id}/revisions/2"
    ).json()["snapshot"]
    assert second_revision["version"] == 2
    assert second_revision["total"] == "402.60"
    assert second_revision["sections"][0]["positions"][0]["quantity"] == "3"


def test_revision_backed_pdf_xlsx_and_json_exports(client: TestClient):
    created = client.post("/api/v1/estimates", json=estimate_payload()).json()
    estimate_id = created["id"]
    updated = client.put(
        f"/api/v1/estimates/{estimate_id}",
        headers={"If-Match": '"1"'},
        json={"sections": estimate_payload("3")["sections"]},
    ).json()
    assert updated["version"] == 2

    pdf = client.get(f"/api/v1/estimates/{estimate_id}/pdf?version=1")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["etag"] == '"1"'
    assert pdf.content.startswith(b"%PDF-")
    assert len(pdf.content) > 1_000

    xlsx = client.get(f"/api/v1/estimates/{estimate_id}/export/xlsx?version=2")
    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert xlsx.headers["etag"] == '"2"'
    assert xlsx.content.startswith(b"PK\x03\x04")
    assert len(xlsx.content) > 1_000
    with zipfile.ZipFile(io.BytesIO(xlsx.content)) as archive:
        assert archive.testzip() is None
        assert "[Content_Types].xml" in archive.namelist()
        assert "xl/workbook.xml" in archive.namelist()
        assert "xl/worksheets/sheet1.xml" in archive.namelist()
    workbook = load_workbook(io.BytesIO(xlsx.content), read_only=False)
    worksheet = workbook["Смета"]
    assert worksheet["F11"].data_type == "f"
    assert worksheet["F11"].value == "=ROUND(D11*E11,2)"
    assert worksheet["B11"].alignment.wrap_text is True
    assert worksheet.row_dimensions[11].height >= 18
    assert worksheet.column_dimensions["B"].width >= 48
    assert worksheet.column_dimensions["E"].width >= 30
    assert worksheet.column_dimensions["F"].width >= 19
    assert worksheet.page_setup.fitToHeight == 0
    assert workbook.calculation.calcMode == "auto"
    workbook.close()

    first_json = client.get(
        f"/api/v1/estimates/{estimate_id}/export/json?version=1"
    )
    assert first_json.status_code == 200
    assert first_json.headers["content-type"] == "application/json"
    assert first_json.headers["etag"] == '"1"'
    assert first_json.json()["version"] == 1
    assert first_json.json()["total"] == "335.50"
    assert first_json.json()["sections"][0]["positions"][0]["quantity"] == "2.5"

    latest_json = client.get(f"/api/v1/estimates/{estimate_id}/export/json")
    assert latest_json.status_code == 200
    assert latest_json.headers["etag"] == '"2"'
    assert latest_json.json()["version"] == 2
    assert latest_json.json()["total"] == "402.60"
