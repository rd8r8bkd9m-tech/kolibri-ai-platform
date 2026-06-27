"""Deterministic search — exact and fuzzy search across all Kolibri data."""
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import EstimateDB, SectionDB, PositionDB, DocumentDB, AgentDB, NodeDB, TaskDB


class SearchEngine:
    """Deterministic search across all Kolibri entities."""
    
    def __init__(self, db: Session):
        self.db = db
    
    def search(self, query: str, entity_types: Optional[List[str]] = None, limit: int = 20) -> Dict[str, List[Dict]]:
        """Search across all entities."""
        query_lower = query.lower().strip()
        results = {}
        
        types = entity_types or ["estimates", "documents", "agents", "nodes", "tasks"]
        
        if "estimates" in types:
            results["estimates"] = self._search_estimates(query_lower, limit)
        if "documents" in types:
            results["documents"] = self._search_documents(query_lower, limit)
        if "agents" in types:
            results["agents"] = self._search_agents(query_lower, limit)
        if "nodes" in types:
            results["nodes"] = self._search_nodes(query_lower, limit)
        if "tasks" in types:
            results["tasks"] = self._search_tasks(query_lower, limit)
        if "positions" in types:
            results["positions"] = self._search_positions(query_lower, limit)
        
        return results
    
    def _search_estimates(self, query: str, limit: int) -> List[Dict]:
        results = []
        for est in self.db.query(EstimateDB).all():
            score = self._score(query, [
                est.title or "",
                est.client or "",
                est.object_name or "",
                est.region or "",
            ])
            if score > 0:
                results.append({
                    "type": "estimate",
                    "id": est.id,
                    "title": est.title,
                    "client": est.client,
                    "object_name": est.object_name,
                    "total": est.total,
                    "status": est.status,
                    "score": score,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def _search_documents(self, query: str, limit: int) -> List[Dict]:
        results = []
        for doc in self.db.query(DocumentDB).all():
            score = self._score(query, [
                doc.title or "",
                doc.client or "",
                doc.project or "",
                doc.content[:500] if doc.content else "",
            ])
            if score > 0:
                results.append({
                    "type": "document",
                    "id": doc.id,
                    "title": doc.title,
                    "client": doc.client,
                    "type_label": doc.type,
                    "status": doc.status,
                    "score": score,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def _search_positions(self, query: str, limit: int) -> List[Dict]:
        results = []
        for pos in self.db.query(PositionDB).all():
            score = self._score(query, [
                pos.name or "",
                pos.code or "",
                pos.comment or "",
            ])
            if score > 0:
                results.append({
                    "type": "position",
                    "id": pos.id,
                    "code": pos.code,
                    "name": pos.name,
                    "unit": pos.unit,
                    "quantity": pos.quantity,
                    "price": pos.price,
                    "sum": pos.sum,
                    "score": score,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def _search_agents(self, query: str, limit: int) -> List[Dict]:
        results = []
        for agent in self.db.query(AgentDB).all():
            score = self._score(query, [
                agent.name or "",
                agent.role or "",
                agent.current_task or "",
            ])
            if score > 0:
                results.append({
                    "type": "agent",
                    "id": agent.id,
                    "name": agent.name,
                    "role": agent.role,
                    "status": agent.status,
                    "score": score,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def _search_nodes(self, query: str, limit: int) -> List[Dict]:
        results = []
        for node in self.db.query(NodeDB).all():
            score = self._score(query, [
                node.name or "",
                node.region or "",
                node.ip_address or "",
            ])
            if score > 0:
                results.append({
                    "type": "node",
                    "id": node.id,
                    "name": node.name,
                    "region": node.region,
                    "status": node.status,
                    "score": score,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def _search_tasks(self, query: str, limit: int) -> List[Dict]:
        results = []
        for task in self.db.query(TaskDB).all():
            score = self._score(query, [
                task.workflow_id or "",
                task.state or "",
            ])
            if score > 0:
                results.append({
                    "type": "task",
                    "id": task.id,
                    "workflow_id": task.workflow_id,
                    "state": task.state,
                    "priority": task.priority,
                    "score": score,
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    def _score(self, query: str, fields: List[str]) -> int:
        """Score a match — exact > prefix > contains."""
        score = 0
        for field in fields:
            field_lower = field.lower()
            if query == field_lower:
                score += 100
            elif field_lower.startswith(query):
                score += 50
            elif query in field_lower:
                score += 25
            # Word-level match
            words = query.split()
            for word in words:
                if word in field_lower:
                    score += 10
        return score
    
    def search_with_context(self, query: str, client_id: Optional[str] = None) -> Dict[str, Any]:
        """Search with additional context."""
        results = self.search(query)
        
        # Flatten results
        all_results = []
        for entity_type, items in results.items():
            for item in items:
                item["entity_type"] = entity_type
                all_results.append(item)
        
        # Sort by score
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        return {
            "query": query,
            "total": len(all_results),
            "results": all_results[:20],
            "by_type": {k: len(v) for k, v in results.items()},
        }
