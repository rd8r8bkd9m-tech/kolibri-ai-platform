"""Bind documents to the signed project principal scope.

Revision ID: 009_document_scope
Revises: 008_estimate_scope
Create Date: 2026-07-14

Legacy ownership cannot be inferred safely.  Existing documents therefore move
to an unreachable quarantine scope until an explicit audited owner migration
reassigns them.  The migration also closes an older schema gap where Alembic
did not create the optional ``documents.estimate_id`` relation.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "009_document_scope"
down_revision: Union[str, None] = "008_estimate_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_DOCUMENT_SCOPE = "legacy:quarantined"
ESTIMATE_FK_NAME = "fk_documents_estimate_id_estimates"


def _inspector():
    return sa.inspect(op.get_bind())


def _columns() -> dict[str, dict]:
    return {column["name"]: column for column in _inspector().get_columns("documents")}


def _index_names() -> set[str]:
    return {index["name"] for index in _inspector().get_indexes("documents")}


def _estimate_foreign_key() -> dict | None:
    for foreign_key in _inspector().get_foreign_keys("documents"):
        if (
            tuple(foreign_key.get("constrained_columns") or []) == ("estimate_id",)
            and foreign_key.get("referred_table") == "estimates"
            and tuple(foreign_key.get("referred_columns") or []) == ("id",)
        ):
            return foreign_key
    return None


def upgrade() -> None:
    columns = _columns()
    if "estimate_id" not in columns:
        op.add_column(
            "documents",
            sa.Column("estimate_id", sa.String(), nullable=True),
        )

    if _estimate_foreign_key() is None:
        with op.batch_alter_table("documents") as batch_op:
            batch_op.create_foreign_key(
                ESTIMATE_FK_NAME,
                "estimates",
                ["estimate_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if "scope_id" not in _columns():
        op.add_column(
            "documents",
            sa.Column(
                "scope_id",
                sa.String(),
                nullable=False,
                server_default=LEGACY_DOCUMENT_SCOPE,
            ),
        )

    # Blank ownership from partially migrated/custom databases is never
    # interpreted as a public/shared scope.
    op.execute(
        sa.text(
            "UPDATE documents SET scope_id = :scope_id "
            "WHERE scope_id IS NULL OR TRIM(scope_id) = ''"
        ).bindparams(scope_id=LEGACY_DOCUMENT_SCOPE)
    )

    scope_column = _columns()["scope_id"]
    if bool(scope_column.get("nullable")):
        with op.batch_alter_table("documents") as batch_op:
            batch_op.alter_column(
                "scope_id",
                existing_type=scope_column["type"],
                nullable=False,
                server_default=LEGACY_DOCUMENT_SCOPE,
            )

    indexes = _index_names()
    if "ix_documents_scope_created_at" not in indexes:
        op.create_index(
            "ix_documents_scope_created_at",
            "documents",
            ["scope_id", "created_at"],
        )
    if "ix_documents_scope_status" not in indexes:
        op.create_index(
            "ix_documents_scope_status",
            "documents",
            ["scope_id", "status"],
        )


def downgrade() -> None:
    indexes = _index_names()
    if "ix_documents_scope_status" in indexes:
        op.drop_index("ix_documents_scope_status", table_name="documents")
    if "ix_documents_scope_created_at" in indexes:
        op.drop_index("ix_documents_scope_created_at", table_name="documents")
    if "scope_id" in _columns():
        op.drop_column("documents", "scope_id")

    # A standard Alembic chain creates the relation in this revision.  An
    # adopted create_all database may already have an unnamed equivalent; keep
    # that pre-existing column/constraint intact on downgrade.
    foreign_key = _estimate_foreign_key()
    if foreign_key and foreign_key.get("name") == ESTIMATE_FK_NAME:
        with op.batch_alter_table("documents") as batch_op:
            batch_op.drop_constraint(ESTIMATE_FK_NAME, type_="foreignkey")
            batch_op.drop_column("estimate_id")
