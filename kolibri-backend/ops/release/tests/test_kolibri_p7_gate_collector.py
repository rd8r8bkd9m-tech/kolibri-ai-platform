from __future__ import annotations

import importlib.util
from io import BytesIO
import json
from pathlib import Path
import socket
import struct
import sys
from threading import Thread
import time
import uuid
import zipfile
import zlib

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
import pytest
import uvicorn


SCRIPT = Path(__file__).parents[1] / "kolibri_p7_gate_collector.py"
SPEC = importlib.util.spec_from_file_location("kolibri_p7_gate_collector", SCRIPT)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)

P7_SCRIPT = SCRIPT.with_name("kolibri_p7_release.py")
P7_SPEC = importlib.util.spec_from_file_location("kolibri_p7_release_for_collector_test", P7_SCRIPT)
assert P7_SPEC and P7_SPEC.loader
p7_release = importlib.util.module_from_spec(P7_SPEC)
sys.modules[P7_SPEC.name] = p7_release
P7_SPEC.loader.exec_module(p7_release)


RELEASE_ID = "kolibri-p7-fixture"
MANIFEST_SHA = "a" * 64
OWNER_TOKEN = "owner-test-token"


def _png(red: int, green: int, blue: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    width = height = 64
    rows = b"".join(b"\x00" + bytes((red, green, blue)) * width for _ in range(height))
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(rows, 9)),
            chunk(b"IEND", b""),
        )
    )


GENERATED_IMAGE = _png(245, 60, 80)
EDITED_IMAGE = _png(45, 120, 230)


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _pdf_bytes(label: str, *, repeat: int = 120) -> bytes:
    return (
        b"%PDF-1.7\n1 0 obj<</Type/Catalog>>endobj\nstream\n"
        + label.encode("utf-8") * repeat
        + b"\nendstream\n%%EOF\n"
    )


def _calculate_estimate(payload: dict, *, version: int) -> dict:
    sections = []
    subtotal = 0
    for section_index, section in enumerate(payload.get("sections", []), 1):
        positions = []
        section_total = 0
        for position_index, position in enumerate(section.get("positions", []), 1):
            value = round(float(position["quantity"]) * float(position["price"]), 2)
            section_total += value
            positions.append(
                {
                    "id": position.get("id") or str(uuid.uuid4()),
                    "code": position.get("code", f"P{position_index}"),
                    "name": position["name"],
                    "unit": position["unit"],
                    "quantity": str(position["quantity"]),
                    "price": str(position["price"]),
                    "sum": f"{value:.2f}",
                    "source": position.get("source", ""),
                    "price_evidence": position.get("price_evidence", []),
                    "comment": position.get("comment", ""),
                }
            )
        subtotal += section_total
        sections.append(
            {
                "id": section.get("id") or str(uuid.uuid4()),
                "title": section["title"],
                "subtotal": f"{section_total:.2f}",
                "positions": positions,
            }
        )
    overhead_rate = float(payload.get("overhead_rate", "0"))
    vat_rate = float(payload.get("vat_rate", "0"))
    overhead = round(subtotal * overhead_rate / 100, 2)
    vat = round((subtotal + overhead) * vat_rate / 100, 2)
    return {
        "id": payload.get("id") or str(uuid.uuid4()),
        "version": version,
        "status": payload.get("status", "draft"),
        "estimate_status": payload.get("estimate_status", "source_backed"),
        "pricing_status": payload.get("pricing_status", "source_backed"),
        "scope_status": payload.get("scope_status", "verified"),
        "source_note": payload.get("source_note", "Fixture evidence"),
        "assumptions": payload.get("assumptions", []),
        "questions": payload.get("questions", []),
        "price_sources": payload.get("price_sources", []),
        "evidence_issues": payload.get("evidence_issues", []),
        "title": payload["title"],
        "client": payload.get("client", ""),
        "object_name": payload.get("object_name", ""),
        "region": payload.get("region", ""),
        "currency": payload.get("currency", "RUB"),
        "overhead_rate": str(payload.get("overhead_rate", "0")),
        "vat_rate": str(payload.get("vat_rate", "0")),
        "subtotal": f"{subtotal:.2f}",
        "overhead_amount": f"{overhead:.2f}",
        "vat_amount": f"{vat:.2f}",
        "total": f"{subtotal + overhead + vat:.2f}",
        "sections": sections,
        "created_at": "2026-07-14T12:00:00Z",
        "updated_at": "2026-07-14T12:00:00Z",
    }


