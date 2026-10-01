from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.events.repository import OutboxRepository
from app.main import app
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.case import Case, CaseStatus
from app.models.country import Country
from app.models.outbox_event import OutboxEvent, OutboxStatus
from app.models.user import User
from app.schemas.case import CaseAssignRequest, CaseCreate, CaseUpdate
from app.services.case_service import CaseService
from scripts.seed import seed_data

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_seed():
    with SessionLocal() as session:
        seed_data(session)


@pytest.fixture(scope="module")
def context(setup_seed):
    with SessionLocal() as session:
        care_app = session.execute(
            select(Application).where(Application.key == "care-companion")
        ).scalar_one()
        alice = session.execute(
            select(User).where(User.display_name == "Alice")
        ).scalar_one()
        bob = session.execute(
            select(User).where(User.display_name == "Bob")
        ).scalar_one()
        carol = session.execute(
            select(User).where(User.display_name == "Carol")
        ).scalar_one()

        arnova = session.execute(
            select(Country).where(Country.code == "ARN")
        ).scalar_one()
        belmara = session.execute(
            select(Country).where(Country.code == "BEL")
        ).scalar_one()
        calduria = session.execute(
            select(Country).where(Country.code == "CAL")
        ).scalar_one()

        return {
            "app": care_app,
            "alice": alice,
            "bob": bob,
            "carol": carol,
            "arnova": arnova,
            "belmara": belmara,
            "calduria": calduria,
        }


def test_case_create_produces_outbox_event(context):
    """
    POST /v1/cases produces Case, AuditLog (case.created), and OutboxEvent (case.created.v1)
    atomically.
    """
    alice = context["alice"]
    arnova = context["arnova"]
    care_app = context["app"]

    title = f"Outbox Create Test {uuid.uuid4()}"
    res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={
            "title": title,
            "description": "Testing atomic outbox event creation",
            "country_id": str(arnova.id),
            "status": "open",
        },
    )
    assert res.status_code == 201
    case_id = uuid.UUID(res.json()["id"])

    with SessionLocal() as session:
        # Check outbox event
        event = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == case_id,
                OutboxEvent.event_type == "case.created.v1",
            )
        ).scalar_one_or_none()
        assert event is not None
        assert event.application_id == care_app.id
        assert event.aggregate_type == "case"
        assert event.country_id == arnova.id
        assert event.status == OutboxStatus.PENDING.value
        assert event.payload["case_id"] == str(case_id)
        assert event.payload["title"] == title
        assert event.payload["status"] == "open"


def test_update_case_authorized_and_audited(context):
    """
    PATCH /v1/cases/{case_id}
    - Alice updates title and description
    - Version increments
    - AuditLog(case.updated) contains before_data and after_data
    - OutboxEvent(case.updated.v1) created with changed_fields
    """
    alice = context["alice"]
    arnova = context["arnova"]

    # 1. Create a case first
    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={
            "title": "Initial Title",
            "description": "Initial Desc",
            "country_id": str(arnova.id),
        },
    )
    case_id = create_res.json()["id"]
    initial_version = create_res.json()["version"]

    # 2. Update case
    update_res = client.patch(
        f"/v1/cases/{case_id}",
        headers={"X-User-Id": str(alice.id)},
        json={
            "title": "Updated Title",
            "description": "Updated Desc",
            "expected_version": initial_version,
        },
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["title"] == "Updated Title"
    assert updated_data["description"] == "Updated Desc"
    assert updated_data["version"] == initial_version + 1

    with SessionLocal() as session:
        # Check AuditLog
        audit = (
            session.execute(
                select(AuditLog)
                .where(
                    AuditLog.entity_id == uuid.UUID(case_id),
                    AuditLog.action == "case.updated",
                )
                .order_by(AuditLog.created_at.desc())
            )
            .scalars()
            .first()
        )
        assert audit is not None
        assert audit.before_data["title"] == "Initial Title"
        assert audit.after_data["title"] == "Updated Title"

        # Check OutboxEvent
        event = (
            session.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == uuid.UUID(case_id),
                    OutboxEvent.event_type == "case.updated.v1",
                )
                .order_by(OutboxEvent.created_at.desc())
            )
            .scalars()
            .first()
        )
        assert event is not None
        assert "changed_fields" in event.payload
        assert event.payload["changed_fields"]["title"]["before"] == "Initial Title"
        assert event.payload["changed_fields"]["title"]["after"] == "Updated Title"


