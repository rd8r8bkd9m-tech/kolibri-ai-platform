from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
import json

router = APIRouter()
ESTIMATE_STORE = Path("/opt/kolibri-ai/data/v1_estimates.json")
TWOPLACES = Decimal("0.01")

KOLIBRI_SYSTEM_PROMPT = (
    "Ты — Kolibri AI, большая языковая модель. " +
    "Отвечай на языке пользователя. Не используй эмодзи."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _money(value: str | int | float | Decimal | None) -> Decimal:
    try:
        return Decimal(str(value if value not in (None, "") else "0").replace(",", ".")).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


class PositionIn(BaseModel):
    code: str = ""
    name: str = ""
    unit: str = "шт"
    quantity: str = "1"
    price: str = "0"
    source: str = ""
    comment: str = ""


class Position(PositionIn):
    id: str = Field(default_factory=lambda: f"pos_{uuid4().hex[:10]}")
    sum: str = "0.00"


class SectionIn(BaseModel):
    title: str = "Раздел"
    positions: list[PositionIn | Position] = Field(default_factory=list)


class Section(BaseModel):
    id: str = Field(default_factory=lambda: f"sec_{uuid4().hex[:10]}")
    title: str = "Раздел"
    subtotal: str = "0.00"
    positions: list[Position] = Field(default_factory=list)


class EstimateIn(BaseModel):
    title: str = "Новая смета"
    status: Literal["draft", "ready", "approved", "archived"] = "draft"
    client: str = ""
    object_name: str = ""
    region: str = "Москва"
    currency: str = "RUB"
    overhead_rate: str = "0"
    vat_rate: str = "20"
    sections: list[SectionIn | Section] = Field(default_factory=list)


class Estimate(EstimateIn):
    id: str = Field(default_factory=lambda: f"EST-{uuid4().hex[:8].upper()}")
    version: int = 1
    subtotal: str = "0.00"
    overhead_amount: str = "0.00"
    vat_amount: str = "0.00"
    total: str = "0.00"
    sections: list[Section] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


def _load_estimates() -> dict[str, dict]:
    if not ESTIMATE_STORE.exists():
        return {}
    try:
        return json.loads(ESTIMATE_STORE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_estimates(items: dict[str, dict]) -> None:
    ESTIMATE_STORE.parent.mkdir(parents=True, exist_ok=True)
    ESTIMATE_STORE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _position_from_any(raw: PositionIn | Position | dict) -> Position:
    data = raw.model_dump() if isinstance(raw, BaseModel) else dict(raw)
    position = Position(**data)
    position.quantity = str(_money(position.quantity))
    position.price = str(_money(position.price))
    position.sum = str(_money(_money(position.quantity) * _money(position.price)))
    return position


def _section_from_any(raw: SectionIn | Section | dict) -> Section:
    data = raw.model_dump() if isinstance(raw, BaseModel) else dict(raw)
    section = Section(id=data.get("id") or f"sec_{uuid4().hex[:10]}", title=data.get("title") or "Раздел")
    section.positions = [_position_from_any(item) for item in data.get("positions", [])]
    section.subtotal = str(_money(sum((_money(item.sum) for item in section.positions), Decimal("0"))))
    return section


def _recalculate(estimate: Estimate) -> Estimate:
    estimate.sections = [_section_from_any(section) for section in estimate.sections]
    subtotal = _money(sum((_money(section.subtotal) for section in estimate.sections), Decimal("0")))
    overhead = _money(subtotal * _money(estimate.overhead_rate) / Decimal("100"))
    vat = _money((subtotal + overhead) * _money(estimate.vat_rate) / Decimal("100"))
    estimate.subtotal = str(subtotal)
    estimate.overhead_rate = str(_money(estimate.overhead_rate))
    estimate.overhead_amount = str(overhead)
    estimate.vat_rate = str(_money(estimate.vat_rate))
    estimate.vat_amount = str(vat)
    estimate.total = str(_money(subtotal + overhead + vat))
    estimate.updated_at = _now()
    return estimate


def _seed_estimate() -> Estimate:
    return _recalculate(Estimate(
        title="Смета на электромонтаж квартиры",
        status="ready",
        client="ООО Заказчик",
        object_name="Квартира 60 м2",
        region="Москва",
        overhead_rate="7",
        vat_rate="20",
        sections=[
            Section(title="Проектирование и подготовка", positions=[
                Position(code="01-001", name="Выезд инженера и обследование объекта", unit="усл.", quantity="1", price="3500", source="Колибри AI"),
                Position(code="01-002", name="Схема щита и групповых линий", unit="компл.", quantity="1", price="8500", source="Колибри AI"),
            ]),
            Section(title="Кабельные линии", positions=[
                Position(code="02-001", name="Прокладка кабеля ВВГнг-LS 3x2.5", unit="м", quantity="120", price="180", source="рыночная ставка"),
                Position(code="02-002", name="Кабель ВВГнг-LS 3x2.5", unit="м", quantity="120", price="105", source="прайс поставщика"),
                Position(code="02-003", name="Гофра ПВХ с протяжкой", unit="м", quantity="120", price="34", source="прайс поставщика"),
            ]),
            Section(title="Розетки, свет, щит", positions=[
                Position(code="03-001", name="Монтаж подрозетника в бетоне", unit="шт", quantity="36", price="420", source="рыночная ставка"),
                Position(code="03-002", name="Розетка / выключатель Schneider Atlas", unit="шт", quantity="36", price="390", source="прайс поставщика"),
                Position(code="03-003", name="Сборка распределительного щита до 36 модулей", unit="шт", quantity="1", price="14500", source="рыночная ставка"),
            ]),
        ],
    ))


def _ensure_estimates() -> dict[str, dict]:
    items = _load_estimates()
    if items:
        return items
    seed = _seed_estimate()
    items[seed.id] = seed.model_dump(mode="json")
    _save_estimates(items)
    return items


def _estimate_or_404(estimate_id: str) -> Estimate:
    row = _ensure_estimates().get(estimate_id)
    if not row:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return _recalculate(Estimate(**row))

@router.get("/api/v1/ai/models")
async def get_models():
    return {"models": [{"name": "mimo-auto", "description": "Auto mode"}], "system_prompt": KOLIBRI_SYSTEM_PROMPT}

@router.get("/api/v1/model/stats")
async def get_model_stats():
    return {"status": "ok", "models": ["mimo-auto"], "active": "mimo-auto"}


@router.get("/api/v1/health")
async def v1_health():
    return {"status": "ok", "service": "kolibri-v1", "estimates": len(_ensure_estimates())}


@router.get("/api/v1/estimates")
async def list_estimates(page: int = 1, page_size: int = 50, status: str | None = None, search: str | None = None):
    items = [_recalculate(Estimate(**item)) for item in _ensure_estimates().values()]
    if status:
        items = [item for item in items if item.status == status]
    if search:
        needle = search.lower()
        items = [
            item for item in items
            if needle in item.title.lower()
            or needle in item.client.lower()
            or needle in item.object_name.lower()
        ]
    items.sort(key=lambda item: item.updated_at, reverse=True)
    start = max(page - 1, 0) * page_size
    page_items = items[start:start + page_size]
    return {
        "items": [item.model_dump(mode="json") for item in page_items],
        "total": len(items),
        "page": page,
        "page_size": page_size,
    }


@router.post("/api/v1/estimates")
async def create_estimate(payload: EstimateIn):
    items = _ensure_estimates()
    estimate = _recalculate(Estimate(**payload.model_dump()))
    if not estimate.sections:
        estimate.sections = [Section(title="Раздел 1")]
    estimate = _recalculate(estimate)
    items[estimate.id] = estimate.model_dump(mode="json")
    _save_estimates(items)
    return estimate.model_dump(mode="json")


@router.get("/api/v1/estimates/{estimate_id}")
async def get_estimate(estimate_id: str):
    return _estimate_or_404(estimate_id).model_dump(mode="json")


@router.put("/api/v1/estimates/{estimate_id}")
async def update_estimate(estimate_id: str, payload: EstimateIn):
    items = _ensure_estimates()
    current = _estimate_or_404(estimate_id)
    estimate = Estimate(
        **payload.model_dump(),
        id=current.id,
        version=current.version + 1,
        created_at=current.created_at,
    )
    estimate = _recalculate(estimate)
    items[estimate.id] = estimate.model_dump(mode="json")
    _save_estimates(items)
    return estimate.model_dump(mode="json")


@router.delete("/api/v1/estimates/{estimate_id}", status_code=204)
async def delete_estimate(estimate_id: str):
    items = _ensure_estimates()
    if estimate_id not in items:
        raise HTTPException(status_code=404, detail="Estimate not found")
    del items[estimate_id]
    _save_estimates(items)
    return Response(status_code=204)


@router.post("/api/v1/estimates/{estimate_id}/calculate")
async def calculate_estimate(estimate_id: str):
    items = _ensure_estimates()
    estimate = _estimate_or_404(estimate_id)
    items[estimate.id] = estimate.model_dump(mode="json")
    _save_estimates(items)
    return estimate.model_dump(mode="json")


@router.post("/api/v1/estimates/{estimate_id}/duplicate")
async def duplicate_estimate(estimate_id: str):
    items = _ensure_estimates()
    original = _estimate_or_404(estimate_id)
    duplicate = original.model_copy(deep=True)
    duplicate.id = f"EST-{uuid4().hex[:8].upper()}"
    duplicate.title = f"{original.title} - копия"
    duplicate.status = "draft"
    duplicate.version = 1
    duplicate.created_at = _now()
    duplicate.updated_at = _now()
    duplicate = _recalculate(duplicate)
    items[duplicate.id] = duplicate.model_dump(mode="json")
    _save_estimates(items)
    return duplicate.model_dump(mode="json")


@router.get("/api/v1/estimates/{estimate_id}/export/{fmt}")
async def export_estimate(estimate_id: str, fmt: Literal["csv", "json"]):
    estimate = _estimate_or_404(estimate_id)
    if fmt == "json":
        return estimate.model_dump(mode="json")
    rows = ["section,code,name,unit,quantity,price,sum,source,comment"]
    for section in estimate.sections:
        for position in section.positions:
            values = [
                section.title,
                position.code,
                position.name,
                position.unit,
                position.quantity,
                position.price,
                position.sum,
                position.source,
                position.comment,
            ]
            rows.append(",".join(f'"{str(value).replace(chr(34), chr(34) + chr(34))}"' for value in values))
    return Response("\n".join(rows), media_type="text/csv; charset=utf-8")


@router.get("/api/v1/estimates/{estimate_id}/pdf")
async def estimate_pdf(estimate_id: str):
    estimate = _estimate_or_404(estimate_id)
    body = "\n".join([
        estimate.title,
        f"Client: {estimate.client}",
        f"Object: {estimate.object_name}",
        f"Total: {estimate.total} {estimate.currency}",
    ])
    return Response(body, media_type="text/plain; charset=utf-8")


@router.post("/api/v1/ai/analyze-estimate")
async def analyze_estimate(est_id: str):
    estimate = _estimate_or_404(est_id)
    empty = sum(1 for section in estimate.sections for position in section.positions if not position.name.strip())
    zero = sum(1 for section in estimate.sections for position in section.positions if _money(position.quantity) <= 0 or _money(position.price) <= 0)
    content = (
        f"Проверено разделов: {len(estimate.sections)}. Позиций: "
        f"{sum(len(section.positions) for section in estimate.sections)}. "
        f"Итог: {estimate.total} {estimate.currency}. "
        f"Пустых названий: {empty}; нулевых количеств или цен: {zero}."
    )
    return {"content": content, "reasoning": "server-side estimate audit", "actions": [], "status": "ok"}


@router.post("/api/v1/ai/fix-estimate")
async def fix_estimate(est_id: str):
    items = _ensure_estimates()
    estimate = _estimate_or_404(est_id)
    changes = []
    for section in estimate.sections:
        for position in section.positions:
            if _money(position.quantity) <= 0:
                changes.append({"type": "quantity", "position": position.name or position.code, "old": position.quantity, "new": "1.00", "reason": "количество должно быть положительным"})
                position.quantity = "1.00"
            if _money(position.price) < 0:
                changes.append({"type": "price", "position": position.name or position.code, "old": position.price, "new": "0.00", "reason": "цена не может быть отрицательной"})
                position.price = "0.00"
            if not position.name.strip():
                changes.append({"type": "name", "position": position.code or "новая позиция", "old": "", "new": "Новая позиция", "reason": "позиция должна иметь название"})
                position.name = "Новая позиция"
    estimate = _recalculate(estimate)
    items[estimate.id] = estimate.model_dump(mode="json")
    _save_estimates(items)
    return {"estimate": estimate.model_dump(mode="json"), "changes": changes}

@router.post("/api/v1/ai/chat")
async def chat(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    result = await manager.generate(messages=messages, provider="mimo")
    return result

@router.post("/api/v1/ai/chat/stream")
async def chat_stream(request: Request):
    from providers import AIProviderManager
    manager = AIProviderManager()
    body = await request.json()
    messages = body.get("messages", [])
    result = await manager.generate(messages=messages, provider="mimo")
    async def generate():
        yield f"data: {json.dumps(result)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")

@router.post("/api/v1/ai/imagine")
async def imagine():
    return {"status": "ok", "message": "Image generation coming soon"}

@router.post("/api/v1/ai/vision/analyze")
async def vision():
    return {"status": "ok", "message": "Vision analysis coming soon"}

@router.post("/api/v1/ai/demo/learn/text")
async def learn():
    return {"status": "ok", "message": "Learning coming soon"}

@router.get("/api/v1/ai/quality/benchmark/history")
async def benchmark():
    return {"history": []}

@router.get("/api/v1/swarm/runtime/status")
async def swarm_status():
    return {"status": "active", "nodes": 4}

@router.get("/api/v1/ai/training/queue/status")
async def training_status():
    return {"queue": []}

@router.post("/api/v1/swarm/runtime/start")
async def swarm_start():
    return {"status": "started"}

@router.post("/api/v1/swarm/runtime/refresh")
async def swarm_refresh():
    return {"status": "refreshed"}

@router.post("/api/v1/swarm/runtime/run")
async def swarm_run():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/text")
async def ingest_text():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/ingest/url")
async def ingest_url():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/export")
async def kpack_export():
    return {"status": "ok"}

@router.post("/api/v1/swarm/runtime/kpack/import")
async def kpack_import():
    return {"status": "ok"}