def _estimate_draft(*, control: bool) -> dict:
    if control:
        title = "Смета: Кирпичный гараж 36 м² — Казань, Татарстан"
        object_name = "Кирпичный гараж 36 м²"
        region = "Казань, Татарстан"
        specs = (
            ("Основание гаража", (("GAR-001", "Щебёночная подготовка", "м³", "8", "2400"), ("GAR-002", "Бетон B22.5", "м³", "12", "6200"))),
            ("Стены гаража", (("GAR-003", "Кирпич керамический", "шт.", "5000", "28"), ("GAR-004", "Раствор кладочный", "м³", "6", "5100"))),
            ("Кровля гаража", (("GAR-005", "Профнастил", "м²", "52", "1050"), ("GAR-006", "Стропильная доска", "м³", "4", "27000"))),
        )
    else:
        title = "Смета: Одноэтажный дом 100 м² — Лениногорск, Татарстан"
        object_name = "Одноэтажный дом 100 м²"
        region = "Лениногорск, Татарстан"
        specs = (
            ("Фундамент", (("HOME-001", "Бетон B25 для фундаментной плиты", "м³", "35", "6500"), ("HOME-002", "Арматура A500C", "т", "4.5", "85000"))),
            ("Стены", (("HOME-003", "Газобетон D500", "м³", "45", "7200"), ("HOME-004", "Клей для газобетона", "меш.", "120", "650"))),
            ("Кровля", (("HOME-005", "Пиломатериал хвойный", "м³", "12", "28000"), ("HOME-006", "Металлочерепица", "м²", "145", "1200"))),
        )
    sections = []
    evidence_records = []
    for section_title, positions in specs:
        section_positions = []
        for code, name, unit, quantity, price in positions:
            evidence = {
                "position_code": code,
                "source_id": f"fixture:{code}",
                "url": f"https://example.test/catalog/{code.lower()}",
                "source_title": "Региональный каталог",
                "source_type": "supplier_catalog",
                "region": region,
                "observed_at": "2026-07-14T12:00:00Z",
                "price_date": "2026-07-14",
                "unit": unit,
                "vat_status": "included",
                "quote": "Проверенная цена",
                "unit_price": price,
                "currency": "RUB",
                "content_sha256": collector._sha256(code.encode()),
                "verification": "source_backed",
                "attestation": collector._sha256(f"attestation:{code}".encode()),
            }
            evidence_records.append(evidence)
            section_positions.append(
                {
                    "code": code,
                    "name": name,
                    "unit": unit,
                    "quantity": quantity,
                    "price": price,
                    "source": evidence["url"],
                    "price_evidence": [evidence],
                    "comment": "",
                }
            )
        sections.append({"title": section_title, "positions": section_positions})
    return {
        "title": title,
        "client": "P7",
        "object_name": object_name,
        "region": region,
        "currency": "RUB",
        "overhead_rate": "10",
        "vat_rate": "22",
        "estimate_status": "source_backed",
        "pricing_status": "source_backed",
        "scope_status": "verified",
        "source_note": "Цены подтверждены источником",
        "assumptions": [],
        "questions": [],
        "price_sources": evidence_records,
        "evidence_issues": [],
        "sections": sections,
    }


class FixtureState:
    def __init__(self):
        self.keys: dict[str, dict] = {}
        self.key_counter = 0
        self.projects: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self.estimates: dict[str, dict] = {}
        self.revisions: dict[str, list[dict]] = {}
        self.artifacts: dict[str, dict] = {}
        self.responses: dict[str, dict] = {}
        self.response_counter = 0

    def new_response_id(self) -> str:
        self.response_counter += 1
        return f"resp_fixture_{self.response_counter}"

    def add_artifact(self, content: bytes, mime: str, artifact_type: str) -> dict:
        artifact_id = str(uuid.uuid4())
        artifact = {
            "id": artifact_id,
            "type": artifact_type,
            "mime_type": mime,
            "size_bytes": len(content),
            "sha256": collector._sha256(content),
            "url": f"/api/v1/artifacts/{artifact_id}",
            "download_url": f"/api/v1/artifacts/{artifact_id}?download=true",
            "reopen_url": f"/api/v1/artifacts/{artifact_id}/reopen",
            "history_url": f"/api/v1/artifacts/{artifact_id}/history",
        }
        self.artifacts[artifact_id] = {"manifest": artifact, "content": content}
        return artifact


def _sse(events: list[tuple[str | None, dict | str]]) -> Response:
    blocks = []
    for name, payload in events:
        prefix = f"event: {name}\n" if name else ""
        data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        blocks.append(f"{prefix}data: {data}\n\n")
    return Response("".join(blocks), media_type="text/event-stream")


