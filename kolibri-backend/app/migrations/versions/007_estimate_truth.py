"""Persist estimate truth status and immutable price evidence.

Revision ID: 007_estimate_truth
Revises: 006_project_handoffs
Create Date: 2026-07-14
"""

from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "007_estimate_truth"
down_revision: Union[str, None] = "006_project_handoffs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ESTIMATE_COLUMNS = {
    "estimate_status": sa.Column(
        "estimate_status", sa.String(), nullable=False, server_default="needs_input"
    ),
    "pricing_status": sa.Column(
        "pricing_status", sa.String(), nullable=False, server_default="needs_input"
    ),
    "scope_status": sa.Column(
        "scope_status", sa.String(), nullable=False, server_default="unverified"
    ),
    "source_note": sa.Column("source_note", sa.Text(), nullable=False, server_default=""),
    "assumptions": sa.Column("assumptions", sa.JSON(), nullable=False, server_default="[]"),
    "questions": sa.Column("questions", sa.JSON(), nullable=False, server_default="[]"),
    "price_sources": sa.Column("price_sources", sa.JSON(), nullable=False, server_default="[]"),
    "evidence_issues": sa.Column("evidence_issues", sa.JSON(), nullable=False, server_default="[]"),
}


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _decimal(value) -> Decimal:
    try:
        parsed = Decimal(str(value if value is not None else "0"))
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return parsed if parsed.is_finite() else Decimal("0")


def _truth_for_positions(positions: list[dict], scope_status: str) -> tuple[str, str]:
    complete = bool(positions) and all(
        _decimal(position.get("quantity")) > 0 and _decimal(position.get("price")) > 0
        for position in positions
    )
    source_backed = complete and all(position.get("price_evidence") for position in positions)
    independently_verified = source_backed and all(
        any(record.get("verification") == "verified" for record in position.get("price_evidence") or [])
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
    if pricing_status == "verified" and scope_status == "verified":
        estimate_status = "verified"
    elif pricing_status in {"source_backed", "verified"}:
        estimate_status = "source_backed"
    else:
        estimate_status = pricing_status
    return estimate_status, pricing_status


def _backfill_live_rows() -> None:
    bind = op.get_bind()
    estimate_rows = bind.execute(sa.text("SELECT id, scope_status FROM estimates ORDER BY id")).mappings()
    for estimate in estimate_rows:
        positions = [
            dict(row)
            for row in bind.execute(
                sa.text(
                    "SELECT p.quantity, p.price, p.price_evidence "
                    "FROM positions p JOIN sections s ON s.id = p.section_id "
                    "WHERE s.estimate_id = :estimate_id ORDER BY s.sort_order, p.sort_order, p.id"
                ),
                {"estimate_id": estimate["id"]},
            ).mappings()
        ]
        for position in positions:
            evidence = position.get("price_evidence")
            if isinstance(evidence, str):
                try:
                    position["price_evidence"] = json.loads(evidence)
                except json.JSONDecodeError:
                    position["price_evidence"] = []
            elif not isinstance(evidence, list):
                position["price_evidence"] = []
        estimate_status, pricing_status = _truth_for_positions(
            positions, str(estimate.get("scope_status") or "unverified")
        )
        bind.execute(
            sa.text(
                "UPDATE estimates SET estimate_status = :estimate_status, "
                "pricing_status = :pricing_status WHERE id = :estimate_id"
            ),
            {
                "estimate_status": estimate_status,
                "pricing_status": pricing_status,
                "estimate_id": estimate["id"],
            },
        )


def _backfill_revision_snapshots() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    revisions = sa.Table("estimate_revisions", metadata, autoload_with=bind)
    for row in bind.execute(sa.select(revisions.c.id, revisions.c.snapshot)).mappings():
        snapshot = row["snapshot"]
        if isinstance(snapshot, str):
            try:
                snapshot = json.loads(snapshot)
            except json.JSONDecodeError:
                continue
        if not isinstance(snapshot, dict):
            continue
        snapshot = copy.deepcopy(snapshot)
        positions: list[dict] = []
        for section in snapshot.get("sections") or []:
            if not isinstance(section, dict):
                continue
            for position in section.get("positions") or []:
                if not isinstance(position, dict):
                    continue
                position["price_evidence"] = (
                    position.get("price_evidence")
                    if isinstance(position.get("price_evidence"), list)
                    else []
                )
                positions.append(position)
        scope_status = str(snapshot.get("scope_status") or "unverified")
        estimate_status, pricing_status = _truth_for_positions(positions, scope_status)
        snapshot["estimate_status"] = estimate_status
        snapshot["pricing_status"] = pricing_status
        snapshot["scope_status"] = scope_status
        snapshot["source_note"] = str(snapshot.get("source_note") or "Legacy snapshot without verified price evidence.")
        snapshot["assumptions"] = snapshot.get("assumptions") if isinstance(snapshot.get("assumptions"), list) else []
        snapshot["questions"] = snapshot.get("questions") if isinstance(snapshot.get("questions"), list) else []
        snapshot["price_sources"] = [
            copy.deepcopy(record)
            for position in positions
            for record in position.get("price_evidence") or []
        ]
        snapshot["evidence_issues"] = (
            snapshot.get("evidence_issues")
            if isinstance(snapshot.get("evidence_issues"), list)
            else []
        )
        bind.execute(
            revisions.update().where(revisions.c.id == row["id"]).values(snapshot=snapshot)
        )


def upgrade() -> None:
    existing_estimate_columns = _columns("estimates")
    for name, column in _ESTIMATE_COLUMNS.items():
        if name not in existing_estimate_columns:
            op.add_column("estimates", column)
    if "price_evidence" not in _columns("positions"):
        op.add_column(
            "positions",
            sa.Column("price_evidence", sa.JSON(), nullable=False, server_default="[]"),
        )
    bind = op.get_bind()
    metadata = sa.MetaData()
    estimates = sa.Table("estimates", metadata, autoload_with=bind)
    positions = sa.Table("positions", metadata, autoload_with=bind)
    for name in ("assumptions", "questions", "price_sources", "evidence_issues"):
        bind.execute(
            estimates.update()
            .where(estimates.c[name].is_(None))
            .values({name: []})
        )
    bind.execute(
        positions.update()
        .where(positions.c.price_evidence.is_(None))
        .values(price_evidence=[])
    )
    _backfill_live_rows()
    _backfill_revision_snapshots()


def downgrade() -> None:
    op.drop_column("positions", "price_evidence")
    for name in reversed(tuple(_ESTIMATE_COLUMNS)):
        op.drop_column("estimates", name)
