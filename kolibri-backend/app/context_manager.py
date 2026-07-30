"""Context manager — stores client context, documents, and conversation history."""
import os
import json
import hashlib
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.orm import Session as SASession

from app.database import Base, SessionLocal


@dataclass
class ClientContext:
    """Full client context for AI interactions."""
    client_id: str
    client_name: str = ""
    project: str = ""
    region: str = ""
    estimates: List[Dict] = field(default_factory=list)
    documents: List[Dict] = field(default_factory=list)
    conversations: List[Dict] = field(default_factory=list)
    preferences: Dict = field(default_factory=dict)
    last_updated: str = ""


class ContextDB(Base):
    __tablename__ = "contexts"

    client_id = Column(String, primary_key=True)
    client_name = Column(String, default="")
    project = Column(String, default="")
    region = Column(String, default="")
    estimates = Column(Text, default="[]")
    documents = Column(Text, default="[]")
    conversations = Column(Text, default="[]")
    preferences = Column(Text, default="{}")
    last_updated = Column(String, default="")


class ContextManager:
    """Manages client context for AI interactions with SQLite persistence."""

    def __init__(self):
        self._contexts: Dict[str, ClientContext] = {}
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self._load_from_db()
            self._loaded = True

    def _load_from_db(self):
        try:
            db = SessionLocal()
            try:
                rows = db.query(ContextDB).all()
                for row in rows:
                    ctx = ClientContext(
                        client_id=row.client_id,
                        client_name=row.client_name or "",
                        project=row.project or "",
                        region=row.region or "",
                        estimates=json.loads(row.estimates or "[]"),
                        documents=json.loads(row.documents or "[]"),
                        conversations=json.loads(row.conversations or "[]"),
                        preferences=json.loads(row.preferences or "{}"),
                        last_updated=row.last_updated or "",
                    )
                    self._contexts[row.client_id] = ctx
            finally:
                db.close()
        except Exception:
            pass

    def _save_to_db(self, client_id: str):
        ctx = self._contexts.get(client_id)
        if not ctx:
            return
        try:
            db = SessionLocal()
            try:
                existing = db.query(ContextDB).filter(ContextDB.client_id == client_id).first()
                if existing:
                    existing.client_name = ctx.client_name
                    existing.project = ctx.project
                    existing.region = ctx.region
                    existing.estimates = json.dumps(ctx.estimates, ensure_ascii=False)
                    existing.documents = json.dumps(ctx.documents, ensure_ascii=False)
                    existing.conversations = json.dumps(ctx.conversations, ensure_ascii=False)
                    existing.preferences = json.dumps(ctx.preferences, ensure_ascii=False)
                    existing.last_updated = ctx.last_updated
                else:
                    db.add(ContextDB(
                        client_id=client_id,
                        client_name=ctx.client_name,
                        project=ctx.project,
                        region=ctx.region,
                        estimates=json.dumps(ctx.estimates, ensure_ascii=False),
                        documents=json.dumps(ctx.documents, ensure_ascii=False),
                        conversations=json.dumps(ctx.conversations, ensure_ascii=False),
                        preferences=json.dumps(ctx.preferences, ensure_ascii=False),
                        last_updated=ctx.last_updated,
                    ))
                db.commit()
            finally:
                db.close()
        except Exception:
            pass

    def get_context(self, client_id: str) -> Optional[ClientContext]:
        self._ensure_loaded()
        return self._contexts.get(client_id)

    def update_context(self, client_id: str, data: Dict) -> ClientContext:
        self._ensure_loaded()
        ctx = self._contexts.get(client_id) or ClientContext(client_id=client_id)

        if "client_name" in data:
            ctx.client_name = data["client_name"]
        if "project" in data:
            ctx.project = data["project"]
        if "region" in data:
            ctx.region = data["region"]
        if "preferences" in data:
            ctx.preferences.update(data["preferences"])

        ctx.last_updated = datetime.now(timezone.utc).isoformat()
        self._contexts[client_id] = ctx
        self._save_to_db(client_id)
        return ctx

    def add_estimate(self, client_id: str, estimate: Dict):
        self._ensure_loaded()
        ctx = self._contexts.get(client_id)
        if ctx:
            ctx.estimates = [estimate] + ctx.estimates[:9]
            ctx.last_updated = datetime.now(timezone.utc).isoformat()
            self._save_to_db(client_id)

    def add_document(self, client_id: str, document: Dict):
        self._ensure_loaded()
        ctx = self._contexts.get(client_id)
        if ctx:
            ctx.documents = [document] + ctx.documents[:9]
            ctx.last_updated = datetime.now(timezone.utc).isoformat()
            self._save_to_db(client_id)

    def add_conversation(self, client_id: str, message: Dict):
        self._ensure_loaded()
        ctx = self._contexts.get(client_id)
        if ctx:
            ctx.conversations.append(message)
            if len(ctx.conversations) > 50:
                ctx.conversations = ctx.conversations[-50:]
            ctx.last_updated = datetime.now(timezone.utc).isoformat()
            self._save_to_db(client_id)

    def build_ai_context(self, client_id: str) -> str:
        """Build context string for AI provider."""
        self._ensure_loaded()
        ctx = self._contexts.get(client_id)
        if not ctx:
            return ""

        parts = []

        if ctx.client_name:
            parts.append(f"Клиент: {ctx.client_name}")
        if ctx.project:
            parts.append(f"Проект: {ctx.project}")
        if ctx.region:
            parts.append(f"Регион: {ctx.region}")

        if ctx.estimates:
            parts.append(f"\nПоследние сметы ({len(ctx.estimates)}):")
            for est in ctx.estimates[:5]:
                parts.append(f"- {est.get('title', 'Без названия')}: {est.get('total', '0')} ₽")

        if ctx.documents:
            parts.append(f"\nПоследние документы ({len(ctx.documents)}):")
            for doc in ctx.documents[:5]:
                parts.append(f"- {doc.get('title', 'Без названия')} ({doc.get('type', 'document')})")

        if ctx.preferences:
            parts.append(f"\nПредпочтения: {json.dumps(ctx.preferences, ensure_ascii=False)}")

        return "\n".join(parts)

    def search_context(self, client_id: str, query: str) -> List[Dict]:
        """Search within client context."""
        self._ensure_loaded()
        ctx = self._contexts.get(client_id)
        if not ctx:
            return []

        query_lower = query.lower()
        results = []

        for est in ctx.estimates:
            if query_lower in est.get("title", "").lower() or query_lower in est.get("client", "").lower():
                results.append({"type": "estimate", "data": est})

        for doc in ctx.documents:
            if query_lower in doc.get("title", "").lower() or query_lower in doc.get("content", "").lower():
                results.append({"type": "document", "data": doc})

        return results


# Global instance
context_manager = ContextManager()
