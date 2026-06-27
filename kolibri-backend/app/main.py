"""Kolibri API — FastAPI backend for estimates, documents, PDF, agents, nodes, tasks."""
from dotenv import load_dotenv
load_dotenv()

import os
import json
import uuid
import base64
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.security import HTTPBearer
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

from app.calculator import (
    Estimate as CalcEstimate, EstimateSection as CalcSection,
    EstimatePosition as CalcPosition, EstimateStatus,
    calculate_estimate, validate_estimate, format_currency,
    estimate_to_dict, export_to_csv, export_to_json,
)
from app.pdf_generator import generate_estimate_pdf, generate_document_pdf
from app.database import Base, engine, SessionLocal, get_db
from app.storage import DBStorage, seed_db
from app import schemas


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_db(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Колибри API",
    description="Backend API for Kolibri AI workspace platform",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.logging_middleware import RequestLoggingMiddleware, setup_logging
setup_logging()
app.add_middleware(RequestLoggingMiddleware)

from app.routers.telegram import router as telegram_router
app.include_router(telegram_router)

from proxy.deepseek_proxy import router as deepseek_router
app.include_router(deepseek_router)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=schemas.HealthResponse)
async def health():
    return {"status": "ok", "version": "3.0.0", "database": "connected", "timestamp": datetime.now(timezone.utc)}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/api/v1/auth/register", status_code=201)
async def register(data: schemas.UserRegister, db: Session = Depends(get_db)):
    from app.models import UserDB
    from app.auth import hash_password, create_access_token
    import uuid
    if db.query(UserDB).filter(UserDB.email == data.email).first():
        raise HTTPException(400, "Email already registered")
    user = UserDB(
        id=str(uuid.uuid4()), email=data.email, name=data.name,
        hashed_password=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    token = create_access_token({"sub": user.id})
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}}


@app.post("/api/v1/auth/login")
async def login(data: schemas.UserLogin, db: Session = Depends(get_db)):
    from app.models import UserDB
    from app.auth import verify_password, create_access_token
    user = db.query(UserDB).filter(UserDB.email == data.email).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    token = create_access_token({"sub": user.id})
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "email": user.email, "name": user.name, "role": user.role}}


