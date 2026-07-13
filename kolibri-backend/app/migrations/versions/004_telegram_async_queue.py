"""Add durable Telegram ingress/outbound queue and bot identity evidence.

Revision ID: 004_telegram_async_queue
Revises: 003_telegram_delivery_evidence
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "004_telegram_async_queue"
down_revision: Union[str, None] = "003_telegram_delivery_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_UPDATE_COLUMNS = {
    "id",
    "update_id",
    "chat_id",
    "message_id",
    "payload_hash",
    "payload",
    "state",
    "attempts",
    "lease_owner",
    "lease_until",
    "project_id",
    "assistant_message_id",
    "response_id",
    "acknowledgement_message_id",
    "result_message_id",
    "outbound_state",
    "delivery_method",
    "last_error_code",
    "created_at",
    "updated_at",
    "completed_at",
}
_IDENTITY_COLUMNS = {
    "id",
    "bot_id",
    "username",
    "verified",
    "verified_at",
    "updated_at",
}
_PUBLIC_API_KEY_COLUMNS = {
    "id",
    "owner_scope",
    "name",
    "key_prefix",
    "secret_hash",
    "created_at",
    "last_used_at",
    "revoked_at",
}


def _inspector():
    return sa.inspect(op.get_bind())


def _ensure_index(table: str, name: str, columns: list[str]) -> None:
    if name not in {index["name"] for index in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    if "telegram_updates" not in _inspector().get_table_names():
        op.create_table(
            "telegram_updates",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("update_id", sa.Integer(), nullable=False),
            sa.Column("chat_id", sa.String(), nullable=False),
            sa.Column("message_id", sa.Integer(), nullable=False),
            sa.Column("payload_hash", sa.String(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("state", sa.String(), nullable=False),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("lease_owner", sa.String(), nullable=True),
            sa.Column("lease_until", sa.DateTime(), nullable=True),
            sa.Column("project_id", sa.String(), nullable=True),
            sa.Column("assistant_message_id", sa.String(), nullable=True),
            sa.Column("response_id", sa.String(), nullable=True),
            sa.Column("acknowledgement_message_id", sa.Integer(), nullable=True),
            sa.Column("result_message_id", sa.Integer(), nullable=True),
            sa.Column("outbound_state", sa.String(), nullable=False),
            sa.Column("delivery_method", sa.String(), nullable=True),
            sa.Column("last_error_code", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("update_id", name="uq_telegram_updates_update_id"),
        )
    else:
        columns = {column["name"] for column in _inspector().get_columns("telegram_updates")}
        missing = sorted(_UPDATE_COLUMNS - columns)
        if missing:
            raise RuntimeError(
                "existing telegram_updates table is incompatible; "
                f"missing columns: {', '.join(missing)}"
            )
        unique_columns = {
            tuple(constraint.get("column_names") or [])
            for constraint in _inspector().get_unique_constraints("telegram_updates")
        }
        if ("update_id",) not in unique_columns:
            raise RuntimeError("telegram_updates is missing its update_id uniqueness contract")
    _ensure_index(
        "telegram_updates",
        "ix_telegram_updates_state_lease",
        ["state", "lease_until", "created_at"],
    )
    _ensure_index(
        "telegram_updates",
        "ix_telegram_updates_chat_created",
        ["chat_id", "created_at"],
    )

    if "telegram_bot_identity" not in _inspector().get_table_names():
        op.create_table(
            "telegram_bot_identity",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("bot_id", sa.String(), nullable=True),
            sa.Column("username", sa.String(), nullable=True),
            sa.Column("verified", sa.Boolean(), nullable=False),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    else:
        columns = {
            column["name"]
            for column in _inspector().get_columns("telegram_bot_identity")
        }
        missing = sorted(_IDENTITY_COLUMNS - columns)
        if missing:
            raise RuntimeError(
                "existing telegram_bot_identity table is incompatible; "
                f"missing columns: {', '.join(missing)}"
            )

    if "public_api_keys" not in _inspector().get_table_names():
        op.create_table(
            "public_api_keys",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("owner_scope", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("key_prefix", sa.String(), nullable=False),
            sa.Column("secret_hash", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("last_used_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("secret_hash", name="uq_public_api_keys_secret_hash"),
        )
    else:
        columns = {
            column["name"]
            for column in _inspector().get_columns("public_api_keys")
        }
        missing = sorted(_PUBLIC_API_KEY_COLUMNS - columns)
        if missing:
            raise RuntimeError(
                "existing public_api_keys table is incompatible; "
                f"missing columns: {', '.join(missing)}"
            )
        unique_columns = {
            tuple(constraint.get("column_names") or [])
            for constraint in _inspector().get_unique_constraints("public_api_keys")
        }
        if ("secret_hash",) not in unique_columns:
            raise RuntimeError("public_api_keys is missing its secret_hash uniqueness contract")
    _ensure_index(
        "public_api_keys",
        "ix_public_api_keys_owner_revoked",
        ["owner_scope", "revoked_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_public_api_keys_owner_revoked", table_name="public_api_keys")
    op.drop_table("public_api_keys")
    op.drop_table("telegram_bot_identity")
    op.drop_index("ix_telegram_updates_chat_created", table_name="telegram_updates")
    op.drop_index("ix_telegram_updates_state_lease", table_name="telegram_updates")
    op.drop_table("telegram_updates")
