"""Storage abstraction — DBStorage (SQLAlchemy) and InMemoryStorage (legacy)."""
import copy
import os
import uuid
import random
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.models import (
    AgentDB,
    ClientDB,
    ConstructionObjectDB,
    DocumentDB,
    EstimateDB,
    EstimateRevisionDB,
    NodeDB,
    PositionDB,
    ProjectDB,
    SectionDB,
    TaskDB,
    TechnologyCatalogDB,
    WorkCatalogDB,
)
from app.calculator import (
    Estimate as CalcEstimate, EstimateSection as CalcSection,
    EstimatePosition as CalcPosition, EstimateStatus,
    calculate_estimate,
)
from app.estimate_evidence import (
    PriceEvidenceRecord,
    evidence_attestation_is_valid,
    evaluate_price_evidence,
)
from app.technology_card import validate_stored_technology_card


_TAX_REGIME_VAT_RATE = {
    "npd": "0",
    "usn_exempt": "0",
    "usn_vat5": "5",
    "usn_vat7": "7",
    "osno_vat22": "22",
}

_STARTER_WORK_CATALOG = (
    ("Подготовка и защита поверхностей", "м²", "Подготовительные работы", "180.00"),
    ("Грунтование стен", "м²", "Отделочные работы", "95.00"),
    ("Штукатурка стен по маякам", "м²", "Отделочные работы", "850.00"),
    ("Шпатлевание стен под покраску", "м²", "Отделочные работы", "620.00"),
    ("Окраска стен в два слоя", "м²", "Отделочные работы", "390.00"),
    ("Устройство цементно-песчаной стяжки", "м²", "Полы", "780.00"),
    ("Укладка керамогранита", "м²", "Полы", "1450.00"),
    ("Монтаж перегородок из ГКЛ", "м²", "Перегородки", "1350.00"),
    ("Электромонтажная точка", "шт", "Электромонтаж", "1650.00"),
    ("Монтаж точки водоснабжения", "шт", "Сантехника", "2400.00"),
    ("Погрузка и вывоз строительного мусора", "м³", "Общестроительные работы", "1850.00"),
    ("Финальная уборка объекта", "м²", "Общестроительные работы", "140.00"),
)


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


