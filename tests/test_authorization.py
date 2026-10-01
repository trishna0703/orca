import uuid
from datetime import datetime
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authorization.service import (
    apply_entity_scope,
    get_allowed_country_ids,
    has_permission,
)
from app.db.session import SessionLocal
from app.models.application import Application
from app.models.case import Case, CaseStatus
from app.models.country import Country
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user import User
from app.models.user_application_role import UserApplicationRole
from app.models.user_country_scope import UserCountryScope
from scripts.seed import seed_data


@pytest.fixture(scope="module")
def db_session():
    session = SessionLocal()
    seed_data(session)
    try:
        yield session
    finally:
        session.close()


def test_permission_resolution(db_session: Session):
    """
    Alice: case-manager -> has case:create, case:read, case:delete
    Bob: case-worker -> has case:create, case:read, but NOT case:delete
    Carol: viewer -> has case:read, but NOT case:create or case:delete
    """
    app = db_session.execute(
        select(Application).where(Application.key == "care-companion")
    ).scalar_one()
    alice = db_session.execute(
        select(User).where(User.display_name == "Alice")
    ).scalar_one()
    bob = db_session.execute(
        select(User).where(User.display_name == "Bob")
    ).scalar_one()
    carol = db_session.execute(
        select(User).where(User.display_name == "Carol")
    ).scalar_one()

    # Alice checks
    assert (
        has_permission(
            db_session,
            user_id=alice.id,
            application_id=app.id,
            permission_key="case:create",
        )
        is True
    )
    assert (
        has_permission(
            db_session,
            user_id=alice.id,
            application_id=app.id,
            permission_key="case:read",
        )
        is True
    )
    assert (
        has_permission(
            db_session,
            user_id=alice.id,
            application_id=app.id,
            permission_key="case:delete",
        )
        is True
    )

    # Bob checks
    assert (
        has_permission(
            db_session,
            user_id=bob.id,
            application_id=app.id,
            permission_key="case:create",
        )
        is True
    )
    assert (
        has_permission(
            db_session,
            user_id=bob.id,
            application_id=app.id,
            permission_key="case:read",
        )
        is True
    )
    assert (
        has_permission(
            db_session,
            user_id=bob.id,
            application_id=app.id,
            permission_key="case:delete",
        )
        is False
    )

    # Carol checks
    assert (
        has_permission(
            db_session,
            user_id=carol.id,
            application_id=app.id,
            permission_key="case:read",
        )
        is True
    )
    assert (
        has_permission(
            db_session,
            user_id=carol.id,
            application_id=app.id,
            permission_key="case:create",
        )
        is False
    )
    assert (
        has_permission(
            db_session,
            user_id=carol.id,
            application_id=app.id,
            permission_key="case:delete",
        )
        is False
    )


def test_country_scope_resolution(db_session: Session):
    """
    Alice -> Arnova, Belmara
    Bob -> Calduria
    Carol -> Belmara
    """
    app = db_session.execute(
        select(Application).where(Application.key == "care-companion")
    ).scalar_one()
    alice = db_session.execute(
        select(User).where(User.display_name == "Alice")
    ).scalar_one()
    bob = db_session.execute(
        select(User).where(User.display_name == "Bob")
    ).scalar_one()
    carol = db_session.execute(
        select(User).where(User.display_name == "Carol")
    ).scalar_one()

    arnova = db_session.execute(
        select(Country).where(Country.code == "ARN")
    ).scalar_one()
    belmara = db_session.execute(
        select(Country).where(Country.code == "BEL")
    ).scalar_one()
    calduria = db_session.execute(
        select(Country).where(Country.code == "CAL")
    ).scalar_one()

    alice_scopes = get_allowed_country_ids(
        db_session, user_id=alice.id, application_id=app.id
    )
    bob_scopes = get_allowed_country_ids(
        db_session, user_id=bob.id, application_id=app.id
    )
    carol_scopes = get_allowed_country_ids(
        db_session, user_id=carol.id, application_id=app.id
    )

    assert alice_scopes == {arnova.id, belmara.id}
    assert bob_scopes == {calduria.id}
    assert carol_scopes == {belmara.id}


def test_apply_entity_scope_sql_construction(db_session: Session):
    """
    Verify apply_entity_scope constructs proper SQL where clauses for country, app, and soft delete.
    """
    app_id = uuid.uuid4()
    c1 = uuid.uuid4()
    c2 = uuid.uuid4()

    stmt = select(Case)
    scoped_stmt = apply_entity_scope(
        stmt,
        entity_cls=Case,
        application_id=app_id,
        allowed_country_ids={c1, c2},
        include_deleted=False,
    )

    sql_str = str(scoped_stmt.compile(compile_kwargs={"literal_binds": False}))
    assert (
        "cases.owner_app_id = :owner_app_id" in sql_str
        or "cases.owner_app_id =" in sql_str
    )
    assert "cases.country_id IN" in sql_str
    assert "cases.deleted_at IS NULL" in sql_str


def test_soft_delete_query_exclusion(db_session: Session):
    """
    Verify that soft-deleted cases are excluded by apply_entity_scope.
    """
    app = db_session.execute(
        select(Application).where(Application.key == "care-companion")
    ).scalar_one()
    arnova = db_session.execute(
        select(Country).where(Country.code == "ARN")
    ).scalar_one()
    alice = db_session.execute(
        select(User).where(User.display_name == "Alice")
    ).scalar_one()

    # Create active case and soft-deleted case in Arnova
    active_case = Case(
        title="Active Case",
        country_id=arnova.id,
        owner_app_id=app.id,
        created_by=alice.id,
    )
    deleted_case = Case(
        title="Deleted Case",
        country_id=arnova.id,
        owner_app_id=app.id,
        created_by=alice.id,
        deleted_at=datetime.now(),
        deleted_by=alice.id,
    )
    db_session.add_all([active_case, deleted_case])
    db_session.commit()

    # Query with apply_entity_scope
    stmt = select(Case).where(Case.id.in_([active_case.id, deleted_case.id]))
    scoped_stmt = apply_entity_scope(
        stmt,
        entity_cls=Case,
        application_id=app.id,
        allowed_country_ids={arnova.id},
        include_deleted=False,
    )
    results = db_session.execute(scoped_stmt).scalars().all()
    result_ids = {r.id for r in results}

    assert active_case.id in result_ids
    assert deleted_case.id not in result_ids
