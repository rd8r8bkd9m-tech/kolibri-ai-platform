"""Add universal technology cards and tenant-scoped approved catalog.

Revision ID: 013_technology_cards
Revises: 012_estimate_tax_regime
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "013_technology_cards"
down_revision: Union[str, None] = "012_estimate_tax_regime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    estimate_columns = {column["name"] for column in inspector.get_columns("estimates")}
    if "technology_card" not in estimate_columns:
        op.add_column("estimates", sa.Column("technology_card", sa.JSON(), nullable=True))
    if "procurement_report" not in estimate_columns:
        op.add_column("estimates", sa.Column("procurement_report", sa.JSON(), nullable=True))

    if "technology_catalog" not in set(sa.inspect(bind).get_table_names()):
        op.create_table(
            "technology_catalog",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("scope_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("content_sha256", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("object_type", sa.String(), nullable=False, server_default=""),
            sa.Column("card", sa.JSON(), nullable=False),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="approved"),
            sa.Column("source_estimate_id", sa.String(), nullable=True),
            sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_estimate_id"], ["estimates.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("scope_id", "content_sha256", name="uq_technology_catalog_scope_hash"),
        )
        op.create_index(
            "ix_technology_catalog_scope_updated",
            "technology_catalog",
            ["scope_id", "updated_at"],
        )
        op.create_index(
            "ix_technology_catalog_organization_status",
            "technology_catalog",
            ["organization_id", "status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "technology_catalog" in set(sa.inspect(bind).get_table_names()):
        op.drop_index("ix_technology_catalog_organization_status", table_name="technology_catalog")
        op.drop_index("ix_technology_catalog_scope_updated", table_name="technology_catalog")
        op.drop_table("technology_catalog")
    estimate_columns = {column["name"] for column in sa.inspect(bind).get_columns("estimates")}
    if "technology_card" in estimate_columns:
        op.drop_column("estimates", "technology_card")
    if "procurement_report" in estimate_columns:
        op.drop_column("estimates", "procurement_report")