def _iso_z(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _enum_value(value, default: str) -> str:
    if value is None:
        return default
    return str(value.value if hasattr(value, "value") else value)


def _decimal(value) -> Decimal:
    try:
        parsed = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return parsed if parsed.is_finite() else Decimal("0")


def _json_list(value) -> list:
    return copy.deepcopy(value) if isinstance(value, list) else []


def _normalized_directory_value(value: object, *, limit: int = 500) -> str:
    """Create a stable, human-language-safe directory identity."""

    compact = " ".join(str(value or "").split()).strip().casefold()
    return re.sub(r"[^0-9a-zа-яё]+", " ", compact).strip()[:limit]


def _dedupe_issues(value) -> list[dict]:
    """Return bounded, stable current-state evidence issues."""

    result: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in _json_list(value):
        if not isinstance(raw, dict):
            continue
        issue = {
            "code": str(raw.get("code") or "")[:80],
            "position_code": str(raw.get("position_code") or "")[:80],
            "message": str(raw.get("message") or "")[:500],
        }
        if not issue["code"] or not issue["message"]:
            continue
        identity = (issue["code"], issue["position_code"], issue["message"])
        if identity in seen:
            continue
        seen.add(identity)
        result.append(issue)
        if len(result) >= 200:
            break
    return result


class EstimateVersionConflict(RuntimeError):
    """Raised when an estimate save loses its compare-and-swap."""

    def __init__(self, *, estimate_id: str, expected_version: int, current_version: int):
        self.estimate_id = estimate_id
        self.expected_version = expected_version
        self.current_version = current_version
        super().__init__(
            f"estimate {estimate_id} is version {current_version}, expected {expected_version}"
        )


class DocumentEstimateNotFound(RuntimeError):
    """A document attempted to reference an estimate outside its scope."""


class DBStorage:
    """Persistent storage using SQLAlchemy."""

    def __init__(
        self,
        db: Session,
        scope_id: Optional[str] = None,
        organization_id: Optional[str] = None,
    ):
        self.db = db
        self.scope_id = scope_id
        self.organization_id = organization_id

    def _estimate_scope(self) -> str:
        """Return the mandatory estimate principal or fail closed."""

        if not self.scope_id:
            raise RuntimeError("estimate storage requires an explicit principal scope")
        return self.scope_id

    def _document_scope(self) -> str:
        """Return the mandatory document principal or fail closed."""

        if not self.scope_id:
            raise RuntimeError("document storage requires an explicit principal scope")
        return self.scope_id

    def _require_owned_document_estimate(self, estimate_id: Optional[str]) -> None:
        """Prevent cross-scope estimate references without disclosing ownership."""

        if not estimate_id:
            return
        owned = (
            self.db.query(EstimateDB.id)
            .filter(
                EstimateDB.id == estimate_id,
                EstimateDB.scope_id == self._document_scope(),
            )
            .first()
        )
        if owned is None:
            raise DocumentEstimateNotFound("linked estimate is not available")

    # ── Estimates ────────────────────────────────────────────────────────────

    def list_estimates(self, status: Optional[str] = None, search: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        q = self.db.query(EstimateDB).filter(
            EstimateDB.scope_id == self._estimate_scope()
        )
        if status:
            q = q.filter(EstimateDB.status == status)
        if search:
            s = search.lower()
            q = q.filter(EstimateDB.title.ilike(f"%{s}%"))
        total = q.count()
        items = q.order_by(EstimateDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": [self._est_to_dict(e) for e in items], "total": total}

    def get_estimate(self, est_id: str) -> Optional[dict]:
        e = (
            self.db.query(EstimateDB)
            .filter(
                EstimateDB.id == est_id,
                EstimateDB.scope_id == self._estimate_scope(),
            )
            .first()
        )
        return self._est_to_dict(e) if e else None

    def create_estimate(self, data: dict, *, trusted_scope: bool = False) -> dict:
        est_id = _uid()
        now = _now()
        project = None
        project_id = str(data.get("project_id") or "").strip()
        if project_id:
            from app.project_case import writable_project

            project = writable_project(
                self.db,
                project_id=project_id,
                scope_id=self._estimate_scope(),
            )
            if project is None:
                from app.project_history import ProjectNotFoundError

                raise ProjectNotFoundError(project_id)
        e = EstimateDB(
            id=est_id,
            scope_id=self._estimate_scope(),
            organization_id=self.organization_id,
            project_id=project.id if project is not None else None,
            version=1,
            title=data.get("title", ""), client=data.get("client", ""),
            object_name=data.get("object_name", ""), region=data.get("region", ""),
            price_as_of=data.get("price_as_of"),
            currency=data.get("currency", "RUB"),
            overhead_rate=data.get("overhead_rate", "0"),
            profit_rate=data.get("profit_rate", "0"),
            contingency_rate=data.get("contingency_rate", "0"),
            general_contractor_rate=data.get("general_contractor_rate", "0"),
            discount_rate=data.get("discount_rate", "0"),
            vat_rate=data.get("vat_rate", "22"),
            tax_regime=_enum_value(data.get("tax_regime"), "unspecified"),
            # Scope verification is a server-side verifier decision.  Public
            # CRUD may carry the field for round-tripping, but it cannot mint
            # a verified scope by posting that enum value itself.
            scope_status=(
                _enum_value(data.get("scope_status"), "unverified")
                if trusted_scope
                else "unverified"
            ),
            # ``source_note`` is derived below from persisted evidence.  A
            # provider/client string cannot promote the truth shown in UI.
            source_note="",
            assumptions=_json_list(data.get("assumptions")),
            questions=_json_list(data.get("questions")),
            technology_card=validate_stored_technology_card(data.get("technology_card")),
            procurement_report=(
                copy.deepcopy(data.get("procurement_report"))
                if isinstance(data.get("procurement_report"), dict)
                else None
            ),
            evidence_issues=_dedupe_issues(data.get("evidence_issues")),
            created_at=now, updated_at=now,
        )
        try:
            self.db.add(e)
            self._sync_estimate_directory_links(e)
            evidence_issues, _price_changed, _scope_changed = self._replace_sections(
                e,
                data.get("sections", []),
                top_level_evidence=data.get("price_sources"),
            )
            e.evidence_issues = _dedupe_issues(
                _json_list(e.evidence_issues) + evidence_issues
            )
            self._calculate_entity(e)
            self._derive_truth(e)
            if e.status == "approved":
                self._promote_estimate_to_catalog(e)
            if project is not None:
                from app.project_case import attach_estimate

                attach_estimate(project, estimate=e)
            self._append_revision(e)
            self.db.commit()
            self.db.refresh(e)
            return self._est_to_dict(e)
        except Exception:
            self.db.rollback()
            raise

    def update_estimate(
        self,
        est_id: str,
        data: dict,
        *,
        expected_version: int,
        trusted_scope: bool = False,
    ) -> Optional[dict]:
        scope_id = self._estimate_scope()
        if (
            self.db.query(EstimateDB.id)
            .filter(EstimateDB.id == est_id, EstimateDB.scope_id == scope_id)
            .first()
            is None
        ):
            return None

        now = _now()
        updated = (
            self.db.query(EstimateDB)
            .filter(
                EstimateDB.id == est_id,
                EstimateDB.scope_id == scope_id,
                EstimateDB.version == expected_version,
            )
            .update(
                {
                    EstimateDB.version: expected_version + 1,
                    EstimateDB.updated_at: now,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            self.db.rollback()
            current = (
                self.db.query(EstimateDB.version)
                .filter(EstimateDB.id == est_id, EstimateDB.scope_id == scope_id)
                .scalar()
            )
            if current is None:
                return None
            raise EstimateVersionConflict(
                estimate_id=est_id,
                expected_version=expected_version,
                current_version=int(current),
            )

        try:
            self.db.expire_all()
            e = (
                self.db.query(EstimateDB)
                .filter(EstimateDB.id == est_id, EstimateDB.scope_id == scope_id)
                .one()
            )
            original_scope_metadata = (
                str(e.object_name or ""),
                str(e.region or ""),
                tuple(str(item) for item in (e.assumptions or [])),
            )
            for field in [
                "title",
                "client",
                "object_name",
                "region",
                "price_as_of",
                "currency",
                "overhead_rate",
                "profit_rate",
                "contingency_rate",
                "general_contractor_rate",
                "discount_rate",
                "vat_rate",
                "tax_regime",
                "status",
            ]:
                if field in data and data[field] is not None:
                    setattr(e, field, data[field])
            for field in ["assumptions", "questions"]:
                if field in data and data[field] is not None:
                    setattr(e, field, _json_list(data[field]))
            if "technology_card" in data and data["technology_card"] is not None:
                e.technology_card = validate_stored_technology_card(data["technology_card"])
            if "procurement_report" in data and data["procurement_report"] is not None:
                e.procurement_report = (
                    copy.deepcopy(data["procurement_report"])
                    if isinstance(data["procurement_report"], dict)
                    else None
                )
            scope_metadata_changed = original_scope_metadata != (
                str(e.object_name or ""),
                str(e.region or ""),
                tuple(str(item) for item in (e.assumptions or [])),
            )
            requested_evidence_issues = (
                _dedupe_issues(data["evidence_issues"])
                if data.get("evidence_issues") is not None
                else None
            )
            if "scope_status" in data and data["scope_status"] is not None:
                requested_scope = _enum_value(data["scope_status"], "unverified")
                if trusted_scope or requested_scope != "verified":
                    e.scope_status = requested_scope

            # Every save repairs legacy estimates that have textual client or
            # object data but no directory link. Empty names never create
            # placeholder directory rows.
            self._sync_estimate_directory_links(e)

            sections_payload = data.get("sections") if "sections" in data else None
            if sections_payload is None and (
                data.get("price_sources") is not None or scope_metadata_changed
            ):
                sections_payload = self._sections_for_replacement(e)
            if sections_payload is not None:
                evidence_issues, price_changed, scope_changed = self._replace_sections(
                    e,
                    sections_payload,
                    top_level_evidence=data.get("price_sources"),
                    preserve_existing=True,
                )
                # A section/evidence save represents a new current truth
                # evaluation. Stale issues from older revisions remain in
                # those immutable snapshots, not on the live estimate.
                e.evidence_issues = _dedupe_issues(
                    (requested_evidence_issues or []) + evidence_issues
                )
                if price_changed or scope_changed or scope_metadata_changed:
                    e.scope_status = "unverified"
            elif requested_evidence_issues is not None:
                e.evidence_issues = requested_evidence_issues
            self._calculate_entity(e)
            self._derive_truth(e)
            if e.status == "approved":
                self._promote_estimate_to_catalog(e)
            if e.project_id:
                from app.project_case import attach_estimate, writable_project

                project = writable_project(
                    self.db,
                    project_id=e.project_id,
                    scope_id=scope_id,
                )
                if project is None:
                    raise ValueError("linked project is not available")
                attach_estimate(project, estimate=e)
            self._append_revision(e)
            self.db.commit()
            self.db.refresh(e)
            return self._est_to_dict(e)
        except Exception:
            self.db.rollback()
            raise

    def recalculate_estimate(self, est_id: str, *, expected_version: int) -> Optional[dict]:
        return self.update_estimate(est_id, {}, expected_version=expected_version)

    def delete_estimate(self, est_id: str) -> bool:
        e = (
            self.db.query(EstimateDB)
            .filter(
                EstimateDB.id == est_id,
                EstimateDB.scope_id == self._estimate_scope(),
            )
            .first()
        )
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
            "overhead_rate": orig["overhead_rate"],
            "profit_rate": orig["profit_rate"],
            "contingency_rate": orig["contingency_rate"],
            "general_contractor_rate": orig["general_contractor_rate"],
            "discount_rate": orig["discount_rate"],
            "vat_rate": orig["vat_rate"],
            "tax_regime": orig["tax_regime"],
            "scope_status": orig["scope_status"],
            "source_note": orig["source_note"],
            "assumptions": copy.deepcopy(orig["assumptions"]),
            "questions": copy.deepcopy(orig["questions"]),
            "technology_card": copy.deepcopy(orig.get("technology_card")),
            "procurement_report": copy.deepcopy(orig.get("procurement_report")),
            "price_sources": copy.deepcopy(orig["price_sources"]),
            "evidence_issues": copy.deepcopy(orig["evidence_issues"]),
            "sections": [
                {"title": s["title"], "positions": [
                    {
                        k: copy.deepcopy(p[k])
                        for k in [
                            "code", "name", "unit", "quantity", "price",
                            "source", "price_evidence", "comment",
                        ]
                    }
                    for p in s["positions"]
                ]}
                for s in orig["sections"]
            ],
        }
        # A duplicate is an internal copy of an already persisted immutable
        # revision, not a new client assertion.  Preserve its existing scope
        # verdict while the copied evidence is independently re-evaluated.
        return self.create_estimate(new_data, trusted_scope=True)

    def list_estimate_revisions(self, est_id: str) -> Optional[dict]:
        if (
            self.db.query(EstimateDB.id)
            .filter(
                EstimateDB.id == est_id,
                EstimateDB.scope_id == self._estimate_scope(),
            )
            .first()
            is None
        ):
            return None
        revisions = (
            self.db.query(EstimateRevisionDB)
            .filter(EstimateRevisionDB.estimate_id == est_id)
            .order_by(EstimateRevisionDB.version.desc())
            .all()
        )
        return {
            "items": [
                {
                    "id": revision.id,
                    "estimate_id": revision.estimate_id,
                    "version": revision.version,
                    "title": revision.snapshot.get("title", ""),
                    "status": revision.snapshot.get("status", "draft"),
                    "estimate_status": revision.snapshot.get("estimate_status", "preliminary"),
                    "pricing_status": revision.snapshot.get("pricing_status", "preliminary"),
                    "total": revision.snapshot.get("total", "0.00"),
                    "created_at": _iso_z(revision.created_at),
                }
                for revision in revisions
            ],
            "total": len(revisions),
        }

    def get_estimate_revision(self, est_id: str, version: int) -> Optional[dict]:
        revision = (
            self.db.query(EstimateRevisionDB)
            .join(EstimateDB, EstimateRevisionDB.estimate_id == EstimateDB.id)
            .filter(
                EstimateRevisionDB.estimate_id == est_id,
                EstimateRevisionDB.version == version,
                EstimateDB.scope_id == self._estimate_scope(),
            )
            .first()
        )
        if revision is None:
            return None
        return {
            "id": revision.id,
            "estimate_id": revision.estimate_id,
            "version": revision.version,
            "snapshot": copy.deepcopy(revision.snapshot),
            "created_at": _iso_z(revision.created_at),
        }

    def get_estimate_snapshot(self, est_id: str, version: Optional[int] = None) -> Optional[dict]:
        query = (
            self.db.query(EstimateRevisionDB)
            .join(EstimateDB, EstimateRevisionDB.estimate_id == EstimateDB.id)
            .filter(
                EstimateRevisionDB.estimate_id == est_id,
                EstimateDB.scope_id == self._estimate_scope(),
            )
        )
        if version is None:
            revision = query.order_by(EstimateRevisionDB.version.desc()).first()
        else:
            revision = query.filter(EstimateRevisionDB.version == version).first()
        return copy.deepcopy(revision.snapshot) if revision is not None else None

    def list_work_catalog(self, search: str = "", page: int = 1, page_size: int = 50) -> dict:
        existing = self.db.query(WorkCatalogDB).filter(
            WorkCatalogDB.scope_id == self._estimate_scope(),
            WorkCatalogDB.status == "approved",
        ).count()
        if existing == 0:
            observed_at = _now()
            for name, unit, category, price in _STARTER_WORK_CATALOG:
                self.db.add(WorkCatalogDB(
                    id=_uid(),
                    scope_id=self._estimate_scope(),
                    organization_id=self.organization_id,
                    normalized_key=re.sub(r"\s+", " ", name.strip().lower()),
                    name=name,
                    unit=unit,
                    category=category,
                    latest_price=price,
                    price_source="Предварительная редактируемая база Kolibri",
                    price_observed_at=observed_at,
                    usage_count=1,
                    status="approved",
                    source_version=1,
                ))
            self.db.commit()
        query = self.db.query(WorkCatalogDB).filter(
            WorkCatalogDB.scope_id == self._estimate_scope(),
            WorkCatalogDB.status == "approved",
        )
        if search.strip():
            query = query.filter(WorkCatalogDB.name.ilike(f"%{search.strip()}%"))
        total = query.count()
        rows = (
            query.order_by(WorkCatalogDB.usage_count.desc(), WorkCatalogDB.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [
                {
                    "id": row.id,
                    "name": row.name,
                    "unit": row.unit,
                    "category": row.category,
                    "latest_price": row.latest_price,
                    "price_source": row.price_source,
                    "price_observed_at": _iso_z(row.price_observed_at) if row.price_observed_at else None,
                    "usage_count": row.usage_count,
                    "status": row.status,
                    "source_estimate_id": row.source_estimate_id,
                    "source_version": row.source_version,
                    "updated_at": _iso_z(row.updated_at),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_work_catalog_price(self, item_id: str, latest_price: str, price_source: str = "manual") -> Optional[dict]:
        row = (
            self.db.query(WorkCatalogDB)
            .filter(
                WorkCatalogDB.id == item_id,
                WorkCatalogDB.scope_id == self._estimate_scope(),
                WorkCatalogDB.status == "approved",
            )
            .first()
        )
        if row is None:
            return None
        try:
            amount = Decimal(str(latest_price).strip().replace(",", "."))
        except InvalidOperation as exc:
            raise ValueError("invalid catalog price") from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError("catalog price must be non-negative")
        row.latest_price = format(amount.quantize(Decimal("0.01")), "f")
        row.price_source = " ".join(str(price_source or "manual").split())[:200] or "manual"
        row.price_observed_at = _now()
        row.updated_at = row.price_observed_at
        self.db.commit()
        return {
            "id": row.id,
            "name": row.name,
            "unit": row.unit,
            "category": row.category,
            "latest_price": row.latest_price,
            "price_source": row.price_source,
            "price_observed_at": _iso_z(row.price_observed_at),
            "usage_count": row.usage_count,
            "status": row.status,
            "source_estimate_id": row.source_estimate_id,
            "source_version": row.source_version,
            "updated_at": _iso_z(row.updated_at),
        }

    def list_clients(self, search: str = "", page: int = 1, page_size: int = 50) -> dict:
        query = self.db.query(ClientDB).filter(
            ClientDB.scope_id == self._estimate_scope()
        )
        if search.strip():
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    ClientDB.name.ilike(pattern),
                    ClientDB.phone.ilike(pattern),
                    ClientDB.email.ilike(pattern),
                )
            )
        total = query.count()
        rows = (
            query.order_by(ClientDB.updated_at.desc(), ClientDB.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [self._client_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def create_client(self, data: dict) -> dict:
        name = " ".join(str(data.get("name") or "").split()).strip()
        if not name:
            raise ValueError("client name is required")
        key = _normalized_directory_value(name)
        if self.db.query(ClientDB.id).filter(
            ClientDB.scope_id == self._estimate_scope(),
            ClientDB.normalized_key == key,
        ).first() is not None:
            raise ValueError("client already exists")
        now = _now()
        row = ClientDB(
            id=_uid(),
            scope_id=self._estimate_scope(),
            organization_id=self.organization_id,
            normalized_key=key,
            name=name[:500],
            phone=" ".join(str(data.get("phone") or "").split()).strip()[:80],
            email=" ".join(str(data.get("email") or "").split()).strip()[:320],
            inn=" ".join(str(data.get("inn") or "").split()).strip()[:20],
            kpp=" ".join(str(data.get("kpp") or "").split()).strip()[:20],
            address=" ".join(str(data.get("address") or "").split()).strip()[:1_000],
            contact_person=" ".join(str(data.get("contact_person") or "").split()).strip()[:300],
            source="manual",
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._client_to_dict(row)

    def update_client(self, client_id: str, data: dict) -> Optional[dict]:
        row = self.db.query(ClientDB).filter(
            ClientDB.id == client_id,
            ClientDB.scope_id == self._estimate_scope(),
        ).first()
        if row is None:
            return None
        if data.get("name") is not None:
            name = " ".join(str(data.get("name") or "").split()).strip()
            if not name:
                raise ValueError("client name is required")
            row.name = name[:500]
            row.normalized_key = _normalized_directory_value(name)
        for field, limit in (("phone", 80), ("email", 320), ("inn", 20), ("kpp", 20), ("address", 1_000), ("contact_person", 300)):
            if data.get(field) is not None:
                setattr(row, field, " ".join(str(data[field] or "").split()).strip()[:limit])
        row.updated_at = _now()
        self.db.commit()
        self.db.refresh(row)
        return self._client_to_dict(row)

    def list_construction_objects(
        self,
        search: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        query = self.db.query(ConstructionObjectDB).filter(
            ConstructionObjectDB.scope_id == self._estimate_scope()
        )
        if search.strip():
            pattern = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    ConstructionObjectDB.name.ilike(pattern),
                    ConstructionObjectDB.address.ilike(pattern),
                    ConstructionObjectDB.region.ilike(pattern),
                )
            )
        total = query.count()
        rows = (
            query.order_by(ConstructionObjectDB.updated_at.desc(), ConstructionObjectDB.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [self._construction_object_to_dict(row) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def create_construction_object(self, data: dict) -> dict:
        scope_id = self._estimate_scope()
        client_id = str(data.get("client_id") or "").strip() or None
        if client_id and self.db.query(ClientDB.id).filter(
            ClientDB.id == client_id,
            ClientDB.scope_id == scope_id,
        ).first() is None:
            raise ValueError("client is not available")
        name = " ".join(str(data.get("name") or "Объект без названия").split()).strip() or "Объект без названия"
        region = " ".join(str(data.get("region") or "").split()).strip()
        key = f"client:{client_id or 'unassigned'}|region:{_normalized_directory_value(region, limit=240)}|name:{_normalized_directory_value(name)}"[:1_200]
        if self.db.query(ConstructionObjectDB.id).filter(
            ConstructionObjectDB.scope_id == scope_id,
            ConstructionObjectDB.normalized_key == key,
        ).first() is not None:
            raise ValueError("construction object already exists")
        now = _now()
        row = ConstructionObjectDB(
            id=_uid(),
            scope_id=scope_id,
            organization_id=self.organization_id,
            client_id=client_id,
            normalized_key=key,
            name=name[:500],
            address=" ".join(str(data.get("address") or "").split()).strip()[:1_000],
            region=region[:320],
            source="manual",
            created_at=now,
            updated_at=now,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._construction_object_to_dict(row)

    def update_construction_object(self, object_id: str, data: dict) -> Optional[dict]:
        scope_id = self._estimate_scope()
        row = self.db.query(ConstructionObjectDB).filter(
            ConstructionObjectDB.id == object_id,
            ConstructionObjectDB.scope_id == scope_id,
        ).first()
        if row is None:
            return None
        client_id = row.client_id
        if "client_id" in data:
            client_id = str(data.get("client_id") or "").strip() or None
            if client_id and self.db.query(ClientDB.id).filter(
                ClientDB.id == client_id,
                ClientDB.scope_id == scope_id,
            ).first() is None:
                raise ValueError("client is not available")
            row.client_id = client_id
        if data.get("name") is not None:
            name = " ".join(str(data.get("name") or "").split()).strip()
            if not name:
                raise ValueError("construction object name is required")
            row.name = name[:500]
        for field, limit in (("address", 1_000), ("region", 320)):
            if data.get(field) is not None:
                setattr(row, field, " ".join(str(data[field] or "").split()).strip()[:limit])
        row.normalized_key = (
            f"client:{client_id or 'unassigned'}|region:{_normalized_directory_value(row.region, limit=240)}|name:{_normalized_directory_value(row.name)}"
        )[:1_200]
        row.updated_at = _now()
        self.db.commit()
        self.db.refresh(row)
        return self._construction_object_to_dict(row)

    def _sync_estimate_directory_links(self, estimate: EstimateDB) -> None:
        """Upsert non-empty textual client/object fields inside one tenant."""

        scope_id = self._estimate_scope()
        now = _now()
        client_name = " ".join(str(estimate.client or "").split()).strip()
        client_key = _normalized_directory_value(client_name)
        client: ClientDB | None = None
        if client_key:
            client = (
                self.db.query(ClientDB)
                .filter(
                    ClientDB.scope_id == scope_id,
                    ClientDB.normalized_key == client_key,
                )
                .first()
            )
            if client is None:
                client = ClientDB(
                    id=_uid(),
                    scope_id=scope_id,
                    organization_id=self.organization_id,
                    normalized_key=client_key,
                    name=client_name[:500],
                    source="chat_estimate",
                    created_at=now,
                    updated_at=now,
                )
                self.db.add(client)
            else:
                client.name = client_name[:500]
                if client.organization_id is None and self.organization_id is not None:
                    client.organization_id = self.organization_id
                client.updated_at = now
            estimate.client_record_id = client.id
        else:
            estimate.client_record_id = None

        object_name = " ".join(str(estimate.object_name or "").split()).strip() or "Объект без названия"
        estimate.object_name = object_name
        object_name_key = _normalized_directory_value(object_name)
        if not object_name_key:
            estimate.object_record_id = None
            return

        region = " ".join(str(estimate.region or "").split()).strip()
        region_key = _normalized_directory_value(region, limit=240)
        owner_key = client.id if client is not None else "unassigned"
        object_key = (
            f"client:{owner_key}|region:{region_key}|name:{object_name_key}"
        )[:1_200]
        construction_object = (
            self.db.query(ConstructionObjectDB)
            .filter(
                ConstructionObjectDB.scope_id == scope_id,
                ConstructionObjectDB.normalized_key == object_key,
            )
            .first()
        )
        if construction_object is None:
            construction_object = ConstructionObjectDB(
                id=_uid(),
                scope_id=scope_id,
                organization_id=self.organization_id,
                client_id=client.id if client is not None else None,
                normalized_key=object_key,
                name=object_name[:500],
                region=region[:320],
                source="chat_estimate",
                created_at=now,
                updated_at=now,
            )
            self.db.add(construction_object)
        else:
            construction_object.name = object_name[:500]
            construction_object.region = region[:320]
            construction_object.client_id = client.id if client is not None else None
            if (
                construction_object.organization_id is None
                and self.organization_id is not None
            ):
                construction_object.organization_id = self.organization_id
            construction_object.updated_at = now
        estimate.object_record_id = construction_object.id

    @staticmethod
    def _client_to_dict(client: ClientDB) -> dict:
        return {
            "id": client.id,
            "name": client.name,
            "phone": client.phone or "",
            "email": client.email or "",
            "inn": client.inn or "",
            "kpp": client.kpp or "",
            "address": client.address or "",
            "contact_person": client.contact_person or "",
            "source": client.source or "chat_estimate",
            "created_at": _iso_z(client.created_at),
            "updated_at": _iso_z(client.updated_at),
        }

    @staticmethod
    def _construction_object_to_dict(construction_object: ConstructionObjectDB) -> dict:
        return {
            "id": construction_object.id,
            "client_id": construction_object.client_id,
            "name": construction_object.name,
            "address": construction_object.address or "",
            "region": construction_object.region or "",
            "source": construction_object.source or "chat_estimate",
            "created_at": _iso_z(construction_object.created_at),
            "updated_at": _iso_z(construction_object.updated_at),
        }

    def list_technology_catalog(self, search: str = "", page: int = 1, page_size: int = 50) -> dict:
        query = self.db.query(TechnologyCatalogDB).filter(
            TechnologyCatalogDB.scope_id == self._estimate_scope(),
            TechnologyCatalogDB.status == "approved",
        )
        if search.strip():
            query = query.filter(TechnologyCatalogDB.title.ilike(f"%{search.strip()}%"))
        total = query.count()
        rows = (
            query.order_by(
                TechnologyCatalogDB.usage_count.desc(),
                TechnologyCatalogDB.updated_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return {
            "items": [
                {
                    "id": row.id,
                    "content_sha256": row.content_sha256,
                    "title": row.title,
                    "object_type": row.object_type,
                    "card": copy.deepcopy(row.card),
                    "usage_count": row.usage_count,
                    "status": row.status,
                    "source_estimate_id": row.source_estimate_id,
                    "source_version": row.source_version,
                    "updated_at": _iso_z(row.updated_at),
                }
                for row in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def promote_estimate_to_catalog(self, est_id: str) -> Optional[dict]:
        estimate = (
            self.db.query(EstimateDB)
            .filter(
                EstimateDB.id == est_id,
                EstimateDB.scope_id == self._estimate_scope(),
            )
            .first()
        )
        if estimate is None:
            return None
        if estimate.status != "approved":
            raise ValueError("approve estimate before adding it to the work catalog")
        self._promote_estimate_to_catalog(estimate)
        self.db.commit()
        return self.list_work_catalog(page_size=100)

    def _promote_estimate_to_catalog(self, estimate: EstimateDB) -> None:
        """Upsert approved work rows without leaking data across tenants."""
        now = _now()
        self._promote_technology_card(estimate, now=now)
        for section in estimate.sections:
            for position in section.positions:
                name = " ".join(str(position.name or "").split()).strip()
                unit = " ".join(str(position.unit or "шт").split()).strip()[:40]
                if not name:
                    continue
                normalized_key = re.sub(r"[^0-9a-zа-яё]+", " ", name.casefold()).strip()[:500]
                if not normalized_key:
                    continue
                row = (
                    self.db.query(WorkCatalogDB)
                    .filter(
                        WorkCatalogDB.scope_id == self._estimate_scope(),
                        WorkCatalogDB.normalized_key == normalized_key,
                        WorkCatalogDB.unit == unit,
                    )
                    .first()
                )
                if row is None:
                    self.db.add(
                        WorkCatalogDB(
                            id=_uid(),
                            scope_id=self._estimate_scope(),
                            organization_id=self.organization_id,
                            normalized_key=normalized_key,
                            name=name[:500],
                            unit=unit,
                            category=str(section.title or "")[:300],
                            latest_price=str(position.price or "0"),
                            price_source="estimate_verified" if position.price_evidence else "estimate_preliminary",
                            price_observed_at=now,
                            usage_count=1,
                            status="approved",
                            source_estimate_id=estimate.id,
                            source_version=int(estimate.version),
                            created_at=now,
                            updated_at=now,
                        )
                    )
                    continue
                if (
                    row.source_estimate_id == estimate.id
                    and int(row.source_version or 0) == int(estimate.version)
                ):
                    continue
                row.name = name[:500]
                row.category = str(section.title or "")[:300]
                row.latest_price = str(position.price or "0")
                row.price_source = "estimate_verified" if position.price_evidence else "estimate_preliminary"
                row.price_observed_at = now
                row.usage_count = int(row.usage_count or 0) + 1
                row.source_estimate_id = estimate.id
                row.source_version = int(estimate.version)
                row.updated_at = now

    def _promote_technology_card(self, estimate: EstimateDB, *, now: datetime) -> None:
        card = validate_stored_technology_card(estimate.technology_card)
        if card is None:
            return
        digest = str(card["content_sha256"])
        row = (
            self.db.query(TechnologyCatalogDB)
            .filter(
                TechnologyCatalogDB.scope_id == self._estimate_scope(),
                TechnologyCatalogDB.content_sha256 == digest,
            )
            .first()
        )
        if row is None:
            self.db.add(
                TechnologyCatalogDB(
                    id=_uid(),
                    scope_id=self._estimate_scope(),
                    organization_id=self.organization_id,
                    content_sha256=digest,
                    title=str(card.get("title") or estimate.title)[:500],
                    object_type=str(card.get("object_type") or "")[:320],
                    card=copy.deepcopy(card),
                    usage_count=1,
                    status="approved",
                    source_estimate_id=estimate.id,
                    source_version=int(estimate.version),
                    created_at=now,
                    updated_at=now,
                )
            )
            return
        if (
            row.source_estimate_id == estimate.id
            and int(row.source_version or 0) == int(estimate.version)
        ):
            return
        row.card = copy.deepcopy(card)
        row.title = str(card.get("title") or estimate.title)[:500]
        row.object_type = str(card.get("object_type") or "")[:320]
        row.usage_count = int(row.usage_count or 0) + 1
        row.source_estimate_id = estimate.id
        row.source_version = int(estimate.version)
        row.updated_at = now

    def _sections_for_replacement(self, estimate: EstimateDB) -> list[dict]:
        return [
            {
                "title": section.title,
                "positions": [
                    {
                        "code": position.code,
                        "name": position.name,
                        "unit": position.unit,
                        "quantity": position.quantity,
                        "price": position.price,
                        "source": position.source or "",
                        "price_evidence": copy.deepcopy(position.price_evidence or []),
                        "comment": position.comment or "",
                    }
                    for position in section.positions
                ],
            }
            for section in estimate.sections
        ]

    def _replace_sections(
        self,
        estimate: EstimateDB,
        sections: list[dict],
        *,
        top_level_evidence=None,
        preserve_existing: bool = False,
    ) -> tuple[list[dict], bool, bool]:
        existing_layout = tuple(
            (
                str(section.title),
                tuple(str(position.code or "") for position in section.positions),
            )
            for section in estimate.sections
        )
        existing = {
            position.code: {
                "price": position.price,
                "quantity": position.quantity,
                "unit": position.unit,
                "name": position.name,
                "source": position.source or "",
                "price_evidence": copy.deepcopy(position.price_evidence or []),
            }
            for section in estimate.sections
            for position in section.positions
            if position.code
        }
        prepared = copy.deepcopy(sections if isinstance(sections, list) else [])
        price_changed_codes: set[str] = set()
        prepared_layout = tuple(
            (
                str(section.get("title") or ""),
                tuple(
                    str(position.get("code") or "")
                    for position in section.get("positions", [])
                    if isinstance(position, dict)
                ),
            )
            for section in prepared
            if isinstance(section, dict)
        )
        # Layout is part of scope: adding, deleting, reordering or moving a
        # line (and changing a section title/order) invalidates the old scope
        # verdict even when every surviving line keeps the same values.
        scope_changed = preserve_existing and existing_layout != prepared_layout
        trusted_records = _json_list(top_level_evidence)
        for section in prepared:
            for position in section.get("positions", []):
                code = str(position.get("code") or "")
                old = existing.get(code) if preserve_existing else None
                incoming_evidence = _json_list(position.get("price_evidence"))
                if old is not None:
                    if _decimal(old["price"]) != _decimal(position.get("price")):
                        price_changed_codes.add(code)
                        incoming_evidence = []
                    elif not incoming_evidence:
                        incoming_evidence = copy.deepcopy(old["price_evidence"])
                    if (
                        _decimal(old["quantity"]) != _decimal(position.get("quantity"))
                        or str(old["unit"]) != str(position.get("unit"))
                        or str(old["name"]) != str(position.get("name"))
                    ):
                        scope_changed = True
                position["price_evidence"] = incoming_evidence
                trusted_records.extend(incoming_evidence)

        # The estimate action carries the same immutable records both at the
        # estimate level and on each position.  Collapse that transport
        # duplication before strict evaluation so a valid source is not
        # reported as a duplicate.  A manual price change is different: no
        # evidence supplied in the same edit may immediately re-certify the
        # changed value.  It must pass through a fresh collection/verifier
        # cycle in a later mutation.
        deduplicated_records: list[dict] = []
        seen_records: set[tuple[str, str, str]] = set()
        for record in trusted_records:
            if not isinstance(record, dict):
                continue
            position_code = str(record.get("position_code") or "")
            if position_code in price_changed_codes:
                continue
            identity = (
                position_code,
                str(record.get("source_id") or ""),
                str(record.get("content_sha256") or ""),
            )
            if identity in seen_records:
                continue
            seen_records.add(identity)
            deduplicated_records.append(record)

        trusted_mutated_codes: set[str] = set()
        for raw in deduplicated_records:
            try:
                record = PriceEvidenceRecord.model_validate(raw)
            except (TypeError, ValueError):
                continue
            if evidence_attestation_is_valid(record):
                trusted_mutated_codes.add(record.position_code)

        evidence_result = evaluate_price_evidence(
            prepared,
            region=estimate.region or "",
            currency=estimate.currency or "RUB",
            trusted_records=deduplicated_records,
        )
        # A trusted collector may assign the price before the final shared
        # verifier checks region/unit/freshness/binding.  When that verifier
        # rejects the signed record, the collector-mutated amount must not
        # survive as an apparently usable manual price in totals.
        for section in prepared:
            for position in section.get("positions", []):
                code = str(position.get("code") or "")
                if code in trusted_mutated_codes and not position.get("price_evidence"):
                    position["price"] = "0.00"
                    position["sum"] = "0.00"
                    position["source"] = ""
        estimate.sections.clear()
        for section_index, section_data in enumerate(prepared):
            section = SectionDB(
                id=_uid(),
                sort_order=section_index,
                title=section_data.get("title", ""),
            )
            estimate.sections.append(section)
            for position_index, position_data in enumerate(section_data.get("positions", [])):
                section.positions.append(
                    PositionDB(
                        id=_uid(),
                        sort_order=position_index,
                        code=position_data.get("code", ""),
                        name=position_data.get("name", ""),
                        unit=position_data.get("unit", "шт"),
                        quantity=position_data.get("quantity", "0"),
                        price=position_data.get("price", "0"),
                        source=position_data.get("source", ""),
                        price_evidence=copy.deepcopy(position_data.get("price_evidence") or []),
                        comment=position_data.get("comment", ""),
                    )
                )
        issues = list(evidence_result["evidence_issues"])
        issues.extend(
            {
                "code": "manual_price_change",
                "position_code": code,
                "message": "Цена изменена вручную; прежний источник удалён.",
            }
            for code in sorted(price_changed_codes)
        )
        return issues, bool(price_changed_codes), scope_changed

    def _derive_truth(self, estimate: EstimateDB) -> None:
        positions = [position for section in estimate.sections for position in section.positions]
        complete = bool(positions) and all(
            _decimal(position.quantity) > 0 and _decimal(position.price) > 0
            for position in positions
        )
        source_backed = complete and all(position.price_evidence for position in positions)
        independently_verified = source_backed and all(
            any(record.get("verification") == "verified" for record in position.price_evidence)
            for position in positions
        )
        if not complete:
            pricing_status = "needs_input"
        elif not source_backed:
            pricing_status = "preliminary"
        elif independently_verified:
            pricing_status = "verified"
        else:
            pricing_status = "source_backed"
        if pricing_status == "verified" and estimate.scope_status == "verified":
            estimate_status = "verified"
        elif pricing_status in {"source_backed", "verified"}:
            estimate_status = "source_backed"
        else:
            estimate_status = pricing_status
        estimate.pricing_status = pricing_status
        estimate.estimate_status = estimate_status
        estimate.price_sources = [
            copy.deepcopy(record)
            for position in positions
            for record in (position.price_evidence or [])
        ]
        issue_codes = {
            str(issue.get("code") or "")
            for issue in (estimate.evidence_issues or [])
            if isinstance(issue, dict)
        }
        if "manual_price_change" in issue_codes:
            estimate.source_note = (
                "Цена изменена вручную; прежний источник снят, требуется повторный "
                "сбор и проверка цены."
            )
        elif estimate_status == "needs_input":
            estimate.source_note = "Требуются индивидуальные объёмы и подтверждённые цены."
        elif pricing_status == "preliminary":
            estimate.source_note = "Цены не подтверждены источниками для каждой строки."
        elif pricing_status == "source_backed":
            estimate.source_note = "Цены связаны с актуальными датированными источниками."
        elif estimate.scope_status != "verified":
            estimate.source_note = (
                "Цены независимо проверены; исходные объёмы и состав работ ещё не подтверждены."
            )
        else:
            estimate.source_note = "Цены и исходные объёмы независимо проверены."

    def _calculate_entity(self, estimate: EstimateDB) -> None:
        # A named tax regime is authoritative for the VAT row.  NPD tax is a
        # contractor obligation on receipts and is not silently added to the
        # customer estimate as VAT.
        expected_vat = _TAX_REGIME_VAT_RATE.get(estimate.tax_regime or "")
        if expected_vat is not None:
            estimate.vat_rate = expected_vat
        calc_sections = []
        for section in estimate.sections:
            calc_positions = [
                CalcPosition(
                    id=position.id,
                    code=position.code,
                    name=position.name,
                    unit=position.unit,
                    quantity=position.quantity,
                    price=position.price,
                    source=position.source or "",
                    comment=position.comment or "",
                    sum=position.sum or "0",
                )
                for position in section.positions
            ]
            calc_sections.append(
                CalcSection(id=section.id, title=section.title, positions=calc_positions)
            )
        calc = calculate_estimate(
            CalcEstimate(
                id=estimate.id,
                title=estimate.title,
                status=EstimateStatus(estimate.status or "draft"),
                sections=calc_sections,
                overhead_rate=estimate.overhead_rate or "0",
                profit_rate=estimate.profit_rate or "0",
                contingency_rate=estimate.contingency_rate or "0",
                general_contractor_rate=estimate.general_contractor_rate or "0",
                discount_rate=estimate.discount_rate or "0",
                vat_rate=estimate.vat_rate or "22",
            )
        )
        estimate.subtotal = str(calc.subtotal)
        estimate.overhead_amount = str(calc.overhead_amount)
        estimate.profit_amount = str(calc.profit_amount)
        estimate.contingency_amount = str(calc.contingency_amount)
        estimate.general_contractor_amount = str(calc.general_contractor_amount)
        estimate.discount_amount = str(calc.discount_amount)
        estimate.vat_amount = str(calc.vat_amount)
        estimate.total = str(calc.total)
        for section, calculated_section in zip(estimate.sections, calc.sections, strict=True):
            section.subtotal = str(calculated_section.subtotal)
            for position, calculated_position in zip(
                section.positions,
                calculated_section.positions,
                strict=True,
            ):
                position.sum = str(calculated_position.sum)

    def _append_revision(self, estimate: EstimateDB) -> None:
        self.db.flush()
        snapshot = self._est_to_dict(estimate)
        self.db.add(
            EstimateRevisionDB(
                id=_uid(),
                estimate_id=estimate.id,
                version=estimate.version,
                snapshot=copy.deepcopy(snapshot),
                created_at=estimate.updated_at or _now(),
            )
        )

    def _est_to_dict(self, e: EstimateDB) -> dict:
        case_id = None
        if e.project_id:
            from app.project_case import project_case_id

            project = self.db.query(ProjectDB).filter(ProjectDB.id == e.project_id).first()
            case_id = project_case_id(project)
        return {
            "id": e.id, "project_id": e.project_id, "case_id": case_id,
            "version": int(e.version), "status": e.status,
            "estimate_status": e.estimate_status or "needs_input",
            "pricing_status": e.pricing_status or "needs_input",
            "scope_status": e.scope_status or "unverified",
            "source_note": e.source_note or "",
            "assumptions": copy.deepcopy(e.assumptions or []),
            "questions": copy.deepcopy(e.questions or []),
            "price_sources": copy.deepcopy(e.price_sources or []),
            "evidence_issues": copy.deepcopy(e.evidence_issues or []),
            "technology_card": copy.deepcopy(e.technology_card),
            "procurement_report": copy.deepcopy(e.procurement_report),
            "client_record_id": e.client_record_id,
            "object_record_id": e.object_record_id,
            "title": e.title, "client": e.client, "object_name": e.object_name,
            "region": e.region, "price_as_of": e.price_as_of, "currency": e.currency,
            "overhead_rate": e.overhead_rate,
            "profit_rate": e.profit_rate or "0",
            "contingency_rate": e.contingency_rate or "0",
            "general_contractor_rate": e.general_contractor_rate or "0",
            "discount_rate": e.discount_rate or "0",
            "vat_rate": e.vat_rate,
            "tax_regime": e.tax_regime or "unspecified",
            "subtotal": e.subtotal, "overhead_amount": e.overhead_amount,
            "profit_amount": e.profit_amount or "0",
            "contingency_amount": e.contingency_amount or "0",
            "general_contractor_amount": e.general_contractor_amount or "0",
            "discount_amount": e.discount_amount or "0",
            "vat_amount": e.vat_amount, "total": e.total,
            "created_at": _iso_z(e.created_at),
            "updated_at": _iso_z(e.updated_at),
            "sections": [
                {
                    "id": s.id, "title": s.title, "subtotal": s.subtotal,
                    "positions": [
                        {
                            "id": p.id, "code": p.code, "name": p.name, "unit": p.unit,
                            "quantity": p.quantity, "price": p.price, "sum": p.sum,
                            "source": p.source,
                            "price_evidence": copy.deepcopy(p.price_evidence or []),
                            "comment": p.comment or "",
                        }
                        for p in s.positions
                    ],
                }
                for s in e.sections
            ],
        }

    # ── Documents ────────────────────────────────────────────────────────────

    def list_documents(self, type_: Optional[str] = None, page: int = 1, page_size: int = 20) -> dict:
        q = self.db.query(DocumentDB).filter(
            DocumentDB.scope_id == self._document_scope()
        )
        if type_:
            q = q.filter(DocumentDB.type == type_)
        total = q.count()
        items = q.order_by(DocumentDB.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {"items": [self._doc_to_dict(d) for d in items], "total": total}

    def get_document(self, doc_id: str) -> Optional[dict]:
        d = (
            self.db.query(DocumentDB)
            .filter(
                DocumentDB.id == doc_id,
                DocumentDB.scope_id == self._document_scope(),
            )
            .first()
        )
        return self._doc_to_dict(d) if d else None

    def create_document(self, data: dict) -> dict:
        self._require_owned_document_estimate(data.get("estimate_id"))
        doc_id = _uid()
        now = _now()
        d = DocumentDB(
            id=doc_id,
            scope_id=self._document_scope(),
            organization_id=self.organization_id,
            title=data.get("title", ""), type=data.get("type", "custom"),
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
        d = (
            self.db.query(DocumentDB)
            .filter(
                DocumentDB.id == doc_id,
                DocumentDB.scope_id == self._document_scope(),
            )
            .first()
        )
        if not d:
            return None
        if "estimate_id" in data:
            self._require_owned_document_estimate(data.get("estimate_id"))
        for field in ["title", "type", "client", "project", "content", "variables", "template", "status", "estimate_id"]:
            if field in data and data[field] is not None:
                setattr(d, field, data[field])
        d.updated_at = _now()
        self.db.commit()
        return self._doc_to_dict(d)

    def delete_document(self, doc_id: str) -> bool:
        d = (
            self.db.query(DocumentDB)
            .filter(
                DocumentDB.id == doc_id,
                DocumentDB.scope_id == self._document_scope(),
            )
            .first()
        )
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
        scope_id = self._document_scope()
        for e in self.db.query(EstimateDB).filter(EstimateDB.scope_id == scope_id).all():
            created_at = e.created_at.isoformat() + "Z" if e.created_at else ""
            updated_at = e.updated_at.isoformat() + "Z" if e.updated_at else ""
            common = {
                "source_id": e.id,
                "status": e.status,
                "client": e.client or "",
                "project": e.object_name or "",
                "file_size": 0,
                "created_at": created_at,
                "updated_at": updated_at,
                "version": e.version,
            }
            items.extend([
                {
                    **common,
                    "id": e.id,
                    "title": e.title,
                    "item_type": "estimate",
                    "source_type": "estimate",
                    "mime_type": "application/vnd.kolibri.estimate+json",
                    "open_url": f"/estimates?edit={e.id}",
                },
                {
                    **common,
                    "id": f"estimate:{e.id}:pdf:v{e.version}",
                    "title": f"{e.title} · PDF",
                    "item_type": "pdf",
                    "source_type": "estimate_pdf",
                    "mime_type": "application/pdf",
                    "filename": f"{e.title}.pdf",
                    "open_url": f"/api/v1/estimates/{e.id}/pdf?version={e.version}",
                    "download_url": f"/api/v1/estimates/{e.id}/pdf?version={e.version}",
                },
                {
                    **common,
                    "id": f"estimate:{e.id}:xlsx:v{e.version}",
                    "title": f"{e.title} · Excel",
                    "item_type": "table",
                    "source_type": "estimate_xlsx",
                    "mime_type": (
                        "application/vnd.openxmlformats-officedocument."
                        "spreadsheetml.sheet"
                    ),
                    "filename": f"{e.title}.xlsx",
                    "open_url": f"/api/v1/estimates/{e.id}/workbook?version={e.version}",
                    "download_url": (
                        f"/api/v1/estimates/{e.id}/export/xlsx?version={e.version}"
                    ),
                },
            ])
        for d in self.db.query(DocumentDB).filter(DocumentDB.scope_id == scope_id).all():
            created_at = d.created_at.isoformat() + "Z" if d.created_at else ""
            updated_at = d.updated_at.isoformat() + "Z" if d.updated_at else ""
            common = {
                "source_id": d.id,
                "status": d.status,
                "client": d.client or "",
                "project": d.project or "",
                "file_size": 0,
                "created_at": created_at,
                "updated_at": updated_at,
                "estimate_id": d.estimate_id,
            }
            items.extend([
                {
                    **common,
                    "id": d.id,
                    "title": d.title,
                    "item_type": "document",
                    "source_type": "document",
                    "document_type": d.type,
                    "mime_type": "application/vnd.kolibri.document+json",
                    "open_url": f"/documents?edit={d.id}",
                },
                {
                    **common,
                    "id": f"document:{d.id}:pdf",
                    "title": f"{d.title} · PDF",
                    "item_type": "pdf",
                    "source_type": "document_pdf",
                    "document_type": d.type,
                    "mime_type": "application/pdf",
                    "filename": f"{d.title}.pdf",
                    "open_url": f"/api/v1/documents/{d.id}/pdf",
                    "download_url": f"/api/v1/documents/{d.id}/pdf",
                },
            ])
            if d.type == "report":
                items.append({
                    **common,
                    "id": f"document:{d.id}:report",
                    "title": d.title,
                    "item_type": "report",
                    "source_type": "document",
                    "document_type": d.type,
                    "mime_type": "application/vnd.kolibri.document+json",
                    "open_url": f"/documents?edit={d.id}",
                })
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


_DEMO_SEED_ENV = "KOLIBRI_DEMO_SEED_ENABLED"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def demo_seed_enabled() -> bool:
    """Return true only after an explicit operator opt-in.

    Production and fresh developer databases must start empty.  Sample rows
    are useful for an intentional visual demo, but must never masquerade as
    live estimates, documents, agents, nodes or tasks.
    """
    return os.getenv(_DEMO_SEED_ENV, "").strip().lower() in _TRUE_VALUES


def seed_demo_data_if_enabled(db: Session) -> bool:
    """Seed sample rows only when ``KOLIBRI_DEMO_SEED_ENABLED`` is explicit."""
    if not demo_seed_enabled():
        return False
    seed_db(db)
    return True


def seed_db(db: Session):
    """Seed database with sample data (same as legacy Store._seed)."""
    if db.query(EstimateDB).count() > 0:
        return

    storage = DBStorage(db, scope_id="demo:seed")

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
