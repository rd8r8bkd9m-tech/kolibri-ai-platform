"""Add ordered estimate state and immutable saved revisions.

Revision ID: 005_estimate_revisions
Revises: 004_telegram_async_queue
Create Date: 2026-07-13
"""

from datetime import datetime, timezone
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op


revision: str = "005_estimate_revisions"
down_revision: Union[str, None] = "004_telegram_async_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_REVISION_COLUMNS = {"id", "estimate_id", "version", "snapshot", "created_at"}


def _inspector():
    return sa.inspect(op.get_bind())


def _ensure_index(table: str, name: str, columns: list[str]) -> None:
    if name not in {index["name"] for index in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def _as_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _iso_z(value: object) -> str:
    date = _as_datetime(value)
    if date.tzinfo is None:
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _backfill_sort_order() -> None:
    bind = op.get_bind()
    sections = bind.execute(
        sa.text("SELECT id, estimate_id FROM sections ORDER BY estimate_id, id")
    ).mappings()
    section_offsets: dict[str, int] = {}
    for section in sections:
        estimate_id = str(section["estimate_id"])
        sort_order = section_offsets.get(estimate_id, 0)
        bind.execute(
            sa.text("UPDATE sections SET sort_order = :sort_order WHERE id = :id"),
            {"sort_order": sort_order, "id": section["id"]},
        )
        section_offsets[estimate_id] = sort_order + 1

    positions = bind.execute(
        sa.text("SELECT id, section_id FROM positions ORDER BY section_id, id")
    ).mappings()
    position_offsets: dict[str, int] = {}
    for position in positions:
        section_id = str(position["section_id"])
        sort_order = position_offsets.get(section_id, 0)
        bind.execute(
            sa.text("UPDATE positions SET sort_order = :sort_order WHERE id = :id"),
            {"sort_order": sort_order, "id": position["id"]},
        )
        position_offsets[section_id] = sort_order + 1


def _estimate_snapshot(estimate: dict[str, object]) -> dict[str, object]:
    bind = op.get_bind()
    sections: list[dict[str, object]] = []
    section_rows = bind.execute(
        sa.text(
            "SELECT id, title, subtotal FROM sections "
            "WHERE estimate_id = :estimate_id ORDER BY sort_order, id"
        ),
        {"estimate_id": estimate["id"]},
    ).mappings()
    for section in section_rows:
        position_rows = bind.execute(
            sa.text(
                "SELECT id, code, name, unit, quantity, price, sum, source, comment "
                "FROM positions WHERE section_id = :section_id ORDER BY sort_order, id"
            ),
            {"section_id": section["id"]},
        ).mappings()
        sections.append(
            {
                "id": section["id"],
                "title": section["title"] or "",
                "subtotal": section["subtotal"] or "0",
                "positions": [
                    {
                        "id": position["id"],
                        "code": position["code"] or "",
                        "name": position["name"] or "",
                        "unit": position["unit"] or "шт",
                        "quantity": position["quantity"] or "0",
                        "price": position["price"] or "0",
                        "sum": position["sum"] or "0",
                        "source": position["source"] or "",
                        "comment": position["comment"] or "",
                    }
                    for position in position_rows
                ],
            }
        )
    return {
        "id": estimate["id"],
        "version": int(estimate["version"] or 1),
        "status": estimate["status"] or "draft",
        "title": estimate["title"] or "",
        "client": estimate["client"] or "",
        "object_name": estimate["object_name"] or "",
        "region": estimate["region"] or "",
        "currency": estimate["currency"] or "RUB",
        "overhead_rate": estimate["overhead_rate"] or "0",
        "vat_rate": estimate["vat_rate"] or "22",
        "subtotal": estimate["subtotal"] or "0",
        "overhead_amount": estimate["overhead_amount"] or "0",
        "vat_amount": estimate["vat_amount"] or "0",
        "total": estimate["total"] or "0",
        "created_at": _iso_z(estimate["created_at"]),
        "updated_at": _iso_z(estimate["updated_at"]),
        "sections": sections,
    }


def _backfill_current_revisions() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    revisions = sa.Table("estimate_revisions", metadata, autoload_with=bind)
    estimates = bind.execute(
        sa.text(
            "SELECT id, version, status, title, client, object_name, region, currency, "
            "overhead_rate, vat_rate, subtotal, overhead_amount, vat_amount, total, "
            "created_at, updated_at FROM estimates ORDER BY id"
        )
    ).mappings()
    for estimate_row in estimates:
        estimate = dict(estimate_row)
        version = int(estimate["version"] or 1)
        exists = bind.execute(
            sa.select(revisions.c.id).where(
                revisions.c.estimate_id == estimate["id"],
                revisions.c.version == version,
            )
        ).first()
        if exists is not None:
            continue
        bind.execute(
            revisions.insert().values(
                id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"kolibri:estimate-revision:{estimate['id']}:{version}",
                    )
                ),
                estimate_id=estimate["id"],
                version=version,
                snapshot=_estimate_snapshot(estimate),
                created_at=_as_datetime(estimate["updated_at"] or estimate["created_at"]),
            )
        )


def upgrade() -> None:
    inspector = _inspector()
    if "sort_order" not in {column["name"] for column in inspector.get_columns("sections")}:
        op.add_column(
            "sections",
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
    if "sort_order" not in {column["name"] for column in _inspector().get_columns("positions")}:
        op.add_column(
            "positions",
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        )
    op.execute(sa.text("UPDATE estimates SET version = 1 WHERE version IS NULL"))
    _backfill_sort_order()

    if "estimate_revisions" not in _inspector().get_table_names():
        op.create_table(
            "estimate_revisions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("estimate_id", sa.String(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["estimate_id"], ["estimates.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "estimate_id",
                "version",
                name="uq_estimate_revisions_version",
            ),
        )
    else:
        columns = {
            column["name"] for column in _inspector().get_columns("estimate_revisions")
        }
        missing = sorted(_REVISION_COLUMNS - columns)
        if missing:
            raise RuntimeError(
                "existing estimate_revisions table is incompatible; "
                f"missing columns: {', '.join(missing)}"
            )
        unique_columns = {
            tuple(constraint.get("column_names") or [])
            for constraint in _inspector().get_unique_constraints("estimate_revisions")
        }
        if ("estimate_id", "version") not in unique_columns:
            raise RuntimeError(
                "estimate_revisions is missing its estimate/version uniqueness contract"
            )
    _ensure_index(
        "estimate_revisions",
        "ix_estimate_revisions_estimate_version",
        ["estimate_id", "version"],
    )
    _backfill_current_revisions()


def downgrade() -> None:
    op.drop_index(
        "ix_estimate_revisions_estimate_version",
        table_name="estimate_revisions",
    )
    op.drop_table("estimate_revisions")
    op.drop_column("positions", "sort_order")
    op.drop_column("sections", "sort_order")
