"""Provider draft -> official prices -> revision -> real export contract."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import zipfile

from fastapi.testclient import TestClient
import httpx
from openpyxl import load_workbook
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import ai_provider
from app.database import Base, get_db
from app.fgiscs_client import FgisCsClient
from app.main import app
from app.pdf_generator import _build_estimate_html


PROMPT = "Составь смету на строительство одноэтажного дома 100 м², Лениногорск, Татарстан"

OFFICIAL_ROWS = [
    {
        "code": "01.2.03.03-0064",
        "name": "Мастика битумно-резиновая изоляционная МБР-75",
        "unitName": "т",
        "aggregatedPrice": "44863.00",
        "distancePrice": "671.60",
        "procureStorageCostPercent": "2.00",
        "estimatedPrice": "46445.29",
    },
    {
        "code": "03.2.01.01-0036",
        "name": "Портландцемент общестроительный ЦЕМ I 42,5Н",
        "unitName": "т",
        "aggregatedPrice": "6147.54",
        "distancePrice": "594.33",
        "procureStorageCostPercent": "2.00",
        "estimatedPrice": "6876.71",
    },
    {
        "code": "04.1.02.01-0006",
        "name": "Смеси бетонные мелкозернистого бетона (БСМ), класс В15 (М200)",
        "unitName": "м3",
        "aggregatedPrice": "5816.56",
        "distancePrice": "1038.79",
        "procureStorageCostPercent": "2.00",
        "estimatedPrice": "6992.46",
    },
    {
        "code": "06.1.01.05-0036",
        "name": (
            "Кирпич керамический рядовой полнотелый одинарный, "
            "размеры 250х120х65 мм, марка М125"
        ),
        "unitName": "1000 шт",
        "aggregatedPrice": "13934.55",
        "distancePrice": "2121.77",
        "procureStorageCostPercent": "2.00",
        "estimatedPrice": "16377.45",
    },
    {
        "code": "12.2.05.08-0015",
        "name": (
            "Плиты теплоизоляционные из минеральной ваты на основе стекловолокна, "
            "группа горючести НГ, плотность 35 кг/м3, теплопроводность при 10/25 °C "
            "не более 0,032/0,034 Вт/(м*К)"
        ),
        "unitName": "м3",
        "aggregatedPrice": "4695.33",
        "distancePrice": "50.05",
        "procureStorageCostPercent": "2.00",
        "estimatedPrice": "4840.29",
    },
]


def _json_response(payload, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers={"content-type": "application/json; charset=utf-8"},
        content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )


def _fgis_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/EstimatedPrice/CountrySubjects"):
        return _json_response([{"id": 296, "name": "Республика Татарстан (Татарстан)"}])
    if path.endswith("/EstimatedPrice/PriceZones"):
        return _json_response([{"id": 202, "name": "Республика Татарстан"}])
    if path.endswith("/EstimatedPrice/Periods"):
        return _json_response([
            {"id": 426, "name": "2 квартал 2026 г."},
            {"id": 425, "name": "1 квартал 2026 г."},
        ])
    if path.endswith("/EstimatedPrice/BuildingResources/Search/Materials"):
        assert request.url.params["periodId"] == "426"
        assert request.url.params["priceZoneId"] == "202"
        return _json_response({"items": [{"items": OFFICIAL_ROWS}]})
    if path.endswith("/EstimatedPrice/BuildingResources/Search/Machines"):
        return _json_response({"items": []})
    if path.endswith("/EstimatedPrice/RimWorkerSalaryRegistry"):
        return _json_response({"items": []})
    return _json_response({"detail": "not found"}, 404)


def _provider_action() -> dict:
    quantities = ["0.25", "12", "25", "25", "30"]
    return {
        "type": "create_estimate",
        "label": "Черновик исполнителя",
        "data": {
            "title": "Смета: Одноэтажный дом 100 м² — Лениногорск, Татарстан",
            "object_name": "Одноэтажный дом 100 м²",
            "region": "Лениногорск, Татарстан",
            "assumptions": [
                "Объёмы — черновик исполнителя и требуют проверки по рабочему проекту."
            ],
            "sections": [{
                "title": "Материалы — проверка официального ценового контура",
                "positions": [
                    {
                        "code": row["code"],
                        "name": row["name"],
                        "unit": row["unitName"],
                        "quantity": quantity,
                        # Provider price and source are deliberately false:
                        # the server must erase and replace both.
                        "price": "999999",
                        "source": "https://provider.invalid/fabricated",
                    }
                    for row, quantity in zip(OFFICIAL_ROWS, quantities, strict=True)
                ],
            }],
        },
    }


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


def test_leninogorsk_source_backed_estimate_revision_and_exports(
    client: TestClient,
    monkeypatch,
):
    monkeypatch.setenv("KOLIBRI_ESTIMATE_FGIS_ENABLED", "true")
    monkeypatch.setenv("KOLIBRI_EVIDENCE_SIGNING_KEY", "e" * 64)
    original_enrich = FgisCsClient.enrich_draft

    async def enrich_through_official_mock(self, draft, **_kwargs):
        transport = httpx.MockTransport(_fgis_handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            collector = FgisCsClient(client=http_client)
            return await original_enrich(
                collector,
                draft,
                observed_at=datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc),
            )

    monkeypatch.setattr(FgisCsClient, "enrich_draft", enrich_through_official_mock)
    actions = asyncio.run(
        ai_provider._materialize_estimate_actions(
            [{"role": "user", "content": PROMPT}],
            [_provider_action()],
        )
    )
    action_data = actions[0]["data"]

    assert action_data["estimate_status"] == "source_backed"
    assert action_data["pricing_status"] == "verified"
    assert action_data["scope_status"] == "unverified"
    assert action_data["totals"]["total"] == "823588.29"
    assert len(action_data["price_sources"]) == len(OFFICIAL_ROWS)
    assert action_data["sections"][0]["positions"][2]["unit"] == "м³"
    assert action_data["sections"][0]["positions"][4]["unit"] == "м³"
    assert all(source["price_date"] == "2026-06-30" for source in action_data["price_sources"])
    assert all("periodId=426" in source["url"] for source in action_data["price_sources"])
    assert all("provider.invalid" not in position["source"] for position in action_data["sections"][0]["positions"])

    created_response = client.post("/api/v1/estimates", json=action_data)
    assert created_response.status_code == 201, created_response.text
    assert created_response.headers["etag"] == '"1"'
    created = created_response.json()
    estimate_id = created["id"]
    assert created["estimate_status"] == "source_backed"
    assert created["pricing_status"] == "verified"
    assert created["scope_status"] == "unverified"
    assert created["total"] == "823588.29"
    assert len(created["price_sources"]) == len(OFFICIAL_ROWS)

    changed_sections = deepcopy(created["sections"])
    changed_sections[0]["positions"][3]["quantity"] = "26"
    updated_response = client.put(
        f"/api/v1/estimates/{estimate_id}",
        headers={"If-Match": '"1"'},
        json={
            "sections": changed_sections,
            "price_sources": created["price_sources"],
        },
    )
    assert updated_response.status_code == 200, updated_response.text
    assert updated_response.headers["etag"] == '"2"'
    updated = updated_response.json()
    assert updated["total"] == "839965.74"
    assert updated["estimate_status"] == "source_backed"

    first_revision = client.get(
        f"/api/v1/estimates/{estimate_id}/revisions/1"
    ).json()["snapshot"]
    second_revision = client.get(
        f"/api/v1/estimates/{estimate_id}/revisions/2"
    ).json()["snapshot"]
    assert first_revision["total"] == "823588.29"
    assert second_revision["total"] == "839965.74"
    assert first_revision["sections"][0]["positions"][3]["quantity"] == "25"
    assert second_revision["sections"][0]["positions"][3]["quantity"] == "26"
    export_html = _build_estimate_html(second_revision)
    assert ">ФГИС ЦС — сметные цены строительных ресурсов," in export_html
    assert " · 2026-06-30</a>" in export_html

    pdf = client.get(f"/api/v1/estimates/{estimate_id}/pdf?version=2")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["etag"] == '"2"'
    assert pdf.content.startswith(b"%PDF-")
    assert len(pdf.content) > 5_000

    xlsx = client.get(f"/api/v1/estimates/{estimate_id}/export/xlsx?version=2")
    assert xlsx.status_code == 200
    assert xlsx.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert xlsx.headers["etag"] == '"2"'
    assert xlsx.content.startswith(b"PK\x03\x04")
    with zipfile.ZipFile(io.BytesIO(xlsx.content)) as archive:
        assert archive.testzip() is None
    workbook = load_workbook(io.BytesIO(xlsx.content), data_only=False, read_only=False)
    worksheet = workbook["Смета"]
    assert worksheet["A1"].value == action_data["title"]
    assert worksheet["F11"].value == "=ROUND(D11*E11,2)"
    assert worksheet["F15"].value == "=ROUND(D15*E15,2)"
    assert worksheet["F16"].value == "=ROUND(SUM(F11:F15),2)"
    workbook.close()

    # Reopening the saved revision and regenerating its exports must not read
    # mutable current-estimate data.
    assert client.get(f"/api/v1/estimates/{estimate_id}").json()["version"] == 2
    assert client.get(f"/api/v1/estimates/{estimate_id}/export/json?version=1").json()["total"] == "823588.29"
