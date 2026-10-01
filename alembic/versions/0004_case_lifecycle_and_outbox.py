"""Add Case lifecycle columns and outbox_events table

Revision ID: 0004_case_lifecycle_and_outbox
Revises: 0003_add_audit_logs
Create Date: 2026-09-30 03:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004_case_lifecycle_and_outbox"
down_revision: Union[str, None] = "0003_add_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add assigned_to, closed_at, closed_by to cases
    op.add_column(
        "cases", sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "cases", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "cases", sa.Column("closed_by", postgresql.UUID(as_uuid=True), nullable=True)
    )

    op.create_foreign_key(
        "fk_cases_assigned_to_users", "cases", "users", ["assigned_to"], ["id"]
    )
    op.create_foreign_key(
        "fk_cases_closed_by_users", "cases", "users", ["closed_by"], ["id"]
    )
    op.create_index(
        op.f("ix_cases_assigned_to"), "cases", ["assigned_to"], unique=False
    )

    # 2. Create outbox_events table
    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=150), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("country_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=50), server_default="pending", nullable=False
        ),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_outbox_events_application_id"),
        "outbox_events",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_country_id"),
        "outbox_events",
        ["country_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_created_at"),
        "outbox_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_event_type"),
        "outbox_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_request_id"),
        "outbox_events",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbox_events_status"), "outbox_events", ["status"], unique=False
    )
    op.create_index(
        "ix_outbox_events_aggregate",
        "outbox_events",
        ["aggregate_type", "aggregate_id"],
        unique=False,
    )
    op.create_index(
        "ix_outbox_events_status_created",
        "outbox_events",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_events_status_created", table_name="outbox_events")
    op.drop_index("ix_outbox_events_aggregate", table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_status"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_request_id"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_event_type"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_created_at"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_country_id"), table_name="outbox_events")
    op.drop_index(op.f("ix_outbox_events_application_id"), table_name="outbox_events")
    op.drop_table("outbox_events")

    op.drop_index(op.f("ix_cases_assigned_to"), table_name="cases")
    op.drop_constraint("fk_cases_closed_by_users", "cases", type_="foreignkey")
    op.drop_constraint("fk_cases_assigned_to_users", "cases", type_="foreignkey")
    op.drop_column("cases", "closed_by")
    op.drop_column("cases", "closed_at")
    op.drop_column("cases", "assigned_to")
