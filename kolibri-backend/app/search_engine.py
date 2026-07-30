"""Deterministic principal-scoped search across public Kolibri resources."""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models import DocumentDB, EstimateDB, PositionDB, SectionDB


class SearchEngine:
    """Deterministic search inside one signed browser/user principal."""
    
    PUBLIC_ENTITY_TYPES = frozenset({"estimates", "documents", "positions"})

    def __init__(self, db: Session, scope_id: str):
        if not scope_id:
            raise RuntimeError("search requires an explicit principal scope")
        self.db = db
        self.scope_id = scope_id
    
    def search(self, query: str, entity_types: Optional[List[str]] = None, limit: int = 20) -> Dict[str, List[Dict]]:
        """Search across all entities."""
        query_lower = query.lower().strip()
        results = {}
        
        requested_types = entity_types or ["estimates", "documents", "positions"]
        types = [name for name in requested_types if name in self.PUBLIC_ENTITY_TYPES]
        
        if "estimates" in types:
            results["estimates"] = self._search_estimates(query_lower, limit)
        if "documents" in types:
            results["documents"] = self._search_documents(query_lower, limit)
        if "positions" in types:
            results["positions"] = self._search_positions(query_lower, limit)
        
        return results
    
    def _search_estimates(self, query: str, limit: int) -> List[Dict]:
        results = []
        for est in self.db.query(EstimateDB).filter(EstimateDB.scope_id == self.scope_id).all():
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
        for doc in self.db.query(DocumentDB).filter(DocumentDB.scope_id == self.scope_id).all():
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
        positions = (
            self.db.query(PositionDB)
            .join(SectionDB, PositionDB.section_id == SectionDB.id)
            .join(EstimateDB, SectionDB.estimate_id == EstimateDB.id)
            .filter(EstimateDB.scope_id == self.scope_id)
            .all()
        )
        for pos in positions:
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
    
    def search_with_context(
        self,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """Search with additional context."""
        results = self.search(query, entity_types=entity_types, limit=limit)
        
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
            "results": all_results[:limit],
            "by_type": {k: len(v) for k, v in results.items()},
        }