def make_fixture_app(state: FixtureState) -> FastAPI:
    app = FastAPI()

    def json_response(payload: dict, status: int = 200, headers: dict | None = None):
        merged = {"X-Kolibri-Release": RELEASE_ID, **(headers or {})}
        return JSONResponse(payload, status_code=status, headers=merged)

    def authorized(request: Request) -> bool:
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        return any(item["secret"] == token and not item["revoked"] for item in state.keys.values())

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def routes(path: str, request: Request):
        route = "/" + path
        method = request.method
        owner = request.headers.get("x-kolibri-owner-token") == OWNER_TOKEN

        if route == "/" and method == "GET":
            return Response(
                "<!doctype html><html><body><div id='root'></div></body></html>",
                media_type="text/html",
                headers={"X-Kolibri-Release": RELEASE_ID},
            )
        if route == "/api/health" and method == "GET":
            return json_response(
                {
                    "status": "ok",
                    "version": "3.0.0",
                    "release_id": RELEASE_ID,
                    "database": "connected",
                    "timestamp": "2026-07-14T12:00:00Z",
                }
            )
        if route == "/api/v1/shell/bootstrap" and method == "POST":
            return json_response(
                {
                    "session_id": "fixture_session_1234567890",
                    "session_type": "anonymous",
                    "restored": False,
                    "expires_at": "2026-08-14T12:00:00Z",
                },
                headers={"Set-Cookie": "kolibri_session=fixture; Path=/; HttpOnly; SameSite=Lax"},
            )
        if route == "/v1/api-keys" and method == "POST":
            if not owner:
                return json_response({"detail": {"code": "owner_authentication_required"}}, 401)
            state.key_counter += 1
            key_id = f"key_fixture_{state.key_counter}"
            secret = f"koli_live_fixture_{state.key_counter}"
            item = {
                "id": key_id,
                "object": "api_key",
                "name": (await request.json())["name"],
                "prefix": secret[:14],
                "created_at": 1,
                "last_used_at": None,
                "revoked": False,
                "revoked_at": None,
                "secret": secret,
            }
            state.keys[key_id] = item
            return json_response({**item, "secret_shown_once": True}, 201)
        if route == "/v1/api-keys" and method == "GET":
            if not owner:
                return json_response({"detail": {"code": "owner_authentication_required"}}, 401)
            data = [
                {key: value for key, value in item.items() if key != "secret"}
                for item in state.keys.values()
            ]
            return json_response({"object": "list", "data": data})
        if route.startswith("/v1/api-keys/") and method == "DELETE":
            if not owner:
                return json_response({"detail": {"code": "owner_authentication_required"}}, 401)
            key_id = route.rsplit("/", 1)[-1]
            item = state.keys[key_id]
            item["revoked"] = True
            item["revoked_at"] = 2
            return json_response({key: value for key, value in item.items() if key != "secret"})
        if route == "/v1/models" and method == "GET":
            if not authorized(request):
                return json_response({"detail": {"code": "invalid_api_key"}}, 401)
            return json_response(
                {"object": "list", "data": [{"id": "kolibri", "object": "model", "owned_by": "kolibri"}]}
            )

        if route == "/api/v1/responses" and method == "POST":
            body = await request.json()
            prompt = str(body.get("input") or "")
            if "Составь реальную смету" in prompt:
                draft = _estimate_draft(control="гаража" in prompt)
                response_id = state.new_response_id()
                return json_response(
                    {
                        "id": response_id,
                        "object": "response",
                        "status": "completed",
                        "model": "kolibri",
                        "output": [],
                        "output_text": "Смета подготовлена.",
                        "error": None,
                        "artifacts": [],
                        "actions": [{"type": "create_estimate", "label": "Открыть смету", "data": draft}],
                    }
                )
        if route == "/v1/responses" and method == "POST":
            if not authorized(request):
                return json_response({"detail": {"code": "invalid_api_key"}}, 401)
            body = await request.json()
            response_id = state.new_response_id()
            if body.get("stream") and body.get("text"):
                value = '{"answer":"P7","score":10}'
                return _sse(
                    [
                        (
                            "response.created",
                            {
                                "type": "response.created",
                                "response": {"id": response_id, "status": "in_progress", "model": "kolibri"},
                            },
                        ),
                        (
                            "response.output_text.delta",
                            {"type": "response.output_text.delta", "response_id": response_id, "delta": value},
                        ),
                        (
                            "response.completed",
                            {
                                "type": "response.completed",
                                "response": {"id": response_id, "status": "completed", "model": "kolibri", "output_text": value},
                            },
                        ),
                    ]
                )
            if body.get("stream"):
                text = "Поток Kolibri P7 завершён."
                return _sse(
                    [
                        (
                            "response.created",
                            {
                                "type": "response.created",
                                "response": {"id": response_id, "status": "in_progress", "model": "kolibri"},
                            },
                        ),
                        (
                            "response.output_text.delta",
                            {"type": "response.output_text.delta", "response_id": response_id, "delta": text},
                        ),
                        (
                            "response.completed",
                            {
                                "type": "response.completed",
                                "response": {"id": response_id, "status": "completed", "model": "kolibri", "output_text": text},
                            },
                        ),
                    ]
                )
            if body.get("background"):
                payload = {
                    "id": response_id,
                    "object": "response",
                    "status": "in_progress",
                    "model": "kolibri",
                    "output": [],
                    "output_text": "",
                    "error": None,
                    "artifacts": [],
                    "actions": [],
                }
                state.responses[response_id] = payload
                return json_response(payload)
        if route.startswith("/v1/responses/") and route.endswith("/cancel") and method == "POST":
            if not authorized(request):
                return json_response({"detail": {"code": "invalid_api_key"}}, 401)
            response_id = route.split("/")[3]
            payload = state.responses[response_id]
            payload["status"] = "cancelled"
            return json_response(payload)
        if route.startswith("/v1/responses/") and route.endswith("/retry") and method == "POST":
            if not authorized(request):
                return json_response({"detail": {"code": "invalid_api_key"}}, 401)
            response_id = state.new_response_id()
            payload = {
                "id": response_id,
                "object": "response",
                "status": "completed",
                "model": "kolibri",
                "output": [],
                "output_text": "Повтор P7 завершён.",
                "error": None,
                "artifacts": [],
                "actions": [],
            }
            state.responses[response_id] = payload
            return json_response(payload)
        if route.startswith("/v1/responses/") and method == "GET":
            if not authorized(request):
                return json_response({"detail": {"code": "invalid_api_key"}}, 401)
            return json_response(state.responses[route.rsplit("/", 1)[-1]])
        if route == "/v1/chat/completions" and method == "POST":
            if not authorized(request):
                return json_response({"detail": {"code": "invalid_api_key"}}, 401)
            return _sse(
                [
                    (
                        None,
                        {
                            "id": "chatcmpl_fixture",
                            "object": "chat.completion.chunk",
                            "model": "kolibri",
                            "choices": [{"index": 0, "delta": {"content": '{"answer":"P7","score":10}'}, "finish_reason": None}],
                        },
                    ),
                    (
                        None,
                        {
                            "id": "chatcmpl_fixture",
                            "object": "chat.completion.chunk",
                            "model": "kolibri",
                            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                        },
                    ),
                    (None, "[DONE]"),
                ]
            )

        if route == "/api/v1/projects" and method == "POST":
            project_id = str(uuid.uuid4())
            body = await request.json()
            project = {
                "id": project_id,
                "title": body.get("title") or "Новый проект",
                "title_source": "manual",
                "status": "active",
                "version": 1,
                "message_count": 0,
                "metadata": {},
                "created_at": "2026-07-14T12:00:00Z",
                "updated_at": "2026-07-14T12:00:00Z",
                "last_message_at": None,
                "deleted_at": None,
            }
            state.projects[project_id] = project
            state.messages[project_id] = []
            return json_response(project, 201)
        if route.startswith("/api/v1/projects/") and route.endswith("/messages"):
            project_id = route.split("/")[4]
            if method == "POST":
                body = await request.json()
                message = {
                    "id": str(uuid.uuid4()),
                    "project_id": project_id,
                    "sequence": len(state.messages[project_id]) + 1,
                    "version": 1,
                    "role": body["role"],
                    "content": body["content"],
                    "status": body.get("status", "completed"),
                    "metadata": body.get("metadata", {}),
                    "created_at": "2026-07-14T12:00:00Z",
                    "updated_at": "2026-07-14T12:00:00Z",
                }
                state.messages[project_id].append(message)
                return json_response(message, 201)
            if method == "GET":
                items = state.messages[project_id]
                return json_response({"items": items, "total": len(items), "after": 0, "limit": 100})

        if route == "/api/v1/estimates" and method == "POST":
            body = await request.json()
            estimate = _calculate_estimate(body, version=1)
            state.estimates[estimate["id"]] = estimate
            state.revisions[estimate["id"]] = [json.loads(json.dumps(estimate))]
            return json_response(estimate, 201, {"ETag": '"1"'})
        if route.startswith("/api/v1/estimates/"):
            parts = route.split("/")
            estimate_id = parts[4]
            if len(parts) == 5 and method == "GET":
                estimate = state.estimates[estimate_id]
                return json_response(estimate, headers={"ETag": f'"{estimate["version"]}"'})
            if len(parts) == 5 and method == "PUT":
                body = await request.json()
                body["id"] = estimate_id
                estimate = _calculate_estimate(body, version=state.estimates[estimate_id]["version"] + 1)
                state.estimates[estimate_id] = estimate
                state.revisions[estimate_id].append(json.loads(json.dumps(estimate)))
                return json_response(estimate, headers={"ETag": f'"{estimate["version"]}"'})
            if len(parts) == 6 and parts[5] == "revisions" and method == "GET":
                items = [
                    {
                        "id": str(uuid.uuid4()),
                        "estimate_id": estimate_id,
                        "version": item["version"],
                        "title": item["title"],
                        "status": item["status"],
                        "estimate_status": item["estimate_status"],
                        "pricing_status": item["pricing_status"],
                        "total": item["total"],
                        "created_at": item["created_at"],
                    }
                    for item in state.revisions[estimate_id]
                ]
                return json_response({"items": items, "total": len(items)})
            if len(parts) == 7 and parts[5] == "revisions" and method == "GET":
                version = int(parts[6])
                snapshot = next(item for item in state.revisions[estimate_id] if item["version"] == version)
                return json_response(
                    {
                        "id": str(uuid.uuid4()),
                        "estimate_id": estimate_id,
                        "version": version,
                        "snapshot": snapshot,
                        "created_at": snapshot["created_at"],
                    }
                )
            if len(parts) == 6 and parts[5] == "pdf" and method == "GET":
                pdf = _pdf_bytes("estimate-p7", repeat=180)
                return Response(pdf, media_type="application/pdf", headers={"X-Kolibri-Release": RELEASE_ID})

        if route == "/v1/capabilities" and method == "GET":
            capabilities = []
            for index in range(12):
                status = "available" if index < 8 else "degraded" if index < 10 else "unavailable"
                capabilities.append(
                    {
                        "id": f"capability.{index}",
                        "name": f"Capability {index}",
                        "kind": "test",
                        "status": status,
                        "invocable": status == "available",
                        "reason": {
                            "code": "live_invocation" if status == "available" else "probe_not_run" if status == "degraded" else "route_not_configured",
                            "message": "Technical runtime verdict",
                        },
                        "verified_at": "2026-07-14T12:00:00Z" if status == "available" else None,
                        "selected_route_id": "fixture-route" if status == "available" else None,
                        "source": {"type": "live_invocation" if status == "available" else "runtime_evidence"},
                        "routes": [
                            {
                                "id": "fixture-route",
                                "probe": {
                                    "state": "succeeded" if status == "available" else "never",
                                    "fresh": status == "available",
                                },
                            }
                        ],
                    }
                )
            return json_response(
                {
                    "schema_version": "kolibri.capabilities.v1",
                    "release_id": RELEASE_ID,
                    "probe_ttl_seconds": 25200,
                    "status": "degraded",
                    "as_of": "2026-07-14T12:00:00Z",
                    "counts": {"available": 8, "degraded": 2, "unavailable": 2},
                    "capabilities": capabilities,
                }
            )

        if route == "/api/v1/files" and method == "POST":
            raw = await request.body()
            start = raw.find(b"\r\n\r\n")
            end = raw.rfind(b"\r\n--")
            content = raw[start + 4 : end]
            artifact = state.add_artifact(content, "text/plain", "file.upload")
            return json_response({"object": "file", "artifact": artifact}, 201)
        if route.startswith("/api/v1/files/") and route.endswith("/analyze") and method == "POST":
            artifact_id = route.split("/")[4]
            source = state.artifacts[artifact_id]
            analysis = json.dumps(
                {"source_artifact_id": artifact_id, "text": source["content"].decode()},
                ensure_ascii=False,
            ).encode()
            artifact = state.add_artifact(analysis, "application/json", "file.analysis")
            return json_response(
                {
                    "analysis": {
                        "source_artifact_id": artifact_id,
                        "source_sha256": source["manifest"]["sha256"],
                        "mime_type": "text/plain",
                        "text": source["content"].decode(),
                        "characters": len(source["content"]),
                    },
                    "artifact": artifact,
                },
                201,
            )
        if route == "/api/v1/files/search" and method == "GET":
            query = request.query_params["q"]
            items = []
            for item in state.artifacts.values():
                if item["manifest"]["type"] == "file.upload" and query.encode() in item["content"]:
                    items.append({"artifact": item["manifest"], "snippet": item["content"].decode()})
            return json_response({"query": query, "items": items, "total": len(items)})

        if route == "/api/v1/tools/invoke" and method == "POST":
            body = await request.json()
            tool = body["tool"]
            arguments = body["arguments"]
            if tool == "web.search":
                return json_response(
                    {
                        "tool": tool,
                        "status": "completed",
                        "result": {
                            "query": arguments["query"],
                            "sources": [
                                {
                                    "title": "Официальный каталог Татарстана",
                                    "snippet": "Актуальные цены",
                                    "url": "https://example.test/official/prices",
                                }
                            ],
                            "total": 1,
                        },
                    }
                )
            if tool.startswith("document."):
                format_id = tool.split(".", 1)[1]
                mime, magic, _arguments = collector.DOCUMENT_FORMATS[format_id]
                if format_id == "pdf":
                    content = _pdf_bytes("document-p7", repeat=90)
                else:
                    required = {
                        "docx": "word/document.xml",
                        "xlsx": "xl/workbook.xml",
                        "pptx": "ppt/presentation.xml",
                    }[format_id]
                    content = _zip_bytes(
                        {
                            "[Content_Types].xml": b"<Types>" + b"x" * 300 + b"</Types>",
                            required: b"<document>" + format_id.encode() * 120 + b"</document>",
                        }
                    )
                artifact = state.add_artifact(content, mime, tool)
                return json_response({"tool": tool, "status": "completed", "result": artifact})
            if tool in {"image.generate", "image.edit"}:
                content = GENERATED_IMAGE if tool == "image.generate" else EDITED_IMAGE
                artifact = state.add_artifact(content, "image/png", "image")
                if tool == "image.edit":
                    artifact["source_artifact_id"] = arguments["source_artifact_id"]
                return json_response(
                    {"tool": tool, "status": "completed", "result": {"artifact": artifact}}
                )
            if tool in {"site.create", "app.create"}:
                content = _zip_bytes(
                    {
                        "index.html": (
                            b"<!doctype html><html><body><h1>Kolibri proof</h1>"
                            + tool.encode() * 100
                            + b"</body></html>"
                        ),
                        "assets/app.js": b"document.documentElement.dataset.ready='true';" * 8,
                    }
                )
                artifact = state.add_artifact(content, "application/zip", f"{tool}.bundle")
                preview_url = f"/api/v1/previews/{artifact['id']}/index.html"
                return json_response(
                    {
                        "tool": tool,
                        "status": "completed",
                        "result": {
                            "artifact": artifact,
                            "preview_url": preview_url,
                            "entrypoint": "index.html",
                            "files": [{"path": "index.html", "size_bytes": 50, "sha256": "d" * 64}],
                            "provider": "fixture-provider",
                            "model": "fixture-model",
                        },
                    }
                )

        if route.startswith("/api/v1/artifacts/") and method == "GET":
            parts = route.split("/")
            artifact_id = parts[4]
            item = state.artifacts[artifact_id]
            if len(parts) == 6 and parts[5] == "reopen":
                return json_response(
                    {
                        "artifact": item["manifest"],
                        "integrity": {"algorithm": "sha256", "digest": item["manifest"]["sha256"]},
                    }
                )
            if len(parts) == 6 and parts[5] == "history":
                return json_response({"artifact_id": artifact_id, "items": [item["manifest"]], "total": 1})
            return Response(
                item["content"],
                media_type=item["manifest"]["mime_type"],
                headers={"X-Kolibri-Release": RELEASE_ID},
            )
        if route.startswith("/api/v1/previews/") and method == "GET":
            return Response(
                "<!doctype html><html><body>Kolibri proof</body></html>",
                media_type="text/html",
                headers={
                    "Content-Security-Policy": "default-src 'none'; connect-src 'none'; sandbox allow-scripts",
                    "X-Content-Type-Options": "nosniff",
                    "Permissions-Policy": "camera=(), microphone=()",
                    "X-Kolibri-Release": RELEASE_ID,
                },
            )
        if route in {"/api/v1/integrations/connect", "/api/v1/automations/run"} and method == "POST":
            if not owner:
                return json_response({"detail": {"code": "owner_authentication_required"}}, 401)
            return json_response({"detail": {"code": "capability_unavailable"}}, 503)

        return json_response({"detail": {"code": "not_found"}}, 404)

    return app


