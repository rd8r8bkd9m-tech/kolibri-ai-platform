"""Add organization tenancy and preserve every existing personal scope.

Revision ID: 011_organization_tenancy
Revises: 010_durable_responses
Create Date: 2026-07-16

The migration is deliberately additive.  Existing ``user:<id>`` ownership is
not rewritten: it becomes the immutable ``data_scope_id`` of that user's
personal organization.  Anonymous, Telegram, demo, legacy and older public API
key scopes remain unassigned until an explicit audited adoption.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op


revision: str = "011_organization_tenancy"
down_revision: Union[str, None] = "010_durable_responses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PERSONAL_ORGANIZATION_NAMESPACE = uuid.UUID("5f19d5ea-4b88-4a17-9a7c-7bfdf11c3a49")
PERSONAL_MEMBERSHIP_NAMESPACE = uuid.UUID("c47a242e-807d-4e87-b030-f9266175ed42")
PERSONAL_AUDIT_NAMESPACE = uuid.UUID("518c3433-2331-4453-8226-184db69e5a7e")


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


def _ensure_organization_column(table: str, index_name: str, index_columns: list[str]) -> None:
    if "organization_id" not in _columns(table):
        _add_nullable_organization_reference(table, "organization_id")
    _ensure_index(table, index_name, index_columns)


def _add_nullable_organization_reference(table: str, column: str) -> None:
    """Add a nullable FK without SQLite's unsupported ALTER CONSTRAINT path."""

    if op.get_bind().dialect.name == "sqlite":
        # The names are migration constants, never request input.  SQLite can
        # add a nullable REFERENCES column directly even though Alembic's
        # generic add_column implementation tries a second ALTER CONSTRAINT.
        op.execute(
            sa.text(
                f'ALTER TABLE "{table}" ADD COLUMN "{column}" VARCHAR '
                "REFERENCES organizations(id) ON DELETE SET NULL"
            )
        )
        return
    op.add_column(
        table,
        sa.Column(
            column,
            sa.String(),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def _personal_id(namespace: uuid.UUID, user_id: str) -> str:
    return str(uuid.uuid5(namespace, user_id))


def _create_organization_tables() -> None:
    if "organizations" not in _tables():
        op.create_table(
            "organizations",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("data_scope_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("slug", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("settings", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "data_scope_id",
                name="uq_organizations_data_scope_id",
            ),
            sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        )
    _ensure_index("organizations", "ix_organizations_status", ["status"])

    if "users" not in _tables():
        op.create_table(
            "users",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=True, server_default="user"),
            sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.true()),
            sa.Column(
                "default_organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("email", name="uq_users_email"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    elif "default_organization_id" not in _columns("users"):
        _add_nullable_organization_reference("users", "default_organization_id")

    if "organization_memberships" not in _tables():
        op.create_table(
            "organization_memberships",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(), nullable=False, server_default="member"),
            sa.Column("status", sa.String(), nullable=False, server_default="active"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint(
                "organization_id",
                "user_id",
                name="uq_organization_memberships_org_user",
            ),
        )
    _ensure_index(
        "organization_memberships",
        "ix_organization_memberships_user_status",
        ["user_id", "status"],
    )
    _ensure_index(
        "organization_memberships",
        "ix_organization_memberships_org_status",
        ["organization_id", "status"],
    )

    if "organization_audit_events" not in _tables():
        op.create_table(
            "organization_audit_events",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "organization_id",
                sa.String(),
                sa.ForeignKey("organizations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "actor_user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("target_type", sa.String(), nullable=True),
            sa.Column("target_id", sa.String(), nullable=True),
            sa.Column("request_id", sa.String(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    _ensure_index(
        "organization_audit_events",
        "ix_organization_audit_events_org_created",
        ["organization_id", "created_at"],
    )
    _ensure_index(
        "organization_audit_events",
        "ix_organization_audit_events_actor",
        ["actor_user_id"],
    )


def _backfill_personal_organizations() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    users = sa.Table("users", metadata, autoload_with=connection)
    organizations = sa.Table("organizations", metadata, autoload_with=connection)
    memberships = sa.Table("organization_memberships", metadata, autoload_with=connection)
    audit_events = sa.Table("organization_audit_events", metadata, autoload_with=connection)
    roots = (
        (sa.Table("projects", metadata, autoload_with=connection), "scope_id"),
        (sa.Table("estimates", metadata, autoload_with=connection), "scope_id"),
        (sa.Table("documents", metadata, autoload_with=connection), "scope_id"),
        (sa.Table("public_responses", metadata, autoload_with=connection), "owner_scope"),
        (sa.Table("public_api_keys", metadata, autoload_with=connection), "owner_scope"),
    )
    now = datetime.now(timezone.utc)

    for user in connection.execute(
        sa.select(users.c.id, users.c.name, users.c.default_organization_id)
    ).mappings():
        user_id = str(user["id"])
        data_scope_id = f"user:{user_id}"
        organization_id = connection.execute(
            sa.select(organizations.c.id).where(
                organizations.c.data_scope_id == data_scope_id
            )
        ).scalar_one_or_none()
        created = organization_id is None
        if organization_id is None:
            organization_id = _personal_id(PERSONAL_ORGANIZATION_NAMESPACE, user_id)
            connection.execute(
                organizations.insert().values(
                    id=organization_id,
                    data_scope_id=data_scope_id,
                    name=f"{str(user['name']).strip()} — личная организация",
                    slug=f"personal-{organization_id}",
                    status="active",
                    settings={},
                    created_at=now,
                    updated_at=now,
                )
            )

        membership_exists = connection.execute(
            sa.select(memberships.c.id).where(
                memberships.c.organization_id == organization_id,
                memberships.c.user_id == user_id,
            )
        ).scalar_one_or_none()
        if membership_exists is None:
            connection.execute(
                memberships.insert().values(
                    id=_personal_id(PERSONAL_MEMBERSHIP_NAMESPACE, user_id),
                    organization_id=organization_id,
                    user_id=user_id,
                    role="owner",
                    status="active",
                    created_at=now,
                    updated_at=now,
                )
            )

        if user["default_organization_id"] is None:
            connection.execute(
                users.update()
                .where(users.c.id == user_id)
                .values(default_organization_id=organization_id)
            )

        for root, scope_column in roots:
            connection.execute(
                root.update()
                .where(
                    root.c.organization_id.is_(None),
                    root.c[scope_column] == data_scope_id,
                )
                .values(organization_id=organization_id)
            )

        if created:
            connection.execute(
                audit_events.insert().values(
                    id=_personal_id(PERSONAL_AUDIT_NAMESPACE, user_id),
                    organization_id=organization_id,
                    actor_user_id=user_id,
                    action="organization.personal_backfilled",
                    target_type="organization",
                    target_id=organization_id,
                    request_id=None,
                    metadata={"data_scope_id": data_scope_id},
                    created_at=now,
                )
            )


def upgrade() -> None:
    _create_organization_tables()
    _ensure_organization_column(
        "projects",
        "ix_projects_organization_updated",
        ["organization_id", "updated_at"],
    )
    _ensure_organization_column(
        "estimates",
        "ix_estimates_organization_created",
        ["organization_id", "created_at"],
    )
    _ensure_organization_column(
        "documents",
        "ix_documents_organization_created",
        ["organization_id", "created_at"],
    )
    _ensure_organization_column(
        "public_responses",
        "ix_public_responses_organization_updated",
        ["organization_id", "updated_at"],
    )
    _ensure_organization_column(
        "public_api_keys",
        "ix_public_api_keys_organization_revoked",
        ["organization_id", "revoked_at", "created_at"],
    )
    _backfill_personal_organizations()


def downgrade() -> None:
    for table, index_name in (
        ("public_api_keys", "ix_public_api_keys_organization_revoked"),
        ("public_responses", "ix_public_responses_organization_updated"),
        ("documents", "ix_documents_organization_created"),
        ("estimates", "ix_estimates_organization_created"),
        ("projects", "ix_projects_organization_updated"),
    ):
        if index_name in _index_names(table):
            op.drop_index(index_name, table_name=table)
        if "organization_id" in _columns(table):
            op.drop_column(table, "organization_id")

    if "organization_audit_events" in _tables():
        op.drop_table("organization_audit_events")
    if "organization_memberships" in _tables():
        op.drop_table("organization_memberships")
    if "default_organization_id" in _columns("users"):
        op.drop_column("users", "default_organization_id")
    if "organizations" in _tables():
        op.drop_table("organizations")
