"""Add project-scoped grants and one-use cross-surface handoffs.

Revision ID: 006_project_handoffs
Revises: 005_estimate_revisions
Create Date: 2026-07-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "006_project_handoffs"
down_revision: Union[str, None] = "005_estimate_revisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ACCESS_NULLABLE = {
    "id": False,
    "project_id": False,
    "scope_id": False,
    "permission": False,
    "source": False,
    "created_at": False,
    "revoked_at": True,
}
_HANDOFF_NULLABLE = {
    "id": False,
    "project_id": False,
    "source_scope_id": False,
    "token_hash": False,
    "idempotency_key": False,
    "expires_at": False,
    "claimed_by_scope_id": True,
    "claimed_at": True,
    "created_at": False,
}


def _inspector():
    return sa.inspect(op.get_bind())


def _ensure_index(table: str, name: str, columns: list[str]) -> None:
    if name not in {index["name"] for index in _inspector().get_indexes(table)}:
        op.create_index(name, table, columns)


def _unique_columns(table: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint.get("column_names") or [])
        for constraint in _inspector().get_unique_constraints(table)
    }


def _contract_issues(
    table: str,
    *,
    nullable: dict[str, bool],
    unique: set[tuple[str, ...]],
) -> list[str]:
    inspector = _inspector()
    columns = {column["name"]: column for column in inspector.get_columns(table)}
    issues: list[str] = []
    missing = sorted(set(nullable) - set(columns))
    if missing:
        issues.append(f"missing columns: {', '.join(missing)}")

    nullable_mismatches = sorted(
        name
        for name, expected in nullable.items()
        if name in columns and bool(columns[name].get("nullable")) is not expected
    )
    if nullable_mismatches:
        issues.append(f"nullable mismatch: {', '.join(nullable_mismatches)}")

    primary_key = tuple(
        inspector.get_pk_constraint(table).get("constrained_columns") or []
    )
    if primary_key != ("id",):
        issues.append("primary key must be (id)")

    missing_unique = sorted(unique - _unique_columns(table))
    if missing_unique:
        issues.append(
            "missing unique constraints: "
            + ", ".join(
                "(" + ", ".join(column_names) + ")"
                for column_names in missing_unique
            )
        )

    project_foreign_key = any(
        tuple(foreign_key.get("constrained_columns") or []) == ("project_id",)
        and foreign_key.get("referred_table") == "projects"
        and tuple(foreign_key.get("referred_columns") or []) == ("id",)
        and str((foreign_key.get("options") or {}).get("ondelete") or "").upper()
        == "CASCADE"
        for foreign_key in inspector.get_foreign_keys(table)
    )
    if not project_foreign_key:
        issues.append("project_id foreign key must reference projects.id ON DELETE CASCADE")
    return issues


def _require_contract(
    table: str,
    *,
    nullable: dict[str, bool],
    unique: set[tuple[str, ...]],
) -> None:
    issues = _contract_issues(table, nullable=nullable, unique=unique)
    if issues:
        raise RuntimeError(
            f"existing {table} table is incompatible; {'; '.join(issues)}"
        )


def upgrade() -> None:
    if "project_access" not in _inspector().get_table_names():
        op.create_table(
            "project_access",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("scope_id", sa.String(), nullable=False),
            sa.Column("permission", sa.String(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "scope_id", name="uq_project_access_scope"),
        )
    else:
        columns = {column["name"] for column in _inspector().get_columns("project_access")}
        if "revoked_at" not in columns:
            legacy_nullable = dict(_ACCESS_NULLABLE)
            legacy_nullable.pop("revoked_at")
            _require_contract(
                "project_access",
                nullable=legacy_nullable,
                unique={("project_id", "scope_id")},
            )
            op.add_column("project_access", sa.Column("revoked_at", sa.DateTime(), nullable=True))
        _require_contract(
            "project_access",
            nullable=_ACCESS_NULLABLE,
            unique={("project_id", "scope_id")},
        )
    _ensure_index(
        "project_access",
        "ix_project_access_scope_project",
        ["scope_id", "project_id"],
    )

    if "project_handoffs" not in _inspector().get_table_names():
        op.create_table(
            "project_handoffs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("project_id", sa.String(), nullable=False),
            sa.Column("source_scope_id", sa.String(), nullable=False),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("claimed_by_scope_id", sa.String(), nullable=True),
            sa.Column("claimed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash", name="uq_project_handoffs_token_hash"),
            sa.UniqueConstraint("idempotency_key", name="uq_project_handoffs_idempotency"),
        )
    else:
        _require_contract(
            "project_handoffs",
            nullable=_HANDOFF_NULLABLE,
            unique={("token_hash",), ("idempotency_key",)},
        )
    _ensure_index(
        "project_handoffs",
        "ix_project_handoffs_project_expiry",
        ["project_id", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_project_handoffs_project_expiry", table_name="project_handoffs")
    op.drop_table("project_handoffs")
    op.drop_index("ix_project_access_scope_project", table_name="project_access")
    op.drop_table("project_access")