@pytest.fixture
def http_fixture():
    state = FixtureState()
    app = make_fixture_app(state)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="critical", access_log=False, lifespan="off")
    )
    thread = Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started
    try:
        yield state, f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


def write_browser_evidence(
    path: Path,
    state: FixtureState,
    origin: str,
    *,
    rendered: bool = True,
) -> Path:
    generated = state.add_artifact(GENERATED_IMAGE, "image/png", "image.generated")
    edited = state.add_artifact(EDITED_IMAGE, "image/png", "image.edited")
    payload = {
        "schema_version": collector.BROWSER_SCHEMA_VERSION,
        "release_id": RELEASE_ID,
        "manifest_sha256": MANIFEST_SHA,
        "backend_origin": origin,
        "frontend_origin": origin,
        "runner": "playwright",
        "run_id": f"playwright-{uuid.uuid4()}",
        "collected_at": collector._utc_now(),
        "frontend_build_release_id": RELEASE_ID,
        "image_lifecycle": {
            "generate_http_status": 201,
            "edit_http_status": 201,
            "provider_tool_invoked": True,
            "generated_artifact_id": generated["id"],
            "generated_sha256": generated["sha256"],
            "generated_url": generated["url"],
            "generated_download_url": generated["download_url"],
            "edited_artifact_id": edited["id"],
            "edited_sha256": edited["sha256"],
            "edited_url": edited["url"],
            "edited_download_url": edited["download_url"],
            "rendered_in_shell": rendered,
        },
        "viewports": {
            "desktop_1440": {
                "status": "passed",
                "console_errors": 0,
                "unexplained_failed_requests": 0,
                "visible_controls_actionable": True,
                "horizontal_overflow": False,
            },
            "tablet_768": {
                "status": "passed",
                "console_errors": 0,
                "unexplained_failed_requests": 0,
                "visible_controls_actionable": True,
                "horizontal_overflow": False,
            },
            "mobile_390": {
                "status": "passed",
                "console_errors": 0,
                "unexplained_failed_requests": 0,
                "visible_controls_actionable": True,
                "horizontal_overflow": False,
            },
            "mobile_360": {
                "status": "passed",
                "console_errors": 0,
                "unexplained_failed_requests": 0,
                "visible_controls_actionable": True,
                "horizontal_overflow": False,
            },
        },
        "reload_reopens_all_artifact_types": True,
        "unavailable_capabilities_hidden": True,
        "placeholder_or_fake_success_detected": False,
    }
    path.write_bytes(collector.canonical_json(payload) + b"\n")
    return path


