from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from product_capabilities import (  # noqa: E402
    build_product_capability_matrix,
    public_capability_projection,
    requested_materialized_capability,
    verified_provider_health,
)


CAPABILITY_ENVELOPE = {
    "data": [{
        "id": "tool:web_search",
        "kind": "tool",
        "status": "available",
        "invocable": True,
    }],
}
ROUTES = [("POST", "/v1/responses")]


def record(matrix, capability_id):
    return next(item for item in matrix["data"] if item["id"] == capability_id)


def test_product_capability_requires_route_provider_tool_and_renderer():
    matrix = build_product_capability_matrix(
        routes=ROUTES,
        capability_envelope=CAPABILITY_ENVELOPE,
        provider_health={"general": True, "code": True, "image_generation": False},
    )

    estimate = record(matrix, "estimate")
    assert estimate["available"] is True
    assert estimate["gates"] == {
        "invocable": True,
        "route_healthy": True,
        "renderer_ready": True,
        "required_tools_ready": True,
    }

    no_provider = build_product_capability_matrix(
        routes=ROUTES,
        capability_envelope=CAPABILITY_ENVELOPE,
        provider_health={"general": False},
    )
    assert record(no_provider, "estimate")["available"] is False
    assert "provider_health_unverified" in record(no_provider, "estimate")["reason_codes"]

    no_tool = build_product_capability_matrix(
        routes=ROUTES,
        capability_envelope={"data": []},
        provider_health={"general": True},
    )
    assert record(no_tool, "estimate")["available"] is False
    assert "required_tool_unavailable" in record(no_tool, "estimate")["reason_codes"]

    no_route = build_product_capability_matrix(
        routes=[],
        capability_envelope=CAPABILITY_ENVELOPE,
        provider_health={"general": True},
    )
    assert record(no_route, "estimate")["available"] is False
    assert "backend_route_missing" in record(no_route, "estimate")["reason_codes"]


def test_image_is_exposed_only_with_healthy_route_tool_and_renderer():
    matrix = build_product_capability_matrix(
        routes=ROUTES,
        capability_envelope={
            "data": [
                *CAPABILITY_ENVELOPE["data"],
                {
                    "id": "tool:image_generation",
                    "kind": "tool",
                    "status": "available",
                    "invocable": True,
                },
            ],
        },
        provider_health={"general": True, "code": True, "image_generation": True},
    )

    assert record(matrix, "image")["available"] is True
    assert record(matrix, "document")["available"] is False
    assert record(matrix, "spreadsheet")["available"] is False
    assert record(matrix, "site")["available"] is False
    assert record(matrix, "app")["available"] is False


def test_public_projection_exposes_available_records_without_operator_reasons():
    matrix = build_product_capability_matrix(
        routes=ROUTES,
        capability_envelope=CAPABILITY_ENVELOPE,
        provider_health={"general": True, "code": True},
    )
    public = public_capability_projection(matrix)

    public_ids = {item["id"] for item in public["data"]}
    assert "estimate" in public_ids
    assert "image" not in public_ids
    assert all("gates" not in item for item in public["data"])
    assert all("reason_codes" not in item for item in public["data"])
    assert all("evidence" not in item for item in public["data"])


def test_provider_binary_or_endpoint_is_not_health_evidence():
    configured_only = SimpleNamespace(available=lambda: {"factory": True})
    assert verified_provider_health(configured_only)["general"] is False

    verified = SimpleNamespace(
        verified_product_health=lambda: {
            "general": True,
            "code": True,
            "image_generation": False,
            "private_debug": True,
        },
    )
    assert verified_provider_health(verified) == {
        "general": True,
        "code": True,
        "image_generation": False,
    }


def test_explicit_image_creation_is_materialized_capability_request():
    assert requested_materialized_capability("Нарисуй картинку колибри") == "image"
    assert requested_materialized_capability("Generate an image of a house") == "image"
    assert requested_materialized_capability("Создай кинематографичный портрет султана") == "image"
    assert requested_materialized_capability("Сделай фото дома") == "image"
    assert requested_materialized_capability("Объясни, как устроено изображение") is None
    assert requested_materialized_capability("Напиши статью про генерацию изображений") is None
    assert requested_materialized_capability("Создай промпт для изображения дома") is None
    assert requested_materialized_capability([
        {"role": "user", "content": "Нарисуй изображение птицы"},
        {"role": "assistant", "content": "Уточните стиль"},
        {"role": "user", "content": "как дела"},
    ]) is None
    assert requested_materialized_capability([
        {"role": "user", "content": "Нарисуй изображение птицы"},
        {"role": "assistant", "content": "Уточните стиль"},
        {"role": "user", "content": "хорошо, давай"},
    ]) is None


def test_public_http_projection_hides_reasons_and_control_requires_owner(monkeypatch):
    import execution_api
    import main

    class CapabilityGateway:
        @staticmethod
        def envelope():
            return CAPABILITY_ENVELOPE

    gateway = SimpleNamespace(
        verified_product_health=lambda: {
            "general": True,
            "code": True,
            "image_generation": False,
        },
    )
    monkeypatch.setattr(main, "get_capability_gateway", lambda: CapabilityGateway())
    monkeypatch.setattr(main, "get_provider_gateway", lambda: gateway)
    execution_api.configure_execution_auth(["product-capabilities-owner"])
    client = TestClient(main.app)

    public = client.get("/v1/capabilities")
    assert public.status_code == 200
    assert "estimate" in {item["id"] for item in public.json()["data"]}
    assert all("reason_codes" not in item for item in public.json()["data"])
    assert "image" not in {item["id"] for item in public.json()["data"]}

    assert client.get("/v1/runtime/product-capabilities").status_code == 401
    control = client.get(
        "/v1/runtime/product-capabilities",
        headers={"Authorization": "Bearer product-capabilities-owner"},
    )
    assert control.status_code == 200
    image = record(control.json(), "image")
    assert image["available"] is False
    assert image["reason_codes"]
    assert image["gates"]["renderer_ready"] is True
    assert image["gates"]["route_healthy"] is False
