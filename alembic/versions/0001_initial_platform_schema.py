"""Initial platform and domain tables

Revision ID: 0001_initial_platform_schema
Revises:
Create Date: 2026-09-30 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_platform_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create applications table
    op.create_table(
        "applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_applications_key"), "applications", ["key"], unique=True)

    # 2. Create countries table
    op.create_table(
        "countries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_countries_code"), "countries", ["code"], unique=True)

    # 3. Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # 4. Create case_status enum
    case_status_enum = postgresql.ENUM(
        "open", "in_progress", "closed", name="case_status", create_type=False
    )
    case_status_enum.create(op.get_bind(), checkfirst=True)

    # 5. Create cases table (inherits BaseEntity columns + domain columns)
    op.create_table(
        "cases",
        # BaseEntity columns
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("country_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        # Case domain columns
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "open", "in_progress", "closed", name="case_status", create_type=False
            ),
            nullable=False,
        ),
        # Foreign key constraints
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.ForeignKeyConstraint(["owner_app_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["deleted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cases_country_id"), "cases", ["country_id"], unique=False)
    op.create_index(
        op.f("ix_cases_owner_app_id"), "cases", ["owner_app_id"], unique=False
    )
    op.create_index(op.f("ix_cases_deleted_at"), "cases", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_cases_deleted_at"), table_name="cases")
    op.drop_index(op.f("ix_cases_owner_app_id"), table_name="cases")
    op.drop_index(op.f("ix_cases_country_id"), table_name="cases")
    op.drop_table("cases")

    sa.Enum("open", "in_progress", "closed", name="case_status").drop(
        op.get_bind(), checkfirst=True
    )

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_countries_code"), table_name="countries")
    op.drop_table("countries")

    op.drop_index(op.f("ix_applications_key"), table_name="applications")
    op.drop_table("applications")