def test_update_case_optimistic_concurrency_conflict(context):
    """
    PATCH with wrong expected_version returns 409 Conflict.
    """
    alice = context["alice"]
    arnova = context["arnova"]

    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Concurrency Case", "country_id": str(arnova.id)},
    )
    case_id = create_res.json()["id"]

    res = client.patch(
        f"/v1/cases/{case_id}",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "New Title", "expected_version": 999},
    )
    assert res.status_code == 409
    assert "Version conflict" in res.json()["detail"]


def test_update_case_unauthorized_permission(context):
    """
    Carol (viewer) lacks case:update -> 403 Forbidden.
    """
    carol = context["carol"]
    alice = context["alice"]
    belmara = context["belmara"]

    # Alice creates a Belmara case (Carol has scope for Belmara)
    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Belmara Case", "country_id": str(belmara.id)},
    )
    case_id = create_res.json()["id"]

    # Carol attempts update
    res = client.patch(
        f"/v1/cases/{case_id}",
        headers={"X-User-Id": str(carol.id)},
        json={"title": "Carol update attempt"},
    )
    assert res.status_code == 403
    assert "case:update" in res.json()["detail"]


def test_update_case_country_scope_404(context):
    """
    Bob has case:update but is only scoped to Calduria.
    Attempting to update an Arnova case returns 404 (hidden resource).
    """
    bob = context["bob"]
    alice = context["alice"]
    arnova = context["arnova"]

    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Arnova Private Case", "country_id": str(arnova.id)},
    )
    case_id = create_res.json()["id"]

    res = client.patch(
        f"/v1/cases/{case_id}",
        headers={"X-User-Id": str(bob.id)},
        json={"title": "Bob hacking"},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Case not found"


def test_assign_case_success(context):
    """
    POST /v1/cases/{case_id}/assign
    - Alice assigns an Arnova case to Alice (Alice has Care Companion role and Arnova scope)
    - Verifies assigned_to, audit log, outbox event (case.assigned.v1)
    """
    alice = context["alice"]
    arnova = context["arnova"]

    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Case to Assign", "country_id": str(arnova.id)},
    )
    case_id = create_res.json()["id"]

    assign_res = client.post(
        f"/v1/cases/{case_id}/assign",
        headers={"X-User-Id": str(alice.id)},
        json={"assigned_to": str(alice.id)},
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["assigned_to"] == str(alice.id)

    with SessionLocal() as session:
        event = (
            session.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == uuid.UUID(case_id),
                    OutboxEvent.event_type == "case.assigned.v1",
                )
                .order_by(OutboxEvent.created_at.desc())
            )
            .scalars()
            .first()
        )
        assert event is not None
        assert event.payload["assigned_to"] == str(alice.id)


def test_assign_case_ineligible_assignee(context):
    """
    Bob only has scope for Calduria.
    Alice attempting to assign an Arnova case to Bob must fail with 422 Unprocessable Entity
    because Bob lacks country scope for Arnova.
    """
    alice = context["alice"]
    bob = context["bob"]
    arnova = context["arnova"]

    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Arnova Assign Test", "country_id": str(arnova.id)},
    )
    case_id = create_res.json()["id"]

    assign_res = client.post(
        f"/v1/cases/{case_id}/assign",
        headers={"X-User-Id": str(alice.id)},
        json={"assigned_to": str(bob.id)},
    )
    assert assign_res.status_code == 422
    assert "Assignee does not have country scope" in assign_res.json()["detail"]


