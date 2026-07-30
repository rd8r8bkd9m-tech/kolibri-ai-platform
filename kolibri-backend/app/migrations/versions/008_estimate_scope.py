"""Bind every estimate to an isolated project principal scope.

Revision ID: 008_estimate_scope
Revises: 007_estimate_truth
Create Date: 2026-07-14

Existing rows cannot be attributed safely to a browser or user after the fact,
so they are assigned an unreachable quarantine scope.  An explicit, audited
owner migration may reassign them later; public sessions never inherit them.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "008_estimate_scope"
down_revision: Union[str, None] = "007_estimate_truth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_ESTIMATE_SCOPE = "legacy:quarantined"


def _inspector():
    return sa.inspect(op.get_bind())


def _column_names() -> set[str]:
    return {column["name"] for column in _inspector().get_columns("estimates")}


def _index_names() -> set[str]:
    return {index["name"] for index in _inspector().get_indexes("estimates")}


def upgrade() -> None:
    if "scope_id" not in _column_names():
        op.add_column(
            "estimates",
            sa.Column(
                "scope_id",
                sa.String(),
                nullable=False,
                server_default=LEGACY_ESTIMATE_SCOPE,
            ),
        )

    # Fail closed for any partially migrated/custom database as well as the
    # normal pre-008 schema.  Empty ownership is never interpreted as public.
    op.execute(
        sa.text(
            "UPDATE estimates SET scope_id = :scope_id "
            "WHERE scope_id IS NULL OR TRIM(scope_id) = ''"
        ).bindparams(scope_id=LEGACY_ESTIMATE_SCOPE)
    )

    scope_column = next(
        column for column in _inspector().get_columns("estimates")
        if column["name"] == "scope_id"
    )
    if bool(scope_column.get("nullable")):
        with op.batch_alter_table("estimates") as batch_op:
            batch_op.alter_column(
                "scope_id",
                existing_type=scope_column["type"],
                nullable=False,
                server_default=LEGACY_ESTIMATE_SCOPE,
            )

    if "ix_estimates_scope_created_at" not in _index_names():
        op.create_index(
            "ix_estimates_scope_created_at",
            "estimates",
            ["scope_id", "created_at"],
        )
    if "ix_estimates_scope_status" not in _index_names():
        op.create_index(
            "ix_estimates_scope_status",
            "estimates",
            ["scope_id", "status"],
        )


def downgrade() -> None:
    indexes = _index_names()
    if "ix_estimates_scope_status" in indexes:
        op.drop_index("ix_estimates_scope_status", table_name="estimates")
    if "ix_estimates_scope_created_at" in indexes:
        op.drop_index("ix_estimates_scope_created_at", table_name="estimates")
    if "scope_id" in _column_names():
        op.drop_column("estimates", "scope_id")
