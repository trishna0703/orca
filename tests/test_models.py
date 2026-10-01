import inspect
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase

from app.db.base import Base
from app.models.application import Application
from app.models.base_entity import BaseEntity
from app.models.case import Case, CaseStatus
from app.models.country import Country
from app.models.user import User


def test_base_entity_is_abstract() -> None:
    """Verify BaseEntity is abstract and does not create a base_entities table."""
    assert BaseEntity.__abstract__ is True
    assert "base_entities" not in Base.metadata.tables


def test_registered_metadata_tables() -> None:
    """Verify exactly expected tables are registered in Base.metadata."""
    expected_tables = {
        "applications",
        "countries",
        "users",
        "cases",
        "roles",
        "permissions",
        "role_permissions",
        "user_application_roles",
        "user_country_scopes",
        "audit_logs",
        "outbox_events",
        "command_view_case_metrics",
        "processed_events",
        "partners",
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert registered_tables == expected_tables


def test_case_inherits_base_entity_columns() -> None:
    """Verify cases table contains all BaseEntity columns and Case domain columns."""
    case_table = Base.metadata.tables["cases"]
    column_names = {col.name for col in case_table.columns}

    # BaseEntity platform columns
    expected_base_columns = {
        "id",
        "country_id",
        "owner_app_id",
        "created_at",
        "created_by",
        "updated_at",
        "updated_by",
        "deleted_at",
        "deleted_by",
        "version",
    }

    # Case domain columns
    expected_case_columns = {
        "title",
        "description",
        "status",
    }

    assert expected_base_columns.issubset(column_names)
    assert expected_case_columns.issubset(column_names)


def test_case_status_enum_values() -> None:
    """Verify CaseStatus enum values match required persisted strings."""
    assert CaseStatus.OPEN.value == "open"
    assert CaseStatus.IN_PROGRESS.value == "in_progress"
    assert CaseStatus.CLOSED.value == "closed"


def test_country_model_columns() -> None:
    """Verify countries table structure."""
    country_table = Base.metadata.tables["countries"]
    column_names = {col.name for col in country_table.columns}
    assert {"id", "code", "name"}.issubset(column_names)


def test_application_model_columns() -> None:
    """Verify applications table structure."""
    app_table = Base.metadata.tables["applications"]
    column_names = {col.name for col in app_table.columns}
    assert {"id", "key", "name", "created_at"}.issubset(column_names)


def test_user_model_columns() -> None:
    """Verify user table is minimal (no role_id or country_id)."""
    user_table = Base.metadata.tables["users"]
    column_names = {col.name for col in user_table.columns}
    assert {"id", "email", "display_name", "created_at"} == column_names
    assert "role_id" not in column_names
    assert "country_id" not in column_names
