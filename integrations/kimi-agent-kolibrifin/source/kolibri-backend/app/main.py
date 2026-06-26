"""Kolibri API — FastAPI backend for estimates, documents, PDF, agents, nodes, tasks."""
import os
import uuid
import base64
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from contextlib import asynccontextmanager

from app.calculator import (
    Estimate as CalcEstimate, EstimateSection as CalcSection,
    EstimatePosition as CalcPosition, EstimateStatus,
    calculate_estimate, validate_estimate, format_currency,
    estimate_to_dict, export_to_csv, export_to_json,
)
from app.pdf_generator import generate_estimate_pdf, generate_document_pdf
from app import schemas


# ---------------------------------------------------------------------------
# In-memory storage (replace with PostgreSQL in production)
# ---------------------------------------------------------------------------

class Store:
    def __init__(self):
        self.estimates: Dict[str, dict] = {}
        self.documents: Dict[str, dict] = {}
        self.library: Dict[str, dict] = {}
        self.agents: Dict[str, dict] = {}
        self.nodes: Dict[str, dict] = {}
        self.tasks: Dict[str, dict] = {}

    def _now(self):
        return datetime.utcnow().isoformat() + "Z"

    def _seed(self):
        """Seed sample data."""
        # Sample estimates
        est_id = str(uuid.uuid4())
        self.estimates[est_id] = {
            "id": est_id, "version": 1, "status": "ready",
            "title": "Смета на электромонтаж дома 120 м²",
            "client": "Иванов И.И.", "object_name": "Дом 120 м², д. Примерное",
            "region": "Московская область", "currency": "RUB",
            "overhead_rate": "15", "vat_rate": "20",
            "subtotal": "0", "overhead_amount": "0",
            "vat_amount": "0", "total": "0",
            "sections": [
                {
                    "id": str(uuid.uuid4()), "title": "Электромонтажные работы", "subtotal": "0",
                    "positions": [
                        {"id": str(uuid.uuid4()), "code": "ЭМ-01-001", "name": "Прокладка кабеля ВВГнг 3x2.5", "unit": "м", "quantity": "150", "price": "85.50", "sum": "0", "source": "СНиП", "comment": ""},
                        {"id": str(uuid.uuid4()), "code": "ЭМ-01-002", "name": "Монтаж розетки", "unit": "шт", "quantity": "25", "price": "450.00", "sum": "0", "source": "Прайс", "comment": ""},
                        {"id": str(uuid.uuid4()), "code": "ЭМ-01-003", "name": "Установка автомата 16А", "unit": "шт", "quantity": "12", "price": "320.00", "sum": "0", "source": "Прайс", "comment": ""},
                        {"id": str(uuid.uuid4()), "code": "ЭМ-01-004", "name": "Сборка электрощита", "unit": "компл", "quantity": "1", "price": "8500.00", "sum": "0", "source": "СМЕТА", "comment": "Щит автоматики"},
                    ]
                },
                {
                    "id": str(uuid.uuid4()), "title": "Сантехнические работы", "subtotal": "0",
                    "positions": [
                        {"id": str(uuid.uuid4()), "code": "СТ-02-001", "name": "Установка смесителя", "unit": "шт", "quantity": "4", "price": "1200.00", "sum": "0", "source": "Прайс", "comment": ""},
                        {"id": str(uuid.uuid4()), "code": "СТ-02-002", "name": "Прокладка трубы ППР 25мм", "unit": "м", "quantity": "35", "price": "180.00", "sum": "0", "source": "СНиП", "comment": ""},
                    ]
                },
                {
                    "id": str(uuid.uuid4()), "title": "Отделочные работы", "subtotal": "0",
                    "positions": [
                        {"id": str(uuid.uuid4()), "code": "ОТ-03-001", "name": "Штукатурка стен", "unit": "м²", "quantity": "280", "price": "350.00", "sum": "0", "source": "СМЕТА", "comment": ""},
                        {"id": str(uuid.uuid4()), "code": "ОТ-03-002", "name": "Покраска потолка", "unit": "м²", "quantity": "120", "price": "220.00", "sum": "0", "source": "Прайс", "comment": ""},
                        {"id": str(uuid.uuid4()), "code": "ОТ-03-003", "name": "Укладка плитки", "unit": "м²", "quantity": "45", "price": "850.00", "sum": "0", "source": "Прайс", "comment": ""},
                    ]
                }
            ],
            "created_at": self._now(), "updated_at": self._now(),
        }
        self._recalc_estimate(est_id)

        # More estimates
        for i, (title, client, obj) in enumerate([
            ("Смета на ремонт офиса 80 м²", "ООО ТехноСервис", "Офис 80 м², Москва"),
            ("Смета на монтаж Видеонаблюдения", "ООО Безопасность", "Склад 500 м²"),
            ("Смета на реконструкцию фасада", "ИП Петров", "Дом 200 м², СПб"),
        ], 2):
            eid = str(uuid.uuid4())
            self.estimates[eid] = {
                "id": eid, "version": 1, "status": "draft" if i % 2 == 0 else "approved",
                "title": title, "client": client, "object_name": obj,
                "region": "Москва" if "Моск" in obj else "Санкт-Петербург",
                "currency": "RUB", "overhead_rate": "10", "vat_rate": "20",
                "subtotal": "0", "overhead_amount": "0",
                "vat_amount": "0", "total": "0",
                "sections": [{
                    "id": str(uuid.uuid4()), "title": "Основные работы", "subtotal": "0",
                    "positions": [
                        {"id": str(uuid.uuid4()), "code": f"П{i:02d}-001", "name": "Позиция 1", "unit": "м", "quantity": "100", "price": "150.00", "sum": "0", "source": "Прайс", "comment": ""},
                        {"id": str(uuid.uuid4()), "code": f"П{i:02d}-002", "name": "Позиция 2", "unit": "шт", "quantity": "10", "price": "500.00", "sum": "0", "source": "Прайс", "comment": ""},
                    ]
                }],
                "created_at": self._now(), "updated_at": self._now(),
            }
            self._recalc_estimate(eid)

        # Documents
        for i, (title, dtype) in enumerate([
            ("Договор подряда №45/2024", "contract"),
            ("Акт выполненных работ", "act"),
            ("Коммерческое предложение", "proposal"),
            ("Технический отчёт", "report"),
        ]):
            did = str(uuid.uuid4())
            self.documents[did] = {
                "id": did, "title": title, "type": dtype,
                "status": "final" if i < 2 else "draft",
                "client": f"Клиент {i+1}", "project": f"Проект {i+1}",
                "content": f"<h1>{title}</h1><p>Содержание документа...</p>",
                "variables": {"client_name": f"Клиент {i+1}", "date": "25.06.2024"},
                "template": "", "created_at": self._now(), "updated_at": self._now(),
            }

        # Agents
        agent_roles = [
            ("Сметчик-аналитик", "estimate_analyst", "active"),
            ("Документолог", "document_writer", "active"),
            ("Code Reviewer", "code_reviewer", "idle"),
            ("Тестировщик", "tester", "active"),
            ("DevOps агент", "devops", "paused"),
            ("FormulaLM Trainer", "ml_trainer", "active"),
        ]
        for i, (name, role, status) in enumerate(agent_roles):
            aid = str(uuid.uuid4())
            self.agents[aid] = {
                "id": aid, "name": name, "role": role, "status": status,
                "node_id": None, "current_task": f"Задача {i+1}" if status == "active" else None,
                "progress": (i + 1) * 15, "model": "gpt-4" if i < 3 else "claude",
                "capabilities": {}, "cost_accumulated": str((i+1) * 1250),
                "heartbeat_at": self._now(),
            }

        # Nodes (20)
        for i in range(1, 21):
            nid = str(uuid.uuid4())
            statuses = ["healthy"] * 15 + ["degraded"] * 3 + ["offline"] * 2
            import random
            random.seed(i)
            status = statuses[i - 1]
            self.nodes[nid] = {
                "id": nid, "name": f"node-{i:02d}",
                "region": random.choice(["msk", "spb", "nsk", "kzn"]),
                "ip_address": f"10.77.{1 + i // 256}.{i % 256}",
                "status": status,
                "cpu_percent": str(random.randint(10, 85)),
                "ram_percent": str(random.randint(20, 75)),
                "disk_percent": str(random.randint(30, 90)),
                "network_mbps": str(random.randint(50, 1000)),
                "agent_count": random.randint(0, 20),
                "task_count": random.randint(0, 50),
                "ping_ms": random.randint(5, 150),
                "max_agents": 50,
                "capabilities": {},
            }

        # Tasks
        for i in range(20):
            tid = str(uuid.uuid4())
            self.tasks[tid] = {
                "id": tid, "workflow_id": f"wf-{i+1}",
                "state": random.choice(["queued", "running", "completed", "failed"]),
                "priority": random.randint(1, 5),
                "owner_agent_id": None,
                "node_id": None,
                "budget_limit": str(random.randint(100, 5000)),
                "attempts": random.randint(0, 2),
                "max_retries": 3,
                "result": None,
                "created_at": self._now(), "updated_at": self._now(),
            }

    def _recalc_estimate(self, est_id: str):
        e = self.estimates[est_id]
        calc = self._to_calc_estimate(e)
        calc = calculate_estimate(calc)
        e["subtotal"] = str(calc.subtotal)
        e["overhead_amount"] = str(calc.overhead_amount)
        e["vat_amount"] = str(calc.vat_amount)
        e["total"] = str(calc.total)
        for si, sec in enumerate(e["sections"]):
            calc_sec = calc.sections[si]
            sec["subtotal"] = str(calc_sec.subtotal)
            for pi, pos in enumerate(sec["positions"]):
                pos["sum"] = str(calc_sec.positions[pi].sum)

    def _to_calc_estimate(self, e: dict) -> CalcEstimate:
        sections = []
        for s in e.get("sections", []):
            positions = []
            for p in s.get("positions", []):
                positions.append(CalcPosition(
                    id=p["id"], code=p["code"], name=p["name"], unit=p["unit"],
                    quantity=p["quantity"], price=p["price"],
                    source=p.get("source", ""), comment=p.get("comment", ""),
                    sum=p.get("sum", "0"),
                ))
            sections.append(CalcSection(id=s["id"], title=s["title"], positions=positions))
        return CalcEstimate(
            id=e["id"], title=e["title"],
            status=EstimateStatus(e.get("status", "draft")),
            sections=sections, client=e.get("client", ""),
            object_name=e.get("object_name", ""),
            region=e.get("region", ""), currency=e.get("currency", "RUB"),
            overhead_rate=e.get("overhead_rate", "0"),
            vat_rate=e.get("vat_rate", "20"),
            subtotal=e.get("subtotal", "0"),
            overhead_amount=e.get("overhead_amount", "0"),
            vat_amount=e.get("vat_amount", "0"),
            total=e.get("total", "0"),
        )


