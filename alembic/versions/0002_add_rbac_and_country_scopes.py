"""Add RBAC and country scope models

Revision ID: 0002_add_rbac_and_country_scopes
Revises: 0001_initial_platform_schema
Create Date: 2026-09-30 01:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_add_rbac_and_country_scopes"
down_revision: Union[str, None] = "0001_initial_platform_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create roles table
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_app_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_app_id", "key", name="uq_roles_owner_app_id_key"),
    )
    op.create_index(
        op.f("ix_roles_owner_app_id"), "roles", ["owner_app_id"], unique=False
    )

    # 2. Create permissions table
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_app_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_app_id"], ["applications.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_app_id", "key", name="uq_permissions_owner_app_id_key"
        ),
    )
    op.create_index(
        op.f("ix_permissions_owner_app_id"),
        "permissions",
        ["owner_app_id"],
        unique=False,
    )

    # 3. Create role_permissions table
    op.create_table(
        "role_permissions",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["permission_id"], ["permissions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # 4. Create user_application_roles table
    op.create_table(
        "user_application_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "application_id", "role_id", name="uq_user_app_role"
        ),
    )
    op.create_index(
        op.f("ix_user_application_roles_application_id"),
        "user_application_roles",
        ["application_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_application_roles_role_id"),
        "user_application_roles",
        ["role_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_application_roles_user_id"),
        "user_application_roles",
        ["user_id"],
        unique=False,
    )

    # 5. Create user_country_scopes table
    op.create_table(
        "user_country_scopes",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("application_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("country_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["application_id"], ["applications.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["country_id"], ["countries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "application_id", "country_id"),
    )


def downgrade() -> None:
    op.drop_table("user_country_scopes")
    op.drop_index(
        op.f("ix_user_application_roles_user_id"), table_name="user_application_roles"
    )
    op.drop_index(
        op.f("ix_user_application_roles_role_id"), table_name="user_application_roles"
    )
    op.drop_index(
        op.f("ix_user_application_roles_application_id"),
        table_name="user_application_roles",
    )
    op.drop_table("user_application_roles")
    op.drop_table("role_permissions")
    op.drop_index(op.f("ix_permissions_owner_app_id"), table_name="permissions")
    op.drop_table("permissions")
    op.drop_index(op.f("ix_roles_owner_app_id"), table_name="roles")
    op.drop_table("roles")
