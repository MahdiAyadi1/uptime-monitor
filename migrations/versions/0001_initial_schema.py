"""Create the initial uptime monitor schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create monitors, probe results, and incidents."""
    op.create_table(
        "monitor",
        sa.Column("id", sa.Integer(), sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("expected_status", sa.Integer(), server_default=sa.text("200"), nullable=False),
        sa.Column("expected_keyword", sa.Text(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), server_default=sa.text("300"), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "probe_result",
        sa.Column("id", sa.Integer(), sa.Identity(always=True), primary_key=True),
        sa.Column("monitor_id", sa.Integer(), nullable=False),
        sa.Column(
            "probed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("is_up", sa.Boolean(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("tls_days_remaining", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitor.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_probe_result_monitor_time",
        "probe_result",
        ["monitor_id", sa.text("probed_at DESC")],
    )
    op.create_table(
        "incident",
        sa.Column("id", sa.Integer(), sa.Identity(always=True), primary_key=True),
        sa.Column("monitor_id", sa.Integer(), nullable=False),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["monitor_id"], ["monitor.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ux_incident_one_open_per_monitor",
        "incident",
        ["monitor_id"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade() -> None:
    """Drop the initial uptime monitor schema."""
    op.drop_index("ux_incident_one_open_per_monitor", table_name="incident")
    op.drop_table("incident")
    op.drop_index("ix_probe_result_monitor_time", table_name="probe_result")
    op.drop_table("probe_result")
    op.drop_table("monitor")