@app.get("/api/v1/auth/me")
async def get_me_profile(
    credentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db),
):
    from app.auth import decode_token
    from app.models import UserDB
    payload = decode_token(credentials.credentials)
    user = db.query(UserDB).filter(UserDB.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(404, "User not found")
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@app.put("/api/v1/auth/me")
async def update_me(
    data: schemas.UserUpdate,
    credentials = Depends(HTTPBearer()),
    db: Session = Depends(get_db),
):
    from app.auth import decode_token, hash_password, verify_password
    from app.models import UserDB
    payload = decode_token(credentials.credentials)
    user = db.query(UserDB).filter(UserDB.id == payload.get("sub")).first()
    if not user:
        raise HTTPException(404, "User not found")
    if data.name is not None:
        user.name = data.name
    if data.email is not None:
        user.email = data.email
    if data.new_password is not None:
        if not data.current_password or not verify_password(data.current_password, user.hashed_password):
            raise HTTPException(400, "Current password required")
        user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


# ---------------------------------------------------------------------------
# Estimates
# ---------------------------------------------------------------------------

@app.get("/api/v1/estimates", response_model=schemas.EstimateListResponse)
async def list_estimates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    storage = DBStorage(db)
    result = storage.list_estimates(status=status, search=search, page=page, page_size=page_size)
    return {"items": result["items"], "total": result["total"], "page": page, "page_size": page_size}


@app.post("/api/v1/estimates", response_model=schemas.EstimateResponse, status_code=201)
async def create_estimate(data: schemas.EstimateCreate, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    return storage.create_estimate(data.model_dump())


@app.get("/api/v1/estimates/{est_id}", response_model=schemas.EstimateResponse)
async def get_estimate(est_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.get_estimate(est_id)
    if not result:
        raise HTTPException(404, "Estimate not found")
    return result


@app.put("/api/v1/estimates/{est_id}", response_model=schemas.EstimateResponse)
async def update_estimate(est_id: str, data: schemas.EstimateUpdate, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    update_data = data.model_dump(exclude_unset=True)
    if "status" in update_data and update_data["status"] is not None:
        update_data["status"] = update_data["status"].value if hasattr(update_data["status"], "value") else update_data["status"]
    result = storage.update_estimate(est_id, update_data)
    if not result:
        raise HTTPException(404, "Estimate not found")
    return result


@app.delete("/api/v1/estimates/{est_id}", status_code=204)
async def delete_estimate(est_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    if not storage.delete_estimate(est_id):
        raise HTTPException(404, "Estimate not found")
    return Response(status_code=204)


@app.post("/api/v1/estimates/{est_id}/calculate")
async def calculate_estimate_endpoint(est_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.get_estimate(est_id)
    if not result:
        raise HTTPException(404, "Estimate not found")
    storage.update_estimate(est_id, {})
    return storage.get_estimate(est_id)


@app.post("/api/v1/estimates/{est_id}/duplicate")
async def duplicate_estimate(est_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.duplicate_estimate(est_id)
    if not result:
        raise HTTPException(404, "Estimate not found")
    return result


@app.get("/api/v1/estimates/{est_id}/pdf")
async def estimate_pdf(est_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.get_estimate(est_id)
    if not result:
        raise HTTPException(404, "Estimate not found")
    pdf_bytes = generate_estimate_pdf(result)
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=estimate_{est_id[:8]}.pdf"})


@app.get("/api/v1/estimates/{est_id}/export/{fmt}")
async def export_estimate(est_id: str, fmt: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    d = storage.get_estimate(est_id)
    if not d:
        raise HTTPException(404, "Estimate not found")
    sections = []
    for s in d.get("sections", []):
        positions = [
            CalcPosition(id=p["id"], code=p["code"], name=p["name"], unit=p["unit"],
                         quantity=p["quantity"], price=p["price"],
                         source=p.get("source", ""), comment=p.get("comment", ""),
                         sum=p.get("sum", "0"))
            for p in s["positions"]
        ]
        sections.append(CalcSection(id=s["id"], title=s["title"], positions=positions))
    calc = CalcEstimate(
        id=d["id"], title=d["title"], status=EstimateStatus(d.get("status", "draft")),
        sections=sections, overhead_rate=d.get("overhead_rate", "0"),
        vat_rate=d.get("vat_rate", "20"),
    )
    calc = calculate_estimate(calc)
    if fmt == "csv":
        content = export_to_csv(calc)
        return Response(content=content, media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=estimate_{est_id[:8]}.csv"})
    elif fmt == "json":
        return export_to_json(calc)
    elif fmt == "xlsx":
        from app.xlsx_export import generate_estimate_xlsx
        xlsx_bytes = generate_estimate_xlsx(d)
        return Response(content=xlsx_bytes,
                        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f"attachment; filename=estimate_{est_id[:8]}.xlsx"})
    raise HTTPException(400, f"Unsupported format: {fmt}")


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents")
async def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    storage = DBStorage(db)
    result = storage.list_documents(type_=type, page=page, page_size=page_size)
    return {"items": result["items"], "total": result["total"], "page": page, "page_size": page_size}


@app.post("/api/v1/documents", status_code=201)
async def create_document(data: schemas.DocumentCreate, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    d = data.model_dump()
    if "type" in d and hasattr(d["type"], "value"):
        d["type"] = d["type"].value
    return storage.create_document(d)


@app.get("/api/v1/documents/{doc_id}")
async def get_document(doc_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.get_document(doc_id)
    if not result:
        raise HTTPException(404, "Document not found")
    return result


@app.put("/api/v1/documents/{doc_id}")
async def update_document(doc_id: str, data: schemas.DocumentUpdate, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    update_data = data.model_dump(exclude_unset=True)
    if "type" in update_data and update_data["type"] is not None and hasattr(update_data["type"], "value"):
        update_data["type"] = update_data["type"].value
    result = storage.update_document(doc_id, update_data)
    if not result:
        raise HTTPException(404, "Document not found")
    return result


@app.delete("/api/v1/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    if not storage.delete_document(doc_id):
        raise HTTPException(404, "Document not found")
    return Response(status_code=204)


@app.get("/api/v1/documents/{doc_id}/pdf")
async def document_pdf(doc_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.get_document(doc_id)
    if not result:
        raise HTTPException(404, "Document not found")
    pdf_bytes = generate_document_pdf(result)
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
    db: Session = Depends(get_db),
):
    storage = DBStorage(db)
    items = storage.list_library(item_type=item_type, search=search)
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
    db: Session = Depends(get_db),
):
    storage = DBStorage(db)
    result = storage.list_agents(status=status, page=page, page_size=page_size)
    return {"items": result["items"], "total": result["total"], "page": page, "page_size": page_size}


@app.post("/api/v1/agents", status_code=201)
async def create_agent(data: dict, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    return storage.create_agent(data)


@app.get("/api/v1/agents/{agent_id}")
async def get_agent(agent_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.get_agent(agent_id)
    if not result:
        raise HTTPException(404, "Agent not found")
    return result


@app.delete("/api/v1/agents/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    if not storage.delete_agent(agent_id):
        raise HTTPException(404, "Agent not found")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

@app.get("/api/v1/nodes")
async def list_nodes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    storage = DBStorage(db)
    result = storage.list_nodes(status=status, page=page, page_size=page_size)
    return {"items": result["items"], "total": result["total"], "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@app.get("/api/v1/tasks")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    state: Optional[str] = None,
    db: Session = Depends(get_db),
):
    storage = DBStorage(db)
    result = storage.list_tasks(state=state, page=page, page_size=page_size)
    return {"items": result["items"], "total": result["total"], "page": page, "page_size": page_size}


# ---------------------------------------------------------------------------
# Control Plane — Cluster stats, agent/node/task actions
# ---------------------------------------------------------------------------

@app.get("/api/v1/cluster/stats")
async def cluster_stats(db: Session = Depends(get_db)):
    storage = DBStorage(db)
    return storage.get_cluster_stats()


@app.get("/api/v1/analytics")
async def analytics(db: Session = Depends(get_db)):
    from app.models import EstimateDB, DocumentDB, AgentDB, TaskDB
    from decimal import Decimal

    estimates = db.query(EstimateDB).all()
    documents = db.query(DocumentDB).all()
    agents = db.query(AgentDB).all()
    tasks = db.query(TaskDB).all()

    # Estimate stats
    total_value = sum(Decimal(e.total or "0") for e in estimates)
    by_status = {}
    for e in estimates:
        by_status[e.status] = by_status.get(e.status, 0) + 1

    # Document stats
    by_type = {}
    for d in documents:
        by_type[d.type] = by_type.get(d.type, 0) + 1

    # Agent stats
    agent_by_status = {}
    for a in agents:
        agent_by_status[a.status] = agent_by_status.get(a.status, 0) + 1

    # Task stats
    task_by_state = {}
    for t in tasks:
        task_by_state[t.state] = task_by_state.get(t.state, 0) + 1

    return {
        "estimates": {
            "total": len(estimates),
            "total_value": str(total_value),
            "by_status": by_status,
        },
        "documents": {
            "total": len(documents),
            "by_type": by_type,
        },
        "agents": {
            "total": len(agents),
            "by_status": agent_by_status,
        },
        "tasks": {
            "total": len(tasks),
            "by_state": task_by_state,
        },
    }


@app.patch("/api/v1/agents/{agent_id}")
async def update_agent(agent_id: str, data: dict, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.update_agent(agent_id, data)
    if not result:
        raise HTTPException(404, "Agent not found")
    return result


@app.patch("/api/v1/nodes/{node_id}")
async def update_node(node_id: str, data: dict, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.update_node(node_id, data)
    if not result:
        raise HTTPException(404, "Node not found")
    return result


@app.patch("/api/v1/tasks/{task_id}")
async def update_task(task_id: str, data: dict, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.update_task(task_id, data)
    if not result:
        raise HTTPException(404, "Task not found")
    return result


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------

@app.post("/api/v1/pdf/generate")
async def generate_pdf(data: schemas.PDFGenerateRequest):
    pdf_bytes = generate_document_pdf({"title": data.title, "content": data.html_content})
    b64 = base64.b64encode(pdf_bytes).decode()
    return {"pdf_base64": b64, "filename": f"{data.title}.pdf",
            "page_count": 1, "size_bytes": len(pdf_bytes)}


# ---------------------------------------------------------------------------
# Chat — Kimi K2.6 AI provider
# ---------------------------------------------------------------------------

@app.post("/api/v1/chat", response_model=schemas.ChatResponse)
async def chat(request: Request, data: schemas.ChatRequest):
    from app.rate_limiter import check_rate_limit, chat_limiter
    await check_rate_limit(request, chat_limiter)
    if not data.messages:
        raise HTTPException(400, "No messages provided")
    from app.ai_provider import chat_completion
    try:
        result = await chat_completion([{"role": m.role, "content": m.content} for m in data.messages])
        return result
    except Exception as e:
        return {
            "content": f"Ошибка AI-провайдера: {str(e)}. Попробуйте позже.",
            "actions": [],
            "status": "error",
        }


@app.post("/api/v1/chat/stream")
async def chat_stream(request: Request, data: schemas.ChatRequest):
    from app.rate_limiter import check_rate_limit, chat_limiter
    await check_rate_limit(request, chat_limiter)
    if not data.messages:
        raise HTTPException(400, "No messages provided")
    from app.ai_provider import chat_completion_stream

    async def event_generator():
        try:
            async for chunk in chat_completion_stream([{"role": m.role, "content": m.content} for m in data.messages]):
                yield f"data: {json.dumps(chunk)}\n\n"
        except Exception as e:
            yield f'data: {json.dumps({"content": f"Ошибка: {str(e)}", "done": True})}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/v1/ai/analyze-estimate")
async def ai_analyze_estimate(est_id: str, db: Session = Depends(get_db)):
    from app.ai_provider import analyze_estimate
    storage = DBStorage(db)
    est = storage.get_estimate(est_id)
    if not est:
        raise HTTPException(404, "Estimate not found")
    try:
        return await analyze_estimate(est)
    except Exception as e:
        return {"content": f"Ошибка AI: {str(e)}", "actions": [], "status": "error"}


@app.post("/api/v1/ai/generate-document")
async def ai_generate_document(data: dict):
    from app.ai_provider import generate_document_content
    doc_type = data.get("type", "custom")
    context = data.get("context", "")
    try:
        return await generate_document_content(doc_type, context)
    except Exception as e:
        return {"content": f"Ошибка AI: {str(e)}", "actions": [], "status": "error"}


@app.post("/api/v1/ai/suggest")
async def ai_suggest(data: dict):
    from app.ai_provider import suggest_search
    query = data.get("query", "")
    if not query:
        raise HTTPException(400, "Query required")
    try:
        return await suggest_search(query)
    except Exception as e:
        return {"content": f"Ошибка AI: {str(e)}", "actions": [], "status": "error"}


# ---------------------------------------------------------------------------
# Providers — registry, healthcheck, capabilities
# ---------------------------------------------------------------------------

@app.get("/api/v1/providers")
async def list_providers_endpoint():
    from app.providers import list_providers
    return list_providers()


@app.get("/api/v1/providers/{provider_id}")
async def get_provider_endpoint(provider_id: str):
    from app.providers import get_provider
    p = get_provider(provider_id)
    if not p:
        raise HTTPException(404, "Provider not found")
    return {
        "id": p.id, "name": p.name, "base_url": p.base_url,
        "protocol": p.protocol, "official": p.official, "custom_proxy": p.custom_proxy,
        "model": p.default_model, "has_key": bool(p.api_key),
        "capabilities": {
            "chat": p.capabilities.chat, "models": p.capabilities.models,
            "streaming": p.capabilities.streaming, "tools": p.capabilities.tools,
            "json_schema": p.capabilities.json_schema, "files": p.capabilities.files,
            "batch": p.capabilities.batch,
        },
    }


@app.post("/api/v1/providers/{provider_id}/healthcheck")
async def healthcheck_provider(provider_id: str):
    from app.healthcheck import probe_provider
    return await probe_provider(provider_id)


@app.post("/api/v1/providers/test-all")
async def test_all_providers():
    """Test all providers and return results."""
    from app.ai_provider import PROVIDERS
    results = {}
    for name, provider in PROVIDERS.items():
        try:
            import httpx
            headers = {"Content-Type": "application/json"}
            if provider["key"]:
                headers["Authorization"] = f"Bearer {provider['key']}"
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    provider["url"],
                    json={"model": provider["model"], "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5},
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    msg = data["choices"][0]["message"]
                    content = msg.get("content") or msg.get("reasoning_content") or ""
                    results[name] = {"status": "ok", "model": provider["model"], "response": content[:50]}
                else:
                    results[name] = {"status": "error", "model": provider["model"], "error": resp.text[:100]}
        except Exception as e:
            results[name] = {"status": "error", "model": provider["model"], "error": str(e)[:100]}
    return results


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
@app.get("/api/v1/templates")
async def list_templates():
    from app.templates import list_templates as _list
    return _list()


@app.get("/api/v1/templates/{template_id}")
async def get_template(template_id: str):
    from app.templates import get_template as _get
    t = _get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    return t


@app.post("/api/v1/templates/{template_id}/create-document", status_code=201)
async def create_document_from_template(template_id: str, db: Session = Depends(get_db)):
    from app.templates import get_template as _get
    t = _get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    storage = DBStorage(db)
    return storage.create_document({
        "title": t["title"], "type": t["type"], "content": t["content"],
    })


@app.post("/api/v1/templates/{template_id}/render")
async def render_template_endpoint(template_id: str, data: dict):
    from app.templates import get_template as _get, render_template as _render
    t = _get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    variables = data.get("variables", {})
    rendered = _render(t["content"], variables)
    return {"title": t["title"], "content": rendered, "variables": t["variables"]}


# ---------------------------------------------------------------------------
# Price Catalog
# ---------------------------------------------------------------------------

@app.get("/api/v1/catalog")
async def list_catalog(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    region: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from app.models import CatalogItemDB
    q = db.query(CatalogItemDB)
    if category:
        q = q.filter(CatalogItemDB.category == category)
    if region:
        q = q.filter(CatalogItemDB.region == region)
    if search:
        q = q.filter(CatalogItemDB.name.ilike(f"%{search}%"))
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [{"id": i.id, "code": i.code, "name": i.name, "unit": i.unit,
                   "price": i.price, "category": i.category, "region": i.region,
                   "source": i.source} for i in items],
        "total": total, "page": page, "page_size": page_size,
    }


@app.get("/api/v1/catalog/categories")
async def list_catalog_categories(db: Session = Depends(get_db)):
    from app.models import CatalogItemDB
    from sqlalchemy import func
    cats = db.query(CatalogItemDB.category, func.count()).group_by(CatalogItemDB.category).order_by(func.count().desc()).all()
    return [{"category": c, "count": n} for c, n in cats]


@app.get("/api/v1/catalog/stats")
async def catalog_stats(db: Session = Depends(get_db)):
    from app.models import CatalogItemDB
    from sqlalchemy import func
    total = db.query(CatalogItemDB).count()
    regions = db.query(CatalogItemDB.region, func.count()).group_by(CatalogItemDB.region).all()
    cats = db.query(CatalogItemDB.category, func.count()).group_by(CatalogItemDB.category).order_by(func.count().desc()).all()
    return {
        "total": total,
        "regions": len(regions),
        "categories": len(cats),
        "by_region": {r: c for r, c in regions},
        "top_categories": [{"category": c, "count": n} for c, n in cats[:20]],
    }


# ---------------------------------------------------------------------------
# DOCX export
# ---------------------------------------------------------------------------

@app.get("/api/v1/documents/{doc_id}/docx")
async def document_docx(doc_id: str, db: Session = Depends(get_db)):
    storage = DBStorage(db)
    result = storage.get_document(doc_id)
    if not result:
        raise HTTPException(404, "Document not found")
    from app.docx_export import html_to_docx
    docx_bytes = html_to_docx(result["title"], result["content"])
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename=document_{doc_id[:8]}.docx'},
    )


@app.post("/api/v1/pdf/generate-docx")
async def generate_docx(data: schemas.PDFGenerateRequest):
    from app.docx_export import html_to_docx
    docx_bytes = html_to_docx(data.title, data.html_content)
    import base64
    b64 = base64.b64encode(docx_bytes).decode()
    return {"docx_base64": b64, "filename": f"{data.title}.docx", "size_bytes": len(docx_bytes)}


# ---------------------------------------------------------------------------
# Web Search
# ---------------------------------------------------------------------------

@app.post("/api/v1/search/web")
async def web_search_endpoint(data: dict):
    from app.web_search import search_and_summarize
    query = data.get("query", "")
    if not query:
        raise HTTPException(400, "Query required")
    return {"query": query, "results": await search_and_summarize(query)}


# ---------------------------------------------------------------------------
# Deterministic Search
# ---------------------------------------------------------------------------

@app.post("/api/v1/search")
async def search_endpoint(data: dict, db: Session = Depends(get_db)):
    from app.search_engine import SearchEngine
    query = data.get("query", "")
    if not query:
        raise HTTPException(400, "Query required")
    entity_types = data.get("types")
    limit = data.get("limit", 20)
    engine = SearchEngine(db)
    return engine.search_with_context(query, entity_types)


# ---------------------------------------------------------------------------
# Client Context
# ---------------------------------------------------------------------------

@app.get("/api/v1/context/{client_id}")
async def get_context(client_id: str):
    from app.context_manager import context_manager
    ctx = context_manager.get_context(client_id)
    if not ctx:
        return {"client_id": client_id, "exists": False}
    return {
        "client_id": ctx.client_id,
        "client_name": ctx.client_name,
        "project": ctx.project,
        "region": ctx.region,
        "estimates_count": len(ctx.estimates),
        "documents_count": len(ctx.documents),
        "conversations_count": len(ctx.conversations),
        "preferences": ctx.preferences,
        "last_updated": ctx.last_updated,
    }


@app.post("/api/v1/context/{client_id}")
async def update_context(client_id: str, data: dict):
    from app.context_manager import context_manager
    ctx = context_manager.update_context(client_id, data)
    return {"status": "ok", "client_id": ctx.client_id}


@app.post("/api/v1/context/{client_id}/estimate")
async def add_estimate_to_context(client_id: str, data: dict):
    from app.context_manager import context_manager
    context_manager.add_estimate(client_id, data)
    return {"status": "ok"}


@app.post("/api/v1/context/{client_id}/document")
async def add_document_to_context(client_id: str, data: dict):
    from app.context_manager import context_manager
    context_manager.add_document(client_id, data)
    return {"status": "ok"}


@app.post("/api/v1/context/{client_id}/message")
async def add_message_to_context(client_id: str, data: dict):
    from app.context_manager import context_manager
    context_manager.add_conversation(client_id, data)
    return {"status": "ok"}


@app.get("/api/v1/context/{client_id}/ai-context")
async def get_ai_context(client_id: str):
    from app.context_manager import context_manager
    return {"context": context_manager.build_ai_context(client_id)}
