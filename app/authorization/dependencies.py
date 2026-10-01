import uuid
from typing import Callable
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authorization.service import (
    get_allowed_country_ids,
    has_permission,
)
from app.db.session import get_db
from app.models.application import Application
from app.models.user import User

# Constant identifiers for application keys
CARE_COMPANION_APP_KEY = "care-companion"
COMMAND_VIEW_APP_KEY = "command-view"
PARTNER_ENGAGE_APP_KEY = "partner-engage"


def get_current_user(
    x_user_id: str | None = Header(
        default=None,
        alias="X-User-Id",
        description="Development/Demo authentication: user UUID header (NOT for production)",
    ),
    db: Session = Depends(get_db),
) -> User:
    """
    Lightweight development/demo authentication mechanism.
    Inspects the X-User-Id header to resolve an existing User.
    Clearly marked as development/demo authentication, not production authentication.
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing development authentication header X-User-Id",
        )

    try:
        user_uuid = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid UUID format for X-User-Id",
        )

    user = db.get(User, user_uuid)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


def resolve_application(
    app_key: str,
) -> Callable[[Session], Application]:
    """
    Factory creating a dependency that resolves an Application by its unique key.
    Avoids hardcoding literal queries across route handlers.
    """

    def _resolve(db: Session = Depends(get_db)) -> Application:
        stmt = select(Application).where(Application.key == app_key).limit(1)
        app = db.execute(stmt).scalar_one_or_none()
        if not app:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Application '{app_key}' not found in platform registry",
            )
        return app

    return _resolve


# Dedicated resolver dependencies
get_care_companion_app = resolve_application(CARE_COMPANION_APP_KEY)
get_command_view_app = resolve_application(COMMAND_VIEW_APP_KEY)
get_partner_engage_app = resolve_application(PARTNER_ENGAGE_APP_KEY)


def require_permission(
    permission_key: str,
    app_resolver: Callable[[Session], Application] = get_care_companion_app,
) -> Callable[..., None]:
    """
    FastAPI dependency factory enforcing that current_user possesses permission_key
    in the application resolved by app_resolver.
    """

    def _check_permission(
        current_user: User = Depends(get_current_user),
        current_app: Application = Depends(app_resolver),
        db: Session = Depends(get_db),
    ) -> None:
        authorized = has_permission(
            db,
            user_id=current_user.id,
            application_id=current_app.id,
            permission_key=permission_key,
        )
        if not authorized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: '{permission_key}'",
            )

    return _check_permission


def get_user_country_scope(
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_care_companion_app),
    db: Session = Depends(get_db),
) -> set[uuid.UUID]:
    """
    FastAPI dependency returning the set of allowed country UUIDs for current_user
    under Care Companion.
    """
    return get_allowed_country_ids(
        db,
        user_id=current_user.id,
        application_id=current_app.id,
    )


def get_command_view_country_scope(
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_command_view_app),
    db: Session = Depends(get_db),
) -> set[uuid.UUID]:
    """
    FastAPI dependency returning the set of allowed country UUIDs for current_user
    under Command View.
    """
    return get_allowed_country_ids(
        db,
        user_id=current_user.id,
        application_id=current_app.id,
    )


def get_partner_engage_country_scope(
    current_user: User = Depends(get_current_user),
    current_app: Application = Depends(get_partner_engage_app),
    db: Session = Depends(get_db),
) -> set[uuid.UUID]:
    """
    FastAPI dependency returning the set of allowed country UUIDs for current_user
    under Partner Engage.
    """
    return get_allowed_country_ids(
        db,
        user_id=current_user.id,
        application_id=current_app.id,
    )
