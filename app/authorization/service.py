import uuid
from typing import Sequence, TypeVar
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.base_entity import BaseEntity
from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user_application_role import UserApplicationRole
from app.models.user_country_scope import UserCountryScope

T = TypeVar("T", bound=BaseEntity)


def has_permission(
    session: Session,
    *,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
    permission_key: str,
) -> bool:
    """
    Determines whether a user has a specific permission in an application.
    Traverses:
    User -> UserApplicationRole -> Role -> RolePermission -> Permission
    without hardcoding role names.
    """
    stmt = (
        select(Permission.id)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(Role, Role.id == RolePermission.role_id)
        .join(UserApplicationRole, UserApplicationRole.role_id == Role.id)
        .where(
            UserApplicationRole.user_id == user_id,
            UserApplicationRole.application_id == application_id,
            Role.owner_app_id == application_id,
            Permission.owner_app_id == application_id,
            Permission.key == permission_key,
        )
        .limit(1)
    )
    return session.execute(stmt).scalar_one_or_none() is not None


def get_allowed_country_ids(
    session: Session,
    *,
    user_id: uuid.UUID,
    application_id: uuid.UUID,
) -> set[uuid.UUID]:
    """
    Returns the set of country IDs a user is authorized to access for a given application.
    """
    stmt = select(UserCountryScope.country_id).where(
        UserCountryScope.user_id == user_id,
        UserCountryScope.application_id == application_id,
    )
    return set(session.execute(stmt).scalars().all())


def apply_entity_scope(
    stmt: Select[tuple[T]],
    *,
    entity_cls: type[T],
    application_id: uuid.UUID,
    allowed_country_ids: Sequence[uuid.UUID] | set[uuid.UUID],
    include_deleted: bool = False,
) -> Select[tuple[T]]:
    """
    Applies reusable SQL query-level scope constraints for any BaseEntity subclass:
    1. owner_app_id == application_id
    2. country_id IN (allowed_country_ids)
    3. deleted_at IS NULL (unless explicitly including deleted entities)

    Executes entirely in SQL. If allowed_country_ids is empty, forces an unsatisfiable condition.
    """
    if not allowed_country_ids:
        # User has no country scopes for this application; return empty result set safely at query level
        return stmt.where(False)

    scoped_stmt = stmt.where(
        entity_cls.owner_app_id == application_id,
        entity_cls.country_id.in_(allowed_country_ids),
    )

    if not include_deleted:
        scoped_stmt = scoped_stmt.where(entity_cls.deleted_at.is_(None))

    return scoped_stmt
