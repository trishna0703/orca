import uuid
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authorization.service import apply_entity_scope
from app.models.case import Case
from app.schemas.case import CaseCreate


class CaseRepository:
    """
    Data access layer for Case entities.
    Applies entity-level and geographic-level query constraints in SQL.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def list_scoped(
        self,
        *,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID] | Sequence[uuid.UUID],
    ) -> list[Case]:
        """
        Queries Cases strictly constrained by application ownership, country scopes,
        and soft-delete status at the SQL level.
        """
        stmt = select(Case)
        stmt = apply_entity_scope(
            stmt,
            entity_cls=Case,
            application_id=application_id,
            allowed_country_ids=allowed_country_ids,
            include_deleted=False,
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_scoped(
        self,
        *,
        case_id: uuid.UUID,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID] | Sequence[uuid.UUID],
    ) -> Case | None:
        """
        Retrieves a single Case with application, country scope, and soft-delete checks
        pushed directly into the SQL WHERE clause.
        Returns None if record does not exist or user lacks scope (preventing information leakage).
        """
        stmt = select(Case).where(Case.id == case_id)
        stmt = apply_entity_scope(
            stmt,
            entity_cls=Case,
            application_id=application_id,
            allowed_country_ids=allowed_country_ids,
            include_deleted=False,
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def create(
        self,
        *,
        data: CaseCreate,
        application_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
    ) -> Case:
        """
        Persists a new Case entity with server-controlled ownership, audit, and lifecycle fields.
        Adds and flushes the entity to generate its ID. Does NOT commit so caller controls the transaction.
        """
        case = Case(
            title=data.title,
            description=data.description,
            status=data.status,
            country_id=data.country_id,
            owner_app_id=application_id,
            created_by=created_by_user_id,
        )
        self.session.add(case)
        self.session.flush()
        return case