def make_collector(tmp_path: Path, origin: str, browser: Path) -> collector.P7GateCollector:
    token = tmp_path / "owner-token"
    token.write_text(OWNER_TOKEN + "\n", encoding="utf-8")
    return collector.P7GateCollector(
        release_id=RELEASE_ID,
        manifest_sha256=MANIFEST_SHA,
        backend_origin=origin,
        frontend_origin=origin,
        browser_evidence_path=browser,
        owner_token_file=token,
        timeout=5,
    )


def test_full_v3_contract_crosses_real_http_and_emits_canonical_unsigned_evidence(
    tmp_path: Path,
    http_fixture,
    capsys,
):
    state, origin = http_fixture
    browser = write_browser_evidence(tmp_path / "browser.json", state, origin)
    token = tmp_path / "owner-token"
    token.write_text(OWNER_TOKEN + "\n", encoding="utf-8")
    output = tmp_path / "gates.json"
    return_code = collector.main(
        [
            "--release-id",
            RELEASE_ID,
            "--manifest-sha256",
            MANIFEST_SHA,
            "--backend-origin",
            origin,
            "--frontend-origin",
            origin,
            "--browser-evidence",
            str(browser),
            "--owner-token-file",
            str(token),
            "--output",
            str(output),
            "--timeout",
            "5",
        ]
    )
    cli_result = json.loads(capsys.readouterr().out)
    evidence = json.loads(output.read_text(encoding="utf-8"))

    assert return_code == 0, {
        key: value
        for key, value in evidence["results"].items()
        if value["status"] != "passed"
    }
    assert cli_result["status"] == "passed"
    assert cli_result["output"] == str(output)
    assert cli_result["evidence_sha256"] == collector._sha256(output.read_bytes())
    assert evidence["schema_version"] == collector.SCHEMA_VERSION
    assert set(evidence["results"]) == set(collector.EXPECTED_GATES)
    assert all(value["status"] == "passed" for value in evidence["results"].values())
    assert evidence["results"]["image_lifecycle"]["edited_sha256"] == collector._sha256(EDITED_IMAGE)
    assert evidence["results"]["estimate_create_regional"]["truth_status"] == "source_backed"
    assert all(item["revoked"] for item in state.keys.values())
    assert "signature" not in json.dumps(evidence).casefold()
    assert OWNER_TOKEN not in json.dumps(evidence)

    canonical_evidence = collector.canonical_json(evidence) + b"\n"
    validator_result = p7_release._validate_gate_payload(
        evidence,
        {
            "release_id": RELEASE_ID,
            "targets": {
                "backend": {"origin": origin},
                "frontend": {"origin": origin},
            },
        },
        MANIFEST_SHA,
        collector._sha256(canonical_evidence),
    )
    assert validator_result["status"] == "verified"
    assert set(validator_result["gates"]) == set(collector.EXPECTED_GATES)

    assert output.read_bytes() == collector.canonical_json(evidence) + b"\n"
    assert output.stat().st_mode & 0o777 == 0o640


