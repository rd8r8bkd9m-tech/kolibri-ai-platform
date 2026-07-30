"""Persist the explicit tax regime selected for an estimate.

Revision ID: 012_estimate_tax_regime
Revises: 011_organization_tenancy
Create Date: 2026-07-16
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "012_estimate_tax_regime"
down_revision: Union[str, None] = "011_organization_tenancy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("estimates")}
    if "tax_regime" not in columns:
        op.add_column(
            "estimates",
            sa.Column(
                "tax_regime",
                sa.String(),
                nullable=False,
                server_default="unspecified",
            ),
        )
    for name in (
        "profit_rate",
        "contingency_rate",
        "general_contractor_rate",
        "discount_rate",
        "profit_amount",
        "contingency_amount",
        "general_contractor_amount",
        "discount_amount",
    ):
        if name not in columns:
            op.add_column(
                "estimates",
                sa.Column(name, sa.String(), nullable=False, server_default="0"),
            )
    inspector = sa.inspect(op.get_bind())
    if "work_catalog" not in set(inspector.get_table_names()):
        op.create_table(
            "work_catalog",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("scope_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("normalized_key", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("unit", sa.String(), nullable=False, server_default="шт"),
            sa.Column("category", sa.String(), nullable=False, server_default=""),
            sa.Column("latest_price", sa.String(), nullable=False, server_default="0"),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("status", sa.String(), nullable=False, server_default="approved"),
            sa.Column("source_estimate_id", sa.String(), nullable=True),
            sa.Column("source_version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_estimate_id"], ["estimates.id"], ondelete="SET NULL"),
            sa.UniqueConstraint("scope_id", "normalized_key", "unit", name="uq_work_catalog_scope_key_unit"),
        )
        op.create_index("ix_work_catalog_scope_updated", "work_catalog", ["scope_id", "updated_at"])
        op.create_index("ix_work_catalog_organization_status", "work_catalog", ["organization_id", "status"])


def downgrade() -> None:
    if "work_catalog" in set(sa.inspect(op.get_bind()).get_table_names()):
        op.drop_index("ix_work_catalog_organization_status", table_name="work_catalog")
        op.drop_index("ix_work_catalog_scope_updated", table_name="work_catalog")
        op.drop_table("work_catalog")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("estimates")}
    for name in (
        "discount_amount",
        "general_contractor_amount",
        "contingency_amount",
        "profit_amount",
        "discount_rate",
        "general_contractor_rate",
        "contingency_rate",
        "profit_rate",
    ):
        if name in columns:
            op.drop_column("estimates", name)
    if "tax_regime" in columns:
        op.drop_column("estimates", "tax_regime")
