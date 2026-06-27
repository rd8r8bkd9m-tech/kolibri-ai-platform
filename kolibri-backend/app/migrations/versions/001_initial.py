"""Initial schema — all Kolibri tables.

Revision ID: 001_initial
Revises: None
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "estimates",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("version", sa.Integer, server_default="1"),
        sa.Column("status", sa.String, server_default="draft"),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("client", sa.String, server_default=""),
        sa.Column("object_name", sa.String, server_default=""),
        sa.Column("region", sa.String, server_default=""),
        sa.Column("currency", sa.String, server_default="RUB"),
        sa.Column("overhead_rate", sa.String, server_default="0"),
        sa.Column("vat_rate", sa.String, server_default="20"),
        sa.Column("subtotal", sa.String, server_default="0"),
        sa.Column("overhead_amount", sa.String, server_default="0"),
        sa.Column("vat_amount", sa.String, server_default="0"),
        sa.Column("total", sa.String, server_default="0"),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )

    op.create_table(
        "sections",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("estimate_id", sa.String, sa.ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("subtotal", sa.String, server_default="0"),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("section_id", sa.String, sa.ForeignKey("sections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String, server_default=""),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("unit", sa.String, server_default="шт"),
        sa.Column("quantity", sa.String, server_default="0"),
        sa.Column("price", sa.String, server_default="0"),
        sa.Column("sum", sa.String, server_default="0"),
        sa.Column("source", sa.String, server_default=""),
        sa.Column("comment", sa.Text, server_default=""),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("title", sa.String, nullable=False),
        sa.Column("type", sa.String, server_default="custom"),
        sa.Column("status", sa.String, server_default="draft"),
        sa.Column("client", sa.String, server_default=""),
        sa.Column("project", sa.String, server_default=""),
        sa.Column("content", sa.Text, server_default=""),
        sa.Column("variables", sa.JSON, server_default="{}"),
        sa.Column("template", sa.Text, server_default=""),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )

    op.create_table(
        "agents",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("role", sa.String, server_default=""),
        sa.Column("status", sa.String, server_default="idle"),
        sa.Column("node_id", sa.String, nullable=True),
        sa.Column("current_task", sa.String, nullable=True),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("model", sa.String, nullable=True),
        sa.Column("capabilities", sa.JSON, server_default="{}"),
        sa.Column("cost_accumulated", sa.String, server_default="0"),
        sa.Column("heartbeat_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "nodes",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("region", sa.String, server_default=""),
        sa.Column("ip_address", sa.String, server_default=""),
        sa.Column("status", sa.String, server_default="healthy"),
        sa.Column("cpu_percent", sa.String, server_default="0"),
        sa.Column("ram_percent", sa.String, server_default="0"),
        sa.Column("disk_percent", sa.String, server_default="0"),
        sa.Column("network_mbps", sa.String, server_default="0"),
        sa.Column("agent_count", sa.Integer, server_default="0"),
        sa.Column("task_count", sa.Integer, server_default="0"),
        sa.Column("ping_ms", sa.Integer, server_default="0"),
        sa.Column("max_agents", sa.Integer, server_default="50"),
        sa.Column("capabilities", sa.JSON, server_default="{}"),
    )

    op.create_table(
        "tasks",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("workflow_id", sa.String, server_default=""),
        sa.Column("state", sa.String, server_default="queued"),
        sa.Column("priority", sa.Integer, server_default="1"),
        sa.Column("owner_agent_id", sa.String, nullable=True),
        sa.Column("node_id", sa.String, nullable=True),
        sa.Column("budget_limit", sa.String, nullable=True),
        sa.Column("attempts", sa.Integer, server_default="0"),
        sa.Column("max_retries", sa.Integer, server_default="3"),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime),
        sa.Column("updated_at", sa.DateTime),
    )


def downgrade() -> None:
    op.drop_table("tasks")
    op.drop_table("nodes")
    op.drop_table("agents")
    op.drop_table("documents")
    op.drop_table("positions")
    op.drop_table("sections")
    op.drop_table("estimates")
