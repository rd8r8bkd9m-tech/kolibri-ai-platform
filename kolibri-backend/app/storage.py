"""Storage abstraction — DBStorage (SQLAlchemy) and InMemoryStorage (legacy)."""
import uuid
import random
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models import EstimateDB, SectionDB, PositionDB, DocumentDB, AgentDB, NodeDB, TaskDB
from app.calculator import (
    Estimate as CalcEstimate, EstimateSection as CalcSection,
    EstimatePosition as CalcPosition, EstimateStatus,
    calculate_estimate,
)


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


class DBStorage:
    """Persistent storage using SQLAlchemy."""

    def __init__(self, db: Session):
        self.db = db

    # ── Estimates ────────────────────────────────────────────────────────────

    def list_estimates(self, status: Optional[str] = None, search: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        q = self.db.query(EstimateDB)
        if status:
            q = q.filter(EstimateDB.status == status)
        if search:
            s = search.lower()
            q = q.filter(EstimateDB.title.ilike(f"%{s}%"))
        total = q.count()
        items = q.order_by(EstimateDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": [self._est_to_dict(e) for e in items], "total": total}

    def get_estimate(self, est_id: str) -> Optional[dict]:
        e = self.db.query(EstimateDB).filter(EstimateDB.id == est_id).first()
        return self._est_to_dict(e) if e else None

    def create_estimate(self, data: dict) -> dict:
        est_id = _uid()
        now = _now()
        e = EstimateDB(
            id=est_id, title=data.get("title", ""), client=data.get("client", ""),
            object_name=data.get("object_name", ""), region=data.get("region", ""),
            currency=data.get("currency", "RUB"),
            overhead_rate=data.get("overhead_rate", "0"),
            vat_rate=data.get("vat_rate", "20"),
            created_at=now, updated_at=now,
        )
        self.db.add(e)
        for s_data in data.get("sections", []):
            sec_id = _uid()
            s = SectionDB(id=sec_id, estimate_id=est_id, title=s_data.get("title", ""))
            self.db.add(s)
            for p_data in s_data.get("positions", []):
                pos_id = _uid()
                p = PositionDB(
                    id=pos_id, section_id=sec_id,
                    code=p_data.get("code", ""), name=p_data.get("name", ""),
                    unit=p_data.get("unit", "шт"), quantity=p_data.get("quantity", "0"),
                    price=p_data.get("price", "0"), source=p_data.get("source", ""),
                    comment=p_data.get("comment", ""),
                )
                self.db.add(p)
        self.db.commit()
        self._recalc_estimate(est_id)
        return self.get_estimate(est_id)

    def update_estimate(self, est_id: str, data: dict) -> Optional[dict]:
        e = self.db.query(EstimateDB).filter(EstimateDB.id == est_id).first()
        if not e:
            return None
        for field in ["title", "client", "object_name", "region", "currency", "overhead_rate", "vat_rate", "status"]:
            if field in data and data[field] is not None:
                setattr(e, field, data[field])
        if "sections" in data and data["sections"] is not None:
            self.db.query(PositionDB).filter(
                PositionDB.section_id.in_([s.id for s in e.sections])
            ).delete(synchronize_session=False)
            self.db.query(SectionDB).filter(SectionDB.estimate_id == est_id).delete()
            for s_data in data["sections"]:
                sec_id = _uid()
                s = SectionDB(id=sec_id, estimate_id=est_id, title=s_data.get("title", ""))
                self.db.add(s)
                for p_data in s_data.get("positions", []):
                    pos_id = _uid()
                    p = PositionDB(
                        id=pos_id, section_id=sec_id,
                        code=p_data.get("code", ""), name=p_data.get("name", ""),
                        unit=p_data.get("unit", "шт"), quantity=p_data.get("quantity", "0"),
                        price=p_data.get("price", "0"), source=p_data.get("source", ""),
                        comment=p_data.get("comment", ""),
                    )
                    self.db.add(p)
        e.updated_at = _now()
        self.db.commit()
        self._recalc_estimate(est_id)
        return self.get_estimate(est_id)

    def delete_estimate(self, est_id: str) -> bool:
        e = self.db.query(EstimateDB).filter(EstimateDB.id == est_id).first()
        if not e:
            return False
        self.db.delete(e)
        self.db.commit()
        return True

    def duplicate_estimate(self, est_id: str) -> Optional[dict]:
        orig = self.get_estimate(est_id)
        if not orig:
            return None
        new_data = {
            "title": f"{orig['title']} (копия)",
            "client": orig["client"], "object_name": orig["object_name"],
            "region": orig["region"], "currency": orig["currency"],
            "overhead_rate": orig["overhead_rate"], "vat_rate": orig["vat_rate"],
            "sections": [
                {"title": s["title"], "positions": [
                    {k: p[k] for k in ["code", "name", "unit", "quantity", "price", "source", "comment"]}
                    for p in s["positions"]
                ]}
                for s in orig["sections"]
            ],
        }
        return self.create_estimate(new_data)

    def _recalc_estimate(self, est_id: str):
        d = self.get_estimate(est_id)
        if not d:
            return
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
            id=d["id"], title=d["title"],
            status=EstimateStatus(d.get("status", "draft")),
            sections=sections, overhead_rate=d.get("overhead_rate", "0"),
            vat_rate=d.get("vat_rate", "20"),
        )
        calc = calculate_estimate(calc)
        e = self.db.query(EstimateDB).filter(EstimateDB.id == est_id).first()
        if not e:
            return
        e.subtotal = str(calc.subtotal)
        e.overhead_amount = str(calc.overhead_amount)
        e.vat_amount = str(calc.vat_amount)
        e.total = str(calc.total)
        for si, s in enumerate(e.sections):
            cs = calc.sections[si]
            s.subtotal = str(cs.subtotal)
            for pi, p in enumerate(s.positions):
                p.sum = str(cs.positions[pi].sum)
        self.db.commit()

    def _est_to_dict(self, e: EstimateDB) -> dict:
        return {
            "id": e.id, "version": e.version, "status": e.status,
            "title": e.title, "client": e.client, "object_name": e.object_name,
            "region": e.region, "currency": e.currency,
            "overhead_rate": e.overhead_rate, "vat_rate": e.vat_rate,
            "subtotal": e.subtotal, "overhead_amount": e.overhead_amount,
            "vat_amount": e.vat_amount, "total": e.total,
            "created_at": e.created_at.isoformat() + "Z" if e.created_at else "",
            "updated_at": e.updated_at.isoformat() + "Z" if e.updated_at else "",
            "sections": [
                {
                    "id": s.id, "title": s.title, "subtotal": s.subtotal,
                    "positions": [
                        {
                            "id": p.id, "code": p.code, "name": p.name, "unit": p.unit,
                            "quantity": p.quantity, "price": p.price, "sum": p.sum,
                            "source": p.source, "comment": p.comment or "",
                        }
                        for p in s.positions
                    ],
                }
                for s in e.sections
            ],
        }

    # ── Documents ────────────────────────────────────────────────────────────

    def list_documents(self, type_: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        q = self.db.query(DocumentDB)
        if type_:
            q = q.filter(DocumentDB.type == type_)
        total = q.count()
        items = q.order_by(DocumentDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": [self._doc_to_dict(d) for d in items], "total": total}

    def get_document(self, doc_id: str) -> Optional[dict]:
        d = self.db.query(DocumentDB).filter(DocumentDB.id == doc_id).first()
        return self._doc_to_dict(d) if d else None

    def create_document(self, data: dict) -> dict:
        doc_id = _uid()
        now = _now()
        d = DocumentDB(
            id=doc_id, title=data.get("title", ""), type=data.get("type", "custom"),
            client=data.get("client", ""), project=data.get("project", ""),
            content=data.get("content", ""), variables=data.get("variables", {}),
            template=data.get("template", ""),
            estimate_id=data.get("estimate_id"),
            created_at=now, updated_at=now,
        )
        self.db.add(d)
        self.db.commit()
        return self._doc_to_dict(d)

    def update_document(self, doc_id: str, data: dict) -> Optional[dict]:
        d = self.db.query(DocumentDB).filter(DocumentDB.id == doc_id).first()
        if not d:
            return None
        for field in ["title", "type", "client", "project", "content", "variables", "template", "status", "estimate_id"]:
            if field in data and data[field] is not None:
                setattr(d, field, data[field])
        d.updated_at = _now()
        self.db.commit()
        return self._doc_to_dict(d)

    def delete_document(self, doc_id: str) -> bool:
        d = self.db.query(DocumentDB).filter(DocumentDB.id == doc_id).first()
        if not d:
            return False
        self.db.delete(d)
        self.db.commit()
        return True

    def _doc_to_dict(self, d: DocumentDB) -> dict:
        return {
            "id": d.id, "title": d.title, "type": d.type, "status": d.status,
            "client": d.client, "project": d.project, "content": d.content,
            "variables": d.variables or {}, "template": d.template or "",
            "estimate_id": d.estimate_id,
            "created_at": d.created_at.isoformat() + "Z" if d.created_at else "",
            "updated_at": d.updated_at.isoformat() + "Z" if d.updated_at else "",
        }

    # ── Library ──────────────────────────────────────────────────────────────

    def list_library(self, item_type: Optional[str] = None, search: Optional[str] = None) -> List[dict]:
        items = []
        for e in self.db.query(EstimateDB).all():
            items.append({"id": e.id, "title": e.title, "item_type": "estimate",
                          "source_id": e.id, "source_type": "estimate",
                          "status": e.status, "client": e.client or "",
                          "project": e.object_name or "", "file_size": 0,
                          "created_at": e.created_at.isoformat() + "Z" if e.created_at else "",
                          "updated_at": e.updated_at.isoformat() + "Z" if e.updated_at else ""})
        for d in self.db.query(DocumentDB).all():
            items.append({"id": d.id, "title": d.title, "item_type": "document",
                          "source_id": d.id, "source_type": "document",
                          "status": d.status, "client": d.client or "",
                          "project": d.project or "", "file_size": 0,
                          "created_at": d.created_at.isoformat() + "Z" if d.created_at else "",
                          "updated_at": d.updated_at.isoformat() + "Z" if d.updated_at else ""})
        if item_type:
            items = [i for i in items if i["item_type"] == item_type]
        if search:
            s = search.lower()
            items = [i for i in items if s in i["title"].lower()]
        return items

    # ── Agents ───────────────────────────────────────────────────────────────

    def list_agents(self, status: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        q = self.db.query(AgentDB)
        if status:
            q = q.filter(AgentDB.status == status)
        total = q.count()
        items = q.offset((page - 1) * page_size).limit(page_size).all()
        return {"items": [self._agent_to_dict(a) for a in items], "total": total}

    def _agent_to_dict(self, a: AgentDB) -> dict:
        return {
            "id": a.id, "name": a.name, "role": a.role, "status": a.status,
            "node_id": a.node_id, "current_task": a.current_task,
            "progress": a.progress, "model": a.model,
            "capabilities": a.capabilities or {},
            "cost_accumulated": a.cost_accumulated,
            "heartbeat_at": a.heartbeat_at.isoformat() + "Z" if a.heartbeat_at else None,
        }

    def get_agent(self, agent_id: str) -> Optional[dict]:
        a = self.db.query(AgentDB).filter(AgentDB.id == agent_id).first()
        return self._agent_to_dict(a) if a else None

    def create_agent(self, data: dict) -> dict:
        a = AgentDB(
            id=_uid(), name=data.get("name", ""), role=data.get("role", ""),
            status=data.get("status", "idle"), model=data.get("model"),
            capabilities=data.get("capabilities", {}),
        )
        self.db.add(a)
        self.db.commit()
        return self._agent_to_dict(a)

    def delete_agent(self, agent_id: str) -> bool:
        a = self.db.query(AgentDB).filter(AgentDB.id == agent_id).first()
        if not a:
            return False
        self.db.delete(a)
        self.db.commit()
        return True

    # ── Nodes ────────────────────────────────────────────────────────────────

    def list_nodes(self, status: Optional[str] = None, page: int = 1, page_size: int = 50) -> dict:
        q = self.db.query(NodeDB)
        if status:
            q = q.filter(NodeDB.status == status)
        total = q.count()
        items = q.offset((page - 1) * page_size).limit(page_size).all()
        return {"items": [self._node_to_dict(n) for n in items], "total": total}

    def _node_to_dict(self, n: NodeDB) -> dict:
        return {
            "id": n.id, "name": n.name, "region": n.region, "ip_address": n.ip_address,
            "status": n.status, "cpu_percent": n.cpu_percent, "ram_percent": n.ram_percent,
            "disk_percent": n.disk_percent, "network_mbps": n.network_mbps,
            "agent_count": n.agent_count, "task_count": n.task_count,
            "ping_ms": n.ping_ms, "max_agents": n.max_agents,
            "capabilities": n.capabilities or {},
        }

    # ── Tasks ────────────────────────────────────────────────────────────────

    def list_tasks(self, state: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        q = self.db.query(TaskDB)
        if state:
            q = q.filter(TaskDB.state == state)
        total = q.count()
        items = q.offset((page - 1) * page_size).limit(page_size).all()
        return {"items": [self._task_to_dict(t) for t in items], "total": total}

    def _task_to_dict(self, t: TaskDB) -> dict:
        return {
            "id": t.id, "workflow_id": t.workflow_id, "state": t.state,
            "priority": t.priority, "owner_agent_id": t.owner_agent_id,
            "node_id": t.node_id, "budget_limit": t.budget_limit,
            "attempts": t.attempts, "max_retries": t.max_retries,
            "result": t.result,
            "created_at": t.created_at.isoformat() + "Z" if t.created_at else "",
            "updated_at": t.updated_at.isoformat() + "Z" if t.updated_at else "",
        }

    # ── Control Plane: Agent actions ─────────────────────────────────────────

    def update_agent(self, agent_id: str, data: dict) -> Optional[dict]:
        a = self.db.query(AgentDB).filter(AgentDB.id == agent_id).first()
        if not a:
            return None
        for field in ["status", "current_task", "progress", "node_id"]:
            if field in data and data[field] is not None:
                setattr(a, field, data[field])
        a.heartbeat_at = _now()
        self.db.commit()
        return self._agent_to_dict(a)

    def update_node(self, node_id: str, data: dict) -> Optional[dict]:
        n = self.db.query(NodeDB).filter(NodeDB.id == node_id).first()
        if not n:
            return None
        for field in ["status", "cpu_percent", "ram_percent", "disk_percent", "network_mbps", "agent_count", "task_count", "ping_ms"]:
            if field in data and data[field] is not None:
                setattr(n, field, data[field])
        self.db.commit()
        return self._node_to_dict(n)

    def update_task(self, task_id: str, data: dict) -> Optional[dict]:
        t = self.db.query(TaskDB).filter(TaskDB.id == task_id).first()
        if not t:
            return None
        for field in ["state", "priority", "owner_agent_id", "node_id", "result"]:
            if field in data and data[field] is not None:
                setattr(t, field, data[field])
        t.updated_at = _now()
        self.db.commit()
        return self._task_to_dict(t)

    def get_cluster_stats(self) -> dict:
        nodes = self.db.query(NodeDB).all()
        agents = self.db.query(AgentDB).all()
        tasks = self.db.query(TaskDB).all()
        healthy = [n for n in nodes if n.status == "healthy"]
        return {
            "nodes": {
                "total": len(nodes),
                "healthy": len(healthy),
                "degraded": len([n for n in nodes if n.status == "degraded"]),
                "offline": len([n for n in nodes if n.status == "offline"]),
            },
            "agents": {
                "total": len(agents),
                "active": len([a for a in agents if a.status == "active"]),
                "idle": len([a for a in agents if a.status == "idle"]),
                "paused": len([a for a in agents if a.status == "paused"]),
            },
            "tasks": {
                "total": len(tasks),
                "running": len([t for t in tasks if t.state == "running"]),
                "queued": len([t for t in tasks if t.state == "queued"]),
                "completed": len([t for t in tasks if t.state == "completed"]),
                "failed": len([t for t in tasks if t.state == "failed"]),
            },
            "resources": {
                "avg_cpu": round(sum(float(n.cpu_percent or 0) for n in healthy) / len(healthy), 1) if healthy else 0,
                "avg_ram": round(sum(float(n.ram_percent or 0) for n in healthy) / len(healthy), 1) if healthy else 0,
                "avg_disk": round(sum(float(n.disk_percent or 0) for n in healthy) / len(healthy), 1) if healthy else 0,
            },
        }


def seed_db(db: Session):
    """Seed database with sample data (same as legacy Store._seed)."""
    if db.query(EstimateDB).count() > 0:
        return

    storage = DBStorage(db)

    storage.create_estimate({
        "title": "Смета на электромонтаж дома 120 м²",
        "client": "Иванов И.И.", "object_name": "Дом 120 м², д. Примерное",
        "region": "Московская область", "overhead_rate": "15", "vat_rate": "20",
        "sections": [
            {"title": "Электромонтажные работы", "positions": [
                {"code": "ЭМ-01-001", "name": "Прокладка кабеля ВВГнг 3x2.5", "unit": "м", "quantity": "150", "price": "85.50", "source": "СНиП"},
                {"code": "ЭМ-01-002", "name": "Монтаж розетки", "unit": "шт", "quantity": "25", "price": "450.00", "source": "Прайс"},
                {"code": "ЭМ-01-003", "name": "Установка автомата 16А", "unit": "шт", "quantity": "12", "price": "320.00", "source": "Прайс"},
                {"code": "ЭМ-01-004", "name": "Сборка электрощита", "unit": "компл", "quantity": "1", "price": "8500.00", "source": "СМЕТА", "comment": "Щит автоматики"},
            ]},
            {"title": "Сантехнические работы", "positions": [
                {"code": "СТ-02-001", "name": "Установка смесителя", "unit": "шт", "quantity": "4", "price": "1200.00", "source": "Прайс"},
                {"code": "СТ-02-002", "name": "Прокладка трубы ППР 25мм", "unit": "м", "quantity": "35", "price": "180.00", "source": "СНиП"},
            ]},
            {"title": "Отделочные работы", "positions": [
                {"code": "ОТ-03-001", "name": "Штукатурка стен", "unit": "м²", "quantity": "280", "price": "350.00", "source": "СМЕТА"},
                {"code": "ОТ-03-002", "name": "Покраска потолка", "unit": "м²", "quantity": "120", "price": "220.00", "source": "Прайс"},
                {"code": "ОТ-03-003", "name": "Укладка плитки", "unit": "м²", "quantity": "45", "price": "850.00", "source": "Прайс"},
            ]},
        ],
    })

    for i, (title, client, obj) in enumerate([
        ("Смета на ремонт офиса 80 м²", "ООО ТехноСервис", "Офис 80 м², Москва"),
        ("Смета на монтаж Видеонаблюдения", "ООО Безопасность", "Склад 500 м²"),
        ("Смета на реконструкцию фасада", "ИП Петров", "Дом 200 м², СПб"),
    ], 2):
        storage.create_estimate({
            "title": title, "client": client, "object_name": obj,
            "region": "Москва" if "Моск" in obj else "Санкт-Петербург",
            "sections": [{"title": "Основные работы", "positions": [
                {"code": f"П{i:02d}-001", "name": "Позиция 1", "unit": "м", "quantity": "100", "price": "150.00"},
                {"code": f"П{i:02d}-002", "name": "Позиция 2", "unit": "шт", "quantity": "10", "price": "500.00"},
            ]}],
        })

    from app.templates import TEMPLATES

    for i, (title, dtype) in enumerate([
        ("Договор подряда №45/2024", "contract"),
        ("Акт выполненных работ", "act"),
        ("Коммерческое предложение", "proposal"),
        ("Технический отчёт", "report"),
    ]):
        tmpl = TEMPLATES.get(dtype, {})
        storage.create_document({
            "title": title, "type": dtype,
            "client": f"Клиент {i+1}", "project": f"Проект {i+1}",
            "content": tmpl.get("content", f"<h1>{title}</h1><p>Содержание документа...</p>"),
            "variables": {"client_name": f"Клиент {i+1}", "date": "25.06.2024"},
        })

    agent_roles = [
        ("Сметчик-аналитик", "estimate_analyst", "active"),
        ("Документолог", "document_writer", "active"),
        ("Code Reviewer", "code_reviewer", "idle"),
        ("Тестировщик", "tester", "active"),
        ("DevOps агент", "devops", "paused"),
        ("FormulaLM Trainer", "ml_trainer", "active"),
    ]
    for i, (name, role, status) in enumerate(agent_roles):
        a = AgentDB(
            id=_uid(), name=name, role=role, status=status,
            current_task=f"Задача {i+1}" if status == "active" else None,
            progress=(i + 1) * 15, model="gpt-4" if i < 3 else "claude",
            cost_accumulated=str((i+1) * 1250),
        )
        db.add(a)

    for i in range(1, 21):
        random.seed(i)
        statuses = ["healthy"] * 15 + ["degraded"] * 3 + ["offline"] * 2
        n = NodeDB(
            id=_uid(), name=f"node-{i:02d}",
            region=random.choice(["msk", "spb", "nsk", "kzn"]),
            ip_address=f"10.77.{1 + i // 256}.{i % 256}",
            status=statuses[i - 1],
            cpu_percent=str(random.randint(10, 85)),
            ram_percent=str(random.randint(20, 75)),
            disk_percent=str(random.randint(30, 90)),
            network_mbps=str(random.randint(50, 1000)),
            agent_count=random.randint(0, 20),
            task_count=random.randint(0, 50),
            ping_ms=random.randint(5, 150),
        )
        db.add(n)

    for i in range(20):
        random.seed(i)
        t = TaskDB(
            id=_uid(), workflow_id=f"wf-{i+1}",
            state=random.choice(["queued", "running", "completed", "failed"]),
            priority=random.randint(1, 5),
            budget_limit=str(random.randint(100, 5000)),
            attempts=random.randint(0, 2),
        )
        db.add(t)

    db.commit()