def test_browser_evidence_is_release_bound_before_any_collection(tmp_path: Path, http_fixture):
    state, origin = http_fixture
    browser = write_browser_evidence(tmp_path / "browser.json", state, origin)
    payload = json.loads(browser.read_text(encoding="utf-8"))
    payload["release_id"] = "wrong-release"
    browser.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(collector.GateCollectorError, match="browser_evidence_binding_mismatch"):
        make_collector(tmp_path, origin, browser)


def test_stale_browser_evidence_is_rejected_before_collection(tmp_path: Path, http_fixture):
    state, origin = http_fixture
    browser = write_browser_evidence(tmp_path / "browser.json", state, origin)
    payload = json.loads(browser.read_text(encoding="utf-8"))
    payload["collected_at"] = (
        collector.datetime.now(collector.timezone.utc) - collector.timedelta(hours=1)
    ).isoformat().replace("+00:00", "Z")
    browser.write_bytes(collector.canonical_json(payload) + b"\n")

    with pytest.raises(collector.GateCollectorError, match="browser_evidence_stale"):
        make_collector(tmp_path, origin, browser)


def test_tablet_viewport_is_required_not_supplemental(tmp_path: Path, http_fixture):
    state, origin = http_fixture
    browser = write_browser_evidence(tmp_path / "browser.json", state, origin)
    payload = json.loads(browser.read_text(encoding="utf-8"))
    del payload["viewports"]["tablet_768"]
    browser.write_bytes(collector.canonical_json(payload) + b"\n")
    instance = make_collector(tmp_path, origin, browser)

    evidence, passed = instance.collect()

    assert passed is False
    assert evidence["results"]["shell_desktop_mobile"] == {
        "status": "failed",
        "error_code": "browser_viewport_matrix_invalid",
    }


