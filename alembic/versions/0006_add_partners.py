"""Add partners table

Revision ID: 0006_add_partners
Revises: 0005_command_view
Create Date: 2026-09-30 05:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006_add_partners"
down_revision: Union[str, None] = "0005_command_view"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    partner_status_enum = postgresql.ENUM(
        "active", "inactive", name="partner_status", create_type=False
    )
    partner_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "partners",
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
        # Partner columns
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("partner_type", sa.String(length=100), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "active", "inactive", name="partner_status", create_type=False
            ),
            nullable=False,
            server_default="active",
        ),
        # Foreign keys
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"]),
        sa.ForeignKeyConstraint(["owner_app_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["deleted_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_partners_country_id"), "partners", ["country_id"], unique=False
    )
    op.create_index(
        op.f("ix_partners_owner_app_id"), "partners", ["owner_app_id"], unique=False
    )
    op.create_index(
        op.f("ix_partners_deleted_at"), "partners", ["deleted_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_partners_deleted_at"), table_name="partners")
    op.drop_index(op.f("ix_partners_owner_app_id"), table_name="partners")
    op.drop_index(op.f("ix_partners_country_id"), table_name="partners")
    op.drop_table("partners")

    sa.Enum("active", "inactive", name="partner_status").drop(
        op.get_bind(), checkfirst=True
    )
