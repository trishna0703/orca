import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.country import Country
from app.models.user import User
from app.schemas.case import CaseCreate
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


def test_successful_case_creation_creates_audit_log(context):
    """
    Given Alice creates a Case in Arnova:
    Verify Case exists AND exactly one corresponding AuditLog exists with:
    - actor_id = Alice
    - application_id = Care Companion
    - action = case.created
    - entity_type = case
    - entity_id = created Case ID
    - country_id = Arnova
    - before_data = null
    - after_data containing correct Case payload
    - request_id preserved
    """
    alice = context["alice"]
    arnova = context["arnova"]
    care_app = context["app"]
    custom_req_id = f"test-req-{uuid.uuid4()}"

    payload = {
        "title": "Alice Arnova Audit Test",
        "description": "Checking audit persistence",
        "country_id": str(arnova.id),
        "status": "open",
    }
    response = client.post(
        "/v1/cases",
        headers={
            "X-User-Id": str(alice.id),
            "X-Request-Id": custom_req_id,
        },
        json=payload,
    )
    assert response.status_code == 201
    case_data = response.json()
    case_id = uuid.UUID(case_data["id"])

    # Verify response header has correlation ID
    assert response.headers["X-Request-Id"] == custom_req_id

    with SessionLocal() as session:
        # Check audit log in database
        audit = session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "case",
                AuditLog.entity_id == case_id,
            )
        ).scalar_one_or_none()

        assert audit is not None
        assert audit.actor_id == alice.id
        assert audit.application_id == care_app.id
        assert audit.action == "case.created"
        assert audit.country_id == arnova.id
        assert audit.before_data is None
        assert audit.after_data is not None
        assert audit.after_data["title"] == "Alice Arnova Audit Test"
        assert audit.after_data["status"] == "open"
        assert audit.after_data["id"] == str(case_id)
        assert audit.request_id == custom_req_id
        assert audit.created_at is not None


def test_permission_failure_creates_no_audit_log(context):
    """
    Carol (viewer) has no case:create permission.
    POST /v1/cases returns 403.
    Verify no Case and no AuditLog with action 'case.created' is persisted.
    """
    carol = context["carol"]
    belmara = context["belmara"]

    unique_title = f"Unauthorized Carol Case {uuid.uuid4()}"
    payload = {
        "title": unique_title,
        "description": "Forbidden attempt",
        "country_id": str(belmara.id),
        "status": "open",
    }
    response = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(carol.id)},
        json=payload,
    )
    assert response.status_code == 403

    with SessionLocal() as session:
        case = session.execute(
            select(Case).where(Case.title == unique_title)
        ).scalar_one_or_none()
        assert case is None

        audit = session.execute(
            select(AuditLog).where(
                AuditLog.action == "case.created",
                AuditLog.actor_id == carol.id,
            )
        ).scalar_one_or_none()
        assert audit is None


def test_country_scope_failure_creates_no_audit_log(context):
    """
    Bob has case:create but only for Calduria.
    Attempting to create in Arnova returns 403.
    Verify no Case and no AuditLog is created.
    """
    bob = context["bob"]
    arnova = context["arnova"]

    unique_title = f"Out-of-scope Bob Case {uuid.uuid4()}"
    payload = {
        "title": unique_title,
        "description": "Scope violation",
        "country_id": str(arnova.id),
        "status": "open",
    }
    response = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(bob.id)},
        json=payload,
    )
    assert response.status_code == 403

    with SessionLocal() as session:
        case = session.execute(
            select(Case).where(Case.title == unique_title)
        ).scalar_one_or_none()
        assert case is None

        # Check no audit log was created for Bob under arnova
        audit = session.execute(
            select(AuditLog).where(
                AuditLog.actor_id == bob.id,
                AuditLog.country_id == arnova.id,
            )
        ).scalar_one_or_none()
        assert audit is None


def test_transaction_atomicity_rollback(context, monkeypatch):
    """
    Simulate a failure during audit log recording.
    Verify the transaction rolls back completely: neither the Case nor the AuditLog is persisted.
    """
    alice = context["alice"]
    arnova = context["arnova"]
    care_app = context["app"]

    unique_title = f"Rollback Case {uuid.uuid4()}"
    case_in = CaseCreate(
        title=unique_title,
        description="Should roll back",
        country_id=arnova.id,
    )

    with SessionLocal() as session:
        service = CaseService(session)

        # Monkeypatch record_audit to simulate an unexpected error during audit persistence
        import app.services.case_service as cs_module

        def mock_record_audit(*args, **kwargs):
            raise RuntimeError("Simulated audit persistence failure")

        monkeypatch.setattr(cs_module, "record_audit", mock_record_audit)

        with pytest.raises(RuntimeError, match="Simulated audit persistence failure"):
            service.create_case(
                data=case_in,
                application_id=care_app.id,
                user_id=alice.id,
                allowed_country_ids={arnova.id},
            )

    # Verify database state in a fresh session
    with SessionLocal() as session:
        case = session.execute(
            select(Case).where(Case.title == unique_title)
        ).scalar_one_or_none()
        assert case is None, "Case should have been rolled back"

        audit = session.execute(
            select(AuditLog).where(
                AuditLog.actor_id == alice.id,
                AuditLog.country_id == arnova.id,
                AuditLog.after_data["title"].astext == unique_title,
            )
        ).scalar_one_or_none()
        assert audit is None, "Audit log should have been rolled back"


def test_audit_logs_read_endpoint(context):
    """
    Test GET /v1/audit-logs:
    - Alice (case-manager) has 'audit:read' permission and scopes for Arnova + Belmara.
    - Bob (case-worker) lacks 'audit:read' permission -> 403 Forbidden.
    - Alice querying receives logs scoped to Arnova/Belmara.
    """
    alice = context["alice"]
    bob = context["bob"]

    # Bob attempts reading audit logs -> 403 Forbidden
    res_bob = client.get("/v1/audit-logs", headers={"X-User-Id": str(bob.id)})
    assert res_bob.status_code == 403
    assert "audit:read" in res_bob.json()["detail"]

    # Alice reads audit logs -> 200 OK
    res_alice = client.get("/v1/audit-logs", headers={"X-User-Id": str(alice.id)})
    assert res_alice.status_code == 200
    logs = res_alice.json()
    assert isinstance(logs, list)
    assert len(logs) >= 1

    # Verify that all returned logs belong to Alice's country scopes or are global
    for log in logs:
        if log["country_id"] is not None:
            assert log["country_id"] in [
                str(context["arnova"].id),
                str(context["belmara"].id),
            ]
