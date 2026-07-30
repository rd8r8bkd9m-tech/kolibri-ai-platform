"""Persist Telegram-origin delivery evidence.

Revision ID: 003_telegram_delivery_evidence
Revises: 002_project_history
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "003_telegram_delivery_evidence"
down_revision: Union[str, None] = "002_project_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_REQUIRED_COLUMNS = {
    "id",
    "update_id",
    "response_method",
    "origin_network",
    "verified_at",
    "updated_at",
}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "telegram_delivery_evidence" not in inspector.get_table_names():
        op.create_table(
            "telegram_delivery_evidence",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("update_id", sa.Integer(), nullable=False),
            sa.Column("response_method", sa.String(), nullable=False),
            sa.Column("origin_network", sa.String(), nullable=False),
            sa.Column("verified_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        return

    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("telegram_delivery_evidence")
    }
    missing = sorted(_REQUIRED_COLUMNS - columns)
    if missing:
        raise RuntimeError(
            "existing telegram_delivery_evidence table is incompatible; "
            f"missing columns: {', '.join(missing)}"
        )


def downgrade() -> None:
    op.drop_table("telegram_delivery_evidence")