store = Store()


@asynccontextmanager
async def lifespan(app: FastAPI):
    store._seed()
    yield


app = FastAPI(
    title="Колибри API",
    description="Backend API for Kolibri AI workspace platform",
    version="2.4.1",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=schemas.HealthResponse)
async def health():
    return {"status": "ok", "version": "2.4.1", "database": "connected", "timestamp": datetime.utcnow()}


# ---------------------------------------------------------------------------
# Estimates
# ---------------------------------------------------------------------------

@app.get("/api/v1/estimates", response_model=schemas.EstimateListResponse)
async def list_estimates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    items = list(store.estimates.values())
    if status:
        items = [e for e in items if e["status"] == status]
    if search:
        s = search.lower()
        items = [e for e in items if s in e["title"].lower() or s in e.get("client", "").lower()]
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    return {"items": items[start:end], "total": total, "page": page, "page_size": page_size}


@app.post("/api/v1/estimates", response_model=schemas.EstimateResponse, status_code=201)
async def create_estimate(data: schemas.EstimateCreate):
    est_id = str(uuid.uuid4())
    now = store._now()
    estimate = {
        "id": est_id, "version": 1, "status": "draft",
        "title": data.title, "client": data.client,
        "object_name": data.object_name, "region": data.region,
        "currency": data.currency, "overhead_rate": data.overhead_rate,
        "vat_rate": data.vat_rate, "subtotal": "0",
        "overhead_amount": "0", "vat_amount": "0", "total": "0",
        "sections": [{"id": str(uuid.uuid4()), "title": s.title,
                       "subtotal": "0", "positions": [
                           {"id": str(uuid.uuid4()), "code": p.code, "name": p.name,
                            "unit": p.unit, "quantity": p.quantity, "price": p.price,
                            "sum": "0", "source": p.source, "comment": p.comment}
                           for p in s.positions]} for s in data.sections],
        "created_at": now, "updated_at": now,
    }
    store.estimates[est_id] = estimate
    store._recalc_estimate(est_id)
    return store.estimates[est_id]