def test_missing_rendered_image_fails_closed_without_faking_other_evidence(
    tmp_path: Path,
    http_fixture,
):
    state, origin = http_fixture
    browser = write_browser_evidence(tmp_path / "browser.json", state, origin, rendered=False)
    instance = make_collector(tmp_path, origin, browser)

    evidence, passed = instance.collect()

    assert passed is False
    assert evidence["results"]["image_lifecycle"] == {
        "status": "failed",
        "error_code": "browser_image_lifecycle_invalid",
    }
    assert evidence["results"]["document_artifacts"]["status"] == "passed"
    assert "private_key" not in SCRIPT.read_text(encoding="utf-8")
    assert "ssh-keygen" not in SCRIPT.read_text(encoding="utf-8")


def test_browser_claimed_image_sha_must_match_downloaded_artifact_bytes(
    tmp_path: Path,
    http_fixture,
):
    state, origin = http_fixture
    browser = write_browser_evidence(tmp_path / "browser.json", state, origin)
    payload = json.loads(browser.read_text(encoding="utf-8"))
    payload["image_lifecycle"]["edited_sha256"] = "f" * 64
    browser.write_bytes(collector.canonical_json(payload) + b"\n")
    instance = make_collector(tmp_path, origin, browser)

    evidence, passed = instance.collect()

    assert passed is False
    assert evidence["results"]["image_lifecycle"] == {
        "status": "failed",
        "error_code": "browser_image_artifact_bytes_invalid",
    }