def test_close_case_success_and_conflict(context):
    """
    POST /v1/cases/{case_id}/close
    - Closes an open case -> 200 OK
    - Checks closed_at, closed_by, AuditLog(case.closed), OutboxEvent(case.closed.v1)
    - Re-closing already closed case -> 409 Conflict
    """
    alice = context["alice"]
    arnova = context["arnova"]

    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Case to Close", "country_id": str(arnova.id)},
    )
    case_id = create_res.json()["id"]

    # 1. Close case
    close_res = client.post(
        f"/v1/cases/{case_id}/close",
        headers={"X-User-Id": str(alice.id)},
    )
    assert close_res.status_code == 200
    closed_data = close_res.json()
    assert closed_data["status"] == "closed"
    assert closed_data["closed_at"] is not None
    assert closed_data["closed_by"] == str(alice.id)

    with SessionLocal() as session:
        event = (
            session.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_id == uuid.UUID(case_id),
                    OutboxEvent.event_type == "case.closed.v1",
                )
                .order_by(OutboxEvent.created_at.desc())
            )
            .scalars()
            .first()
        )
        assert event is not None
        assert event.payload["previous_status"] == "open"
        assert event.payload["status"] == "closed"
        assert event.payload["closed_by"] == str(alice.id)

    # 2. Re-close case -> 409 Conflict
    reclose_res = client.post(
        f"/v1/cases/{case_id}/close",
        headers={"X-User-Id": str(alice.id)},
    )
    assert reclose_res.status_code == 409
    assert "Case is already closed" in reclose_res.json()["detail"]


def test_soft_delete_case(context):
    """
    DELETE /v1/cases/{case_id}
    - Sets deleted_at, deleted_by, updated_by
    - Record physically exists, but GET returns 404
    - Emits AuditLog(case.deleted) and OutboxEvent(case.deleted.v1)
    """
    alice = context["alice"]
    arnova = context["arnova"]

    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Case to Delete", "country_id": str(arnova.id)},
    )
    case_id = create_res.json()["id"]

    # Delete case
    del_res = client.delete(
        f"/v1/cases/{case_id}",
        headers={"X-User-Id": str(alice.id)},
    )
    assert del_res.status_code == 204

    # Subsequent GET returns 404
    get_res = client.get(
        f"/v1/cases/{case_id}",
        headers={"X-User-Id": str(alice.id)},
    )
    assert get_res.status_code == 404

    # Verify physical existence and audit/outbox entries
    with SessionLocal() as session:
        raw_case = session.get(Case, uuid.UUID(case_id))
        assert raw_case is not None
        assert raw_case.deleted_at is not None
        assert raw_case.deleted_by == alice.id

        event = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == uuid.UUID(case_id),
                OutboxEvent.event_type == "case.deleted.v1",
            )
        ).scalar_one_or_none()
        assert event is not None
        assert event.payload["deleted_by"] == str(alice.id)


def test_outbox_failure_causes_full_rollback(context, monkeypatch):
    """
    Simulate an error during OutboxEvent recording.
    Verify transaction rolls back: Case is NOT updated, AuditLog is NOT recorded, OutboxEvent is NOT recorded.
    """
    alice = context["alice"]
    arnova = context["arnova"]
    care_app = context["app"]

    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Rollback Test Case", "country_id": str(arnova.id)},
    )
    case_id = uuid.UUID(create_res.json()["id"])
    initial_version = create_res.json()["version"]

    with SessionLocal() as session:
        service = CaseService(session)

        import app.services.case_service as cs_module

        def mock_record_outbox(*args, **kwargs):
            raise RuntimeError("Simulated outbox failure")

        monkeypatch.setattr(cs_module, "record_outbox_event", mock_record_outbox)

        with pytest.raises(RuntimeError, match="Simulated outbox failure"):
            service.update_case(
                case_id=case_id,
                data=CaseUpdate(title="Should Not Persist"),
                application_id=care_app.id,
                user_id=alice.id,
                allowed_country_ids={arnova.id},
            )

    # In fresh session, confirm case title and version were rolled back
    with SessionLocal() as session:
        fresh_case = session.get(Case, case_id)
        assert fresh_case.title == "Rollback Test Case"
        assert fresh_case.version == initial_version

        # Verify no case.updated audit entry exists for this case
        audit = session.execute(
            select(AuditLog).where(
                AuditLog.entity_id == case_id,
                AuditLog.action == "case.updated",
            )
        ).scalar_one_or_none()
        assert audit is None


def test_outbox_repository_list_pending(context):
    """
    Test OutboxRepository.list_pending ordering (created_at ASC).
    """
    care_app = context["app"]
    with SessionLocal() as session:
        repo = OutboxRepository(session)
        pending = repo.list_pending(application_id=care_app.id, limit=10)
        assert len(pending) > 0
        # Verify ordering
        for i in range(len(pending) - 1):
            assert pending[i].created_at <= pending[i + 1].created_at