@app.get("/api/v1/estimates/{est_id}", response_model=schemas.EstimateResponse)
async def get_estimate(est_id: str):
    if est_id not in store.estimates:
        raise HTTPException(404, "Estimate not found")
    return store.estimates[est_id]


@app.put("/api/v1/estimates/{est_id}", response_model=schemas.EstimateResponse)
async def update_estimate(est_id: str, data: schemas.EstimateUpdate):
    if est_id not in store.estimates:
        raise HTTPException(404, "Estimate not found")
    e = store.estimates[est_id]
    if data.title is not None: e["title"] = data.title
    if data.client is not None: e["client"] = data.client
    if data.object_name is not None: e["object_name"] = data.object_name
    if data.region is not None: e["region"] = data.region
    if data.currency is not None: e["currency"] = data.currency
    if data.overhead_rate is not None: e["overhead_rate"] = data.overhead_rate
    if data.vat_rate is not None: e["vat_rate"] = data.vat_rate
    if data.status is not None: e["status"] = data.status.value
    if data.sections is not None:
        e["sections"] = [{"id": str(uuid.uuid4()), "title": s.title,
                          "subtotal": "0", "positions": [
                              {"id": str(uuid.uuid4()), "code": p.code, "name": p.name,
                               "unit": p.unit, "quantity": p.quantity, "price": p.price,
                               "sum": "0", "source": p.source, "comment": p.comment}
                              for p in s.positions]} for s in data.sections]
    e["updated_at"] = store._now()
    store._recalc_estimate(est_id)
    return e


