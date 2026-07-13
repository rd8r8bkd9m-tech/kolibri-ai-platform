"""Add durable project and conversation history.

Revision ID: 002_project_history
Revises: 001_initial
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "002_project_history"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector():
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _require_columns(table: str, expected: set[str]) -> None:
    missing = sorted(expected - _columns(table))
    if missing:
        raise RuntimeError(f"existing {table} table is incompatible; missing columns: {', '.join(missing)}")


def _ensure_index(table: str, name: str, columns: list[str]) -> None:
    if name not in {index["name"] for index in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def _require_unique(table: str, names: set[str]) -> None:
    existing = {constraint["name"] for constraint in _inspector().get_unique_constraints(table)}
    missing = sorted(names - existing)
    if missing:
        raise RuntimeError(f"existing {table} table is incompatible; missing unique constraints: {', '.join(missing)}")


def upgrade() -> None:
    if "projects" not in _inspector().get_table_names():
        op.create_table(
            "projects",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("scope_id", sa.String(), nullable=False),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("title_source", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("message_count", sa.Integer(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=True),
            sa.Column("create_request_hash", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("last_message_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("scope_id", "idempotency_key", name="uq_projects_scope_idempotency"),
        )
    else:
        _require_columns("projects", {
            "id", "scope_id", "title", "title_source", "status", "version", "message_count",
            "metadata", "idempotency_key", "create_request_hash", "created_at", "updated_at",
            "last_message_at", "deleted_at",
        })
        _require_unique("projects", {"uq_projects_scope_idempotency"})
    _ensure_index("projects", "ix_projects_scope_deleted_updated", ["scope_id", "deleted_at", "updated_at"])
    _ensure_index("projects", "ix_projects_scope_last_message", ["scope_id", "last_message_at"])

    if "project_messages" not in _inspector().get_table_names():
        op.create_table(
            "project_messages",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("scope_id", sa.String(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=True),
            sa.Column("request_hash", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "idempotency_key", name="uq_project_messages_idempotency"),
            sa.UniqueConstraint("project_id", "sequence", name="uq_project_messages_sequence"),
        )
    else:
        if "version" not in _columns("project_messages"):
            op.add_column(
                "project_messages",
                sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
            )
        _require_columns("project_messages", {
            "id", "project_id", "scope_id", "sequence", "version", "role", "content", "status",
            "metadata", "idempotency_key", "request_hash", "created_at", "updated_at",
        })
        _require_unique("project_messages", {
            "uq_project_messages_idempotency", "uq_project_messages_sequence",
        })
    _ensure_index("project_messages", "ix_project_messages_project_sequence", ["project_id", "sequence"])
    _ensure_index("project_messages", "ix_project_messages_scope_created", ["scope_id", "created_at"])

    if "project_message_mutations" not in _inspector().get_table_names():
        op.create_table(
            "project_message_mutations",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("message_id", sa.String(), nullable=False),
            sa.Column("scope_id", sa.String(), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=False),
            sa.Column("request_hash", sa.String(), nullable=False),
            sa.Column("response_payload", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["message_id"], ["project_messages.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("message_id", "idempotency_key", name="uq_message_mutations_idempotency"),
        )
    else:
        _require_columns("project_message_mutations", {
            "id", "message_id", "scope_id", "idempotency_key", "request_hash", "response_payload", "created_at",
        })
        _require_unique("project_message_mutations", {"uq_message_mutations_idempotency"})
    _ensure_index(
        "project_message_mutations",
        "ix_message_mutations_scope_created",
        ["scope_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_message_mutations_scope_created", table_name="project_message_mutations")
    op.drop_table("project_message_mutations")
    op.drop_index("ix_project_messages_scope_created", table_name="project_messages")
    op.drop_index("ix_project_messages_project_sequence", table_name="project_messages")
    op.drop_table("project_messages")
    op.drop_index("ix_projects_scope_last_message", table_name="projects")
    op.drop_index("ix_projects_scope_deleted_updated", table_name="projects")
    op.drop_table("projects")
