"""Add tenant-scoped clients and construction objects linked to estimates.

Revision ID: 014_clients_objects
Revises: 013_technology_cards
Create Date: 2026-07-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "014_clients_objects"
down_revision: Union[str, None] = "013_technology_cards"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _tables() -> set[str]:
    return set(_inspector().get_table_names())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _index_names(table: str) -> set[str]:
    return {index["name"] for index in _inspector().get_indexes(table)}


def _ensure_index(table: str, name: str, columns: list[str]) -> None:
    if name not in _index_names(table):
        op.create_index(name, table, columns)


def _add_nullable_reference(table: str, column: str, target: str) -> None:
    """Add a nullable FK without SQLite's unsupported ALTER CONSTRAINT path."""

    if op.get_bind().dialect.name == "sqlite":
        # Identifiers are migration constants, never request data.
        op.execute(
            sa.text(
                f'ALTER TABLE "{table}" ADD COLUMN "{column}" VARCHAR '
                f"REFERENCES {target}(id) ON DELETE SET NULL"
            )
        )
        return
    op.add_column(
        table,
        sa.Column(
            column,
            sa.String(),
            sa.ForeignKey(f"{target}.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def upgrade() -> None:
    if "clients" not in _tables():
        op.create_table(
            "clients",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("scope_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("normalized_key", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("phone", sa.String(), nullable=False, server_default=""),
            sa.Column("email", sa.String(), nullable=False, server_default=""),
            sa.Column(
                "source",
                sa.String(),
                nullable=False,
                server_default="chat_estimate",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["organization_id"],
                ["organizations.id"],
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint(
                "scope_id",
                "normalized_key",
                name="uq_clients_scope_key",
            ),
        )
    _ensure_index("clients", "ix_clients_scope_updated", ["scope_id", "updated_at"])
    _ensure_index(
        "clients",
        "ix_clients_organization_updated",
        ["organization_id", "updated_at"],
    )

    if "construction_objects" not in _tables():
        op.create_table(
            "construction_objects",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("scope_id", sa.String(), nullable=False),
            sa.Column("organization_id", sa.String(), nullable=True),
            sa.Column("client_id", sa.String(), nullable=True),
            sa.Column("normalized_key", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("address", sa.String(), nullable=False, server_default=""),
            sa.Column("region", sa.String(), nullable=False, server_default=""),
            sa.Column(
                "source",
                sa.String(),
                nullable=False,
                server_default="chat_estimate",
            ),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(
                ["organization_id"],
                ["organizations.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["client_id"],
                ["clients.id"],
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint(
                "scope_id",
                "normalized_key",
                name="uq_construction_objects_scope_key",
            ),
        )
    _ensure_index(
        "construction_objects",
        "ix_construction_objects_scope_updated",
        ["scope_id", "updated_at"],
    )
    _ensure_index(
        "construction_objects",
        "ix_construction_objects_organization_updated",
        ["organization_id", "updated_at"],
    )

    estimate_columns = _columns("estimates")
    if "client_record_id" not in estimate_columns:
        _add_nullable_reference("estimates", "client_record_id", "clients")
    if "object_record_id" not in estimate_columns:
        _add_nullable_reference(
            "estimates",
            "object_record_id",
            "construction_objects",
        )
    _ensure_index(
        "estimates",
        "ix_estimates_scope_client",
        ["scope_id", "client_record_id"],
    )
    _ensure_index(
        "estimates",
        "ix_estimates_scope_object",
        ["scope_id", "object_record_id"],
    )


def downgrade() -> None:
    estimate_indexes = _index_names("estimates")
    if "ix_estimates_scope_object" in estimate_indexes:
        op.drop_index("ix_estimates_scope_object", table_name="estimates")
    if "ix_estimates_scope_client" in estimate_indexes:
        op.drop_index("ix_estimates_scope_client", table_name="estimates")
    estimate_columns = _columns("estimates")
    removable = [
        column
        for column in ("object_record_id", "client_record_id")
        if column in estimate_columns
    ]
    if removable:
        with op.batch_alter_table("estimates") as batch_op:
            for column in removable:
                batch_op.drop_column(column)
    if "construction_objects" in _tables():
        op.drop_table("construction_objects")
    if "clients" in _tables():
        op.drop_table("clients")