@app.delete("/api/v1/estimates/{est_id}", status_code=204)
async def delete_estimate(est_id: str):
    if est_id not in store.estimates:
        raise HTTPException(404, "Estimate not found")
    del store.estimates[est_id]
    return Response(status_code=204)


@app.post("/api/v1/estimates/{est_id}/calculate")
async def calculate_estimate_endpoint(est_id: str):
    if est_id not in store.estimates:
        raise HTTPException(404, "Estimate not found")
    store._recalc_estimate(est_id)
    return store.estimates[est_id]


@app.post("/api/v1/estimates/{est_id}/duplicate")
async def duplicate_estimate(est_id: str):
    if est_id not in store.estimates:
        raise HTTPException(404, "Estimate not found")
    orig = store.estimates[est_id]
    new_id = str(uuid.uuid4())
    new_est = {**orig, "id": new_id, "version": 1, "status": "draft",
               "title": f"{orig['title']} (копия)",
               "created_at": store._now(), "updated_at": store._now()}
    store.estimates[new_id] = new_est
    return new_est


@app.get("/api/v1/estimates/{est_id}/pdf")
async def estimate_pdf(est_id: str):
    if est_id not in store.estimates:
        raise HTTPException(404, "Estimate not found")
    pdf_bytes = generate_estimate_pdf(store.estimates[est_id])
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=estimate_{est_id[:8]}.pdf"})


