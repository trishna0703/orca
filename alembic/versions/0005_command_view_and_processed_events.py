"""Add command_view_case_metrics and processed_events tables

Revision ID: 0005_command_view_and_processed_events
Revises: 0004_case_lifecycle_and_outbox
Create Date: 2026-09-30 04:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005_command_view"
down_revision: Union[str, None] = "0004_case_lifecycle_and_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create command_view_case_metrics table
    op.create_table(
        "command_view_case_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("country_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "in_progress_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("closed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "open_count >= 0", name="ck_metrics_open_count_non_negative"
        ),
        sa.CheckConstraint(
            "in_progress_count >= 0", name="ck_metrics_in_progress_count_non_negative"
        ),
        sa.CheckConstraint(
            "closed_count >= 0", name="ck_metrics_closed_count_non_negative"
        ),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("country_id", name="uq_metrics_country_id"),
    )
    op.create_index(
        op.f("ix_command_view_case_metrics_country_id"),
        "command_view_case_metrics",
        ["country_id"],
        unique=True,
    )

    # 2. Create processed_events table
    op.create_table(
        "processed_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer", sa.String(length=150), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("event_id", "consumer"),
    )


def downgrade() -> None:
    op.drop_table("processed_events")
    op.drop_index(
        op.f("ix_command_view_case_metrics_country_id"),
        table_name="command_view_case_metrics",
    )
    op.drop_table("command_view_case_metrics")
