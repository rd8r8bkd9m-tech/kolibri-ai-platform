"""Storage abstraction — DBStorage (SQLAlchemy) and InMemoryStorage (legacy)."""
import copy
import os
import uuid
import random
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy.orm import Session
from app.models import (
    AgentDB,
    DocumentDB,
    EstimateDB,
    EstimateRevisionDB,
    NodeDB,
    PositionDB,
    SectionDB,
    TaskDB,
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
        e = EstimateDB(
            id=est_id,
            scope_id=self._estimate_scope(),
            organization_id=self.organization_id,
            version=1,
            title=data.get("title", ""), client=data.get("client", ""),
            object_name=data.get("object_name", ""), region=data.get("region", ""),
            currency=data.get("currency", "RUB"),
            overhead_rate=data.get("overhead_rate", "0"),
            vat_rate=data.get("vat_rate", "22"),
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
            evidence_issues=_dedupe_issues(data.get("evidence_issues")),
            created_at=now, updated_at=now,
        )
        try:
            self.db.add(e)
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
                "currency",
                "overhead_rate",
                "vat_rate",
                "status",
            ]:
                if field in data and data[field] is not None:
                    setattr(e, field, data[field])
            for field in ["assumptions", "questions"]:
                if field in data and data[field] is not None:
                    setattr(e, field, _json_list(data[field]))
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
            "overhead_rate": orig["overhead_rate"], "vat_rate": orig["vat_rate"],
            "scope_status": orig["scope_status"],
            "source_note": orig["source_note"],
            "assumptions": copy.deepcopy(orig["assumptions"]),
            "questions": copy.deepcopy(orig["questions"]),
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
                vat_rate=estimate.vat_rate or "22",
            )
        )
        estimate.subtotal = str(calc.subtotal)
        estimate.overhead_amount = str(calc.overhead_amount)
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
        return {
            "id": e.id, "version": int(e.version), "status": e.status,
            "estimate_status": e.estimate_status or "needs_input",
            "pricing_status": e.pricing_status or "needs_input",
            "scope_status": e.scope_status or "unverified",
            "source_note": e.source_note or "",
            "assumptions": copy.deepcopy(e.assumptions or []),
            "questions": copy.deepcopy(e.questions or []),
            "price_sources": copy.deepcopy(e.price_sources or []),
            "evidence_issues": copy.deepcopy(e.evidence_issues or []),
            "title": e.title, "client": e.client, "object_name": e.object_name,
            "region": e.region, "currency": e.currency,
            "overhead_rate": e.overhead_rate, "vat_rate": e.vat_rate,
            "subtotal": e.subtotal, "overhead_amount": e.overhead_amount,
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
            items.append({"id": e.id, "title": e.title, "item_type": "estimate",
                          "source_id": e.id, "source_type": "estimate",
                          "status": e.status, "client": e.client or "",
                          "project": e.object_name or "", "file_size": 0,
                          "created_at": e.created_at.isoformat() + "Z" if e.created_at else "",
                          "updated_at": e.updated_at.isoformat() + "Z" if e.updated_at else ""})
        for d in self.db.query(DocumentDB).filter(DocumentDB.scope_id == scope_id).all():
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