@app.get("/api/v1/estimates/{est_id}/export/{fmt}")
async def export_estimate(est_id: str, fmt: str):
    if est_id not in store.estimates:
        raise HTTPException(404, "Estimate not found")
    e = store.estimates[est_id]
    calc = store._to_calc_estimate(e)
    calc = calculate_estimate(calc)
    if fmt == "csv":
        content = export_to_csv(calc)
        return Response(content=content, media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=estimate_{est_id[:8]}.csv"})
    elif fmt == "json":
        return export_to_json(calc)
    raise HTTPException(400, f"Unsupported format: {fmt}")


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
):
    items = list(store.documents.values())
    if type:
        items = [d for d in items if d["type"] == type]
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size}


@app.post("/api/v1/documents", status_code=201)
async def create_document(data: schemas.DocumentCreate):
    did = str(uuid.uuid4())
    now = store._now()
    store.documents[did] = {
        "id": did, "title": data.title, "type": data.type.value,
        "status": "draft", "client": data.client, "project": data.project,
        "content": data.content, "variables": data.variables,
        "template": data.template, "created_at": now, "updated_at": now,
    }
    return store.documents[did]


@app.get("/api/v1/documents/{doc_id}")
async def get_document(doc_id: str):
    if doc_id not in store.documents:
        raise HTTPException(404, "Document not found")
    return store.documents[doc_id]


@app.put("/api/v1/documents/{doc_id}")
async def update_document(doc_id: str, data: schemas.DocumentUpdate):
    if doc_id not in store.documents:
        raise HTTPException(404, "Document not found")
    d = store.documents[doc_id]
    for field in ["title", "type", "client", "project", "content", "variables", "template", "status"]:
        val = getattr(data, field)
        if val is not None:
            d[field] = val.value if hasattr(val, "value") else val
    d["updated_at"] = store._now()
    return d


@app.delete("/api/v1/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str):
    if doc_id not in store.documents:
        raise HTTPException(404, "Document not found")
    del store.documents[doc_id]
    return Response(status_code=204)


@app.get("/api/v1/documents/{doc_id}/pdf")
async def document_pdf(doc_id: str):
    if doc_id not in store.documents:
        raise HTTPException(404, "Document not found")
    pdf_bytes = generate_document_pdf(store.documents[doc_id])
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=document_{doc_id[:8]}.pdf"})


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

@app.get("/api/v1/library")
async def list_library(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    item_type: Optional[str] = None,
    search: Optional[str] = None,
):
    items = []
    for e in store.estimates.values():
        items.append({"id": e["id"], "title": e["title"], "item_type": "estimate",
                      "source_id": e["id"], "source_type": "estimate",
                      "status": e["status"], "client": e.get("client", ""),
                      "project": e.get("object_name", ""), "file_size": 0,
                      "created_at": e["created_at"], "updated_at": e["updated_at"]})
    for d in store.documents.values():
        items.append({"id": d["id"], "title": d["title"], "item_type": "document",
                      "source_id": d["id"], "source_type": "document",
                      "status": d["status"], "client": d.get("client", ""),
                      "project": d.get("project", ""), "file_size": 0,
                      "created_at": d["created_at"], "updated_at": d["updated_at"]})
    if item_type:
        items = [i for i in items if i["item_type"] == item_type]
    if search:
        s = search.lower()
        items = [i for i in items if s in i["title"].lower()]
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

@app.get("/api/v1/agents")
async def list_agents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
):
    items = list(store.agents.values())
    if status:
        items = [a for a in items if a["status"] == status]
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

@app.get("/api/v1/nodes")
async def list_nodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
):
    items = list(store.nodes.values())
    if status:
        items = [n for n in items if n["status"] == status]
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@app.get("/api/v1/tasks")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    state: Optional[str] = None,
):
    items = list(store.tasks.values())
    if state:
        items = [t for t in items if t["state"] == state]
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "total": len(items), "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

@app.post("/api/v1/pdf/generate")
async def generate_pdf(data: schemas.PDFGenerateRequest):
    pdf_bytes = generate_document_pdf({"title": data.title, "content": data.html_content})
    b64 = base64.b64encode(pdf_bytes).decode()
    return {"pdf_base64": b64, "filename": f"{data.title}.pdf",
            "page_count": 1, "size_bytes": len(pdf_bytes)}
