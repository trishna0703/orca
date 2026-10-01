from datetime import datetime, timezone
import uuid
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.serializers import serialize_entity
from app.audit.service import record_audit
from app.authorization.service import get_allowed_country_ids
from app.events.service import record_outbox_event
from app.models.case import Case, CaseStatus
from app.models.user import User
from app.models.user_application_role import UserApplicationRole
from app.repositories.case_repository import CaseRepository
from app.schemas.case import CaseAssignRequest, CaseCreate, CaseUpdate


class CaseService:
    """
    Business service layer coordinating Case domain operations, authorization validation,
    and atomic transaction management including generic audit logging and transactional outbox events.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CaseRepository(session)

    def list_cases(
        self,
        *,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
    ) -> list[Case]:
        return self.repository.list_scoped(
            application_id=application_id,
            allowed_country_ids=allowed_country_ids,
        )

    def get_case(
        self,
        *,
        case_id: uuid.UUID,
        application_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
    ) -> Case:
        case = self.repository.get_scoped(
            case_id=case_id,
            application_id=application_id,
            allowed_country_ids=allowed_country_ids,
        )
        if not case:
            # Avoid leaking existence of out-of-scope records
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Case not found",
            )
        return case

    def create_case(
        self,
        *,
        data: CaseCreate,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
        request_id: str | uuid.UUID | None = None,
    ) -> Case:
        """
        Creates a Case, AuditLog, and OutboxEvent atomically in a single transaction.
        If any step fails, the entire transaction is rolled back.
        """
        # Enforce country scope for requested country
        if data.country_id not in allowed_country_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is not authorized for country_id '{data.country_id}'",
            )

        try:
            # 1. Create and flush Case (populates case.id, server defaults)
            case = self.repository.create(
                data=data,
                application_id=application_id,
                created_by_user_id=user_id,
            )

            # 2. Serialize entity state for audit trail
            after_payload = serialize_entity(case)

            # 3. Record audit entry in the same session without committing
            record_audit(
                session=self.session,
                actor_id=user_id,
                application_id=application_id,
                action="case.created",
                entity_type="case",
                entity_id=case.id,
                country_id=case.country_id,
                before_data=None,
                after_data=after_payload,
                metadata=None,
                request_id=request_id,
            )

            # 4. Record outbox event in the same session without committing
            event_payload = {
                "case_id": str(case.id),
                "country_id": str(case.country_id),
                "title": case.title,
                "status": case.status.value,
                "created_by": str(case.created_by),
                "created_at": case.created_at.isoformat() if case.created_at else None,
            }
            record_outbox_event(
                session=self.session,
                application_id=application_id,
                event_type="case.created.v1",
                aggregate_type="case",
                aggregate_id=case.id,
                country_id=case.country_id,
                payload=event_payload,
                request_id=request_id,
            )

            # 5. Atomically commit Case, AuditLog, and OutboxEvent
            self.session.commit()
            self.session.refresh(case)
            return case
        except HTTPException:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise

    def update_case(
        self,
        *,
        case_id: uuid.UUID,
        data: CaseUpdate,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
        request_id: str | uuid.UUID | None = None,
    ) -> Case:
        """
        Updates mutable fields of a Case (title, description), increments version,
        and records AuditLog + case.updated.v1 event atomically.
        """
        try:
            case = self.repository.get_scoped(
                case_id=case_id,
                application_id=application_id,
                allowed_country_ids=allowed_country_ids,
            )
            if not case:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Case not found",
                )

            # Check optimistic concurrency if client passed expected_version
            if (
                data.expected_version is not None
                and case.version != data.expected_version
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Version conflict: current version is {case.version}, expected {data.expected_version}",
                )

            before_payload = serialize_entity(case)
            changed_fields: dict[str, dict[str, str | None]] = {}

            if data.title is not None and data.title != case.title:
                changed_fields["title"] = {"before": case.title, "after": data.title}
                case.title = data.title

            if data.description is not None and data.description != case.description:
                changed_fields["description"] = {
                    "before": case.description,
                    "after": data.description,
                }
                case.description = data.description

            case.updated_by = user_id
            case.version += 1
            self.session.flush()

            after_payload = serialize_entity(case)

            record_audit(
                session=self.session,
                actor_id=user_id,
                application_id=application_id,
                action="case.updated",
                entity_type="case",
                entity_id=case.id,
                country_id=case.country_id,
                before_data=before_payload,
                after_data=after_payload,
                metadata=None,
                request_id=request_id,
            )

            event_payload = {
                "case_id": str(case.id),
                "country_id": str(case.country_id),
                "changed_fields": changed_fields,
                "version": case.version,
                "updated_by": str(user_id),
            }
            record_outbox_event(
                session=self.session,
                application_id=application_id,
                event_type="case.updated.v1",
                aggregate_type="case",
                aggregate_id=case.id,
                country_id=case.country_id,
                payload=event_payload,
                request_id=request_id,
            )

            self.session.commit()
            self.session.refresh(case)
            return case
        except HTTPException:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise

    def assign_case(
        self,
        *,
        case_id: uuid.UUID,
        data: CaseAssignRequest,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
        request_id: str | uuid.UUID | None = None,
    ) -> Case:
        """
        Assigns a Case to a user.
        Validates assignee eligibility: assignee must exist, have a role in the application,
        and have country scope for the Case's country.
        """
        try:
            case = self.repository.get_scoped(
                case_id=case_id,
                application_id=application_id,
                allowed_country_ids=allowed_country_ids,
            )
            if not case:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Case not found",
                )

            if (
                data.expected_version is not None
                and case.version != data.expected_version
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Version conflict: current version is {case.version}, expected {data.expected_version}",
                )

            # Validate target assignee
            assignee = self.session.get(User, data.assigned_to)
            if not assignee:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Assignee user '{data.assigned_to}' not found",
                )

            # Check that assignee has a role in Care Companion
            has_role = (
                self.session.execute(
                    select(UserApplicationRole.id)
                    .where(
                        UserApplicationRole.user_id == data.assigned_to,
                        UserApplicationRole.application_id == application_id,
                    )
                    .limit(1)
                ).scalar_one_or_none()
                is not None
            )
            if not has_role:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Assignee does not have an active role in this application",
                )

            # Check that assignee has country scope for the Case's country
            assignee_countries = get_allowed_country_ids(
                self.session,
                user_id=data.assigned_to,
                application_id=application_id,
            )
            if case.country_id not in assignee_countries:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Assignee does not have country scope for this case's country",
                )

            before_payload = serialize_entity(case)
            previous_assigned_to = str(case.assigned_to) if case.assigned_to else None

            case.assigned_to = data.assigned_to
            case.updated_by = user_id
            case.version += 1
            self.session.flush()

            after_payload = serialize_entity(case)

            record_audit(
                session=self.session,
                actor_id=user_id,
                application_id=application_id,
                action="case.assigned",
                entity_type="case",
                entity_id=case.id,
                country_id=case.country_id,
                before_data=before_payload,
                after_data=after_payload,
                metadata=None,
                request_id=request_id,
            )

            event_payload = {
                "case_id": str(case.id),
                "country_id": str(case.country_id),
                "previous_assigned_to": previous_assigned_to,
                "assigned_to": str(data.assigned_to),
                "assigned_by": str(user_id),
                "version": case.version,
            }
            record_outbox_event(
                session=self.session,
                application_id=application_id,
                event_type="case.assigned.v1",
                aggregate_type="case",
                aggregate_id=case.id,
                country_id=case.country_id,
                payload=event_payload,
                request_id=request_id,
            )

            self.session.commit()
            self.session.refresh(case)
            return case
        except HTTPException:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise

    def close_case(
        self,
        *,
        case_id: uuid.UUID,
        expected_version: int | None = None,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
        request_id: str | uuid.UUID | None = None,
    ) -> Case:
        """
        Closes an open or in_progress Case.
        Rejects closing already-closed cases with 409 Conflict.
        """
        try:
            case = self.repository.get_scoped(
                case_id=case_id,
                application_id=application_id,
                allowed_country_ids=allowed_country_ids,
            )
            if not case:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Case not found",
                )

            if expected_version is not None and case.version != expected_version:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Version conflict: current version is {case.version}, expected {expected_version}",
                )

            if case.status == CaseStatus.CLOSED:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Case is already closed",
                )

            before_payload = serialize_entity(case)
            previous_status = case.status.value

            now = datetime.now(timezone.utc)
            case.status = CaseStatus.CLOSED
            case.closed_at = now
            case.closed_by = user_id
            case.updated_by = user_id
            case.version += 1
            self.session.flush()

            after_payload = serialize_entity(case)

            record_audit(
                session=self.session,
                actor_id=user_id,
                application_id=application_id,
                action="case.closed",
                entity_type="case",
                entity_id=case.id,
                country_id=case.country_id,
                before_data=before_payload,
                after_data=after_payload,
                metadata=None,
                request_id=request_id,
            )

            event_payload = {
                "case_id": str(case.id),
                "country_id": str(case.country_id),
                "previous_status": previous_status,
                "status": CaseStatus.CLOSED.value,
                "closed_by": str(user_id),
                "closed_at": now.isoformat(),
                "version": case.version,
            }
            record_outbox_event(
                session=self.session,
                application_id=application_id,
                event_type="case.closed.v1",
                aggregate_type="case",
                aggregate_id=case.id,
                country_id=case.country_id,
                payload=event_payload,
                request_id=request_id,
            )

            self.session.commit()
            self.session.refresh(case)
            return case
        except HTTPException:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise

    def soft_delete_case(
        self,
        *,
        case_id: uuid.UUID,
        expected_version: int | None = None,
        application_id: uuid.UUID,
        user_id: uuid.UUID,
        allowed_country_ids: set[uuid.UUID],
        request_id: str | uuid.UUID | None = None,
    ) -> None:
        """
        Soft deletes a Case by setting deleted_at, deleted_by, updated_by and incrementing version.
        Emits case.deleted audit log and case.deleted.v1 outbox event.
        """
        try:
            case = self.repository.get_scoped(
                case_id=case_id,
                application_id=application_id,
                allowed_country_ids=allowed_country_ids,
            )
            if not case:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Case not found",
                )

            if expected_version is not None and case.version != expected_version:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Version conflict: current version is {case.version}, expected {expected_version}",
                )

            before_payload = serialize_entity(case)

            now = datetime.now(timezone.utc)
            case.deleted_at = now
            case.deleted_by = user_id
            case.updated_by = user_id
            case.version += 1
            self.session.flush()

            after_payload = serialize_entity(case)

            record_audit(
                session=self.session,
                actor_id=user_id,
                application_id=application_id,
                action="case.deleted",
                entity_type="case",
                entity_id=case.id,
                country_id=case.country_id,
                before_data=before_payload,
                after_data=after_payload,
                metadata=None,
                request_id=request_id,
            )

            event_payload = {
                "case_id": str(case.id),
                "country_id": str(case.country_id),
                "deleted_by": str(user_id),
                "deleted_at": now.isoformat(),
                "version": case.version,
            }
            record_outbox_event(
                session=self.session,
                application_id=application_id,
                event_type="case.deleted.v1",
                aggregate_type="case",
                aggregate_id=case.id,
                country_id=case.country_id,
                payload=event_payload,
                request_id=request_id,
            )

            self.session.commit()
        except HTTPException:
            self.session.rollback()
            raise
        except Exception:
            self.session.rollback()
            raise
