"""Create durable owner-scoped Responses and ordered event ledger.

Revision ID: 010_durable_responses
Revises: 009_document_scope
Create Date: 2026-07-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "010_durable_responses"
down_revision: Union[str, None] = "009_document_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "public_responses" not in tables:
        op.create_table(
            "public_responses",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("owner_scope", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=True),
            sa.Column("request_hash", sa.String(), nullable=True),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "owner_scope",
                "idempotency_key",
                name="uq_public_responses_scope_idempotency",
            ),
        )
        op.create_index(
            "ix_public_responses_scope_updated",
            "public_responses",
            ["owner_scope", "updated_at"],
        )
        op.create_index(
            "ix_public_responses_status_updated",
            "public_responses",
            ["status", "updated_at"],
        )
    if "public_response_events" not in tables:
        op.create_table(
            "public_response_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "response_id",
                sa.String(),
                sa.ForeignKey("public_responses.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "response_id",
                "sequence",
                name="uq_public_response_events_sequence",
            ),
        )
        op.create_index(
            "ix_public_response_events_response_sequence",
            "public_response_events",
            ["response_id", "sequence"],
        )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "public_response_events" in tables:
        op.drop_table("public_response_events")
    if "public_responses" in tables:
        op.drop_table("public_responses")
