import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.base import Base
from app.db.session import SessionLocal
from app.main import app
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.country import Country
from app.models.partner import Partner, PartnerStatus
from app.models.user import User
from scripts.seed import seed_data

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_seed():
    with SessionLocal() as session:
        seed_data(session)


@pytest.fixture(scope="module")
def context(setup_seed):
    with SessionLocal() as session:
        partner_app = session.execute(
            select(Application).where(Application.key == "partner-engage")
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
            "partner_app": partner_app,
            "alice": alice,
            "bob": bob,
            "carol": carol,
            "arnova": arnova,
            "belmara": belmara,
            "calduria": calduria,
        }


def test_partner_inherits_base_entity_columns():
    """1. Partner inherits BaseEntity columns and has Partner domain columns."""
    partner_table = Base.metadata.tables["partners"]
    columns = {col.name for col in partner_table.columns}

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
    expected_partner_columns = {
        "name",
        "partner_type",
        "contact_email",
        "status",
    }

    assert expected_base_columns.issubset(columns)
    assert expected_partner_columns.issubset(columns)


def test_authorized_user_can_create_partner(context):
    """2. Authorized user (Alice, partner-manager in Arnova) can create Partner."""
    alice = context["alice"]
    arnova = context["arnova"]
    partner_app = context["partner_app"]

    res = client.post(
        "/v1/partners",
        headers={"X-User-Id": str(alice.id)},
        json={
            "name": "Red Cross Arnova",
            "partner_type": "NGO",
            "contact_email": "arnova@redcross.org",
            "country_id": str(arnova.id),
            "status": "active",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Red Cross Arnova"
    assert data["partner_type"] == "NGO"
    assert data["country_id"] == str(arnova.id)
    assert data["owner_app_id"] == str(partner_app.id)
    assert data["created_by"] == str(alice.id)
    assert data["version"] == 1


def test_create_partner_produces_generic_audit_log(context):
    """3. Create produces correct generic AuditLog."""
    alice = context["alice"]
    arnova = context["arnova"]
    partner_app = context["partner_app"]
    custom_req_id = f"test-req-partner-{uuid.uuid4()}"

    res = client.post(
        "/v1/partners",
        headers={
            "X-User-Id": str(alice.id),
            "X-Request-Id": custom_req_id,
        },
        json={
            "name": "Doctors Beyond Borders",
            "partner_type": "Medical",
            "contact_email": "contact@msf-arnova.org",
            "country_id": str(arnova.id),
        },
    )
    assert res.status_code == 201
    partner_id = uuid.UUID(res.json()["id"])

    with SessionLocal() as session:
        audit = session.execute(
            select(AuditLog).where(
                AuditLog.entity_type == "partner",
                AuditLog.entity_id == partner_id,
            )
        ).scalar_one_or_none()

        assert audit is not None
        assert audit.action == "partner.created"
        assert audit.actor_id == alice.id
        assert audit.application_id == partner_app.id
        assert audit.country_id == arnova.id
        assert audit.before_data is None
        assert audit.after_data is not None
        assert audit.after_data["name"] == "Doctors Beyond Borders"
        assert audit.after_data["partner_type"] == "Medical"
        assert audit.request_id == custom_req_id


def test_get_list_filters_countries_at_query_level(context):
    """4. GET list filters countries at SQL/query level (Alice sees Arnova, not Belmara/Calduria)."""
    alice = context["alice"]
    arnova = context["arnova"]
    belmara = context["belmara"]
    partner_app = context["partner_app"]

    # Directly persist a Belmara partner for partner-engage to test query filtering
    with SessionLocal() as session:
        belmara_partner = Partner(
            name="Belmara Shelter Corp",
            partner_type="Shelter",
            country_id=belmara.id,
            owner_app_id=partner_app.id,
            created_by=alice.id,
        )
        session.add(belmara_partner)
        session.commit()

    res = client.get("/v1/partners", headers={"X-User-Id": str(alice.id)})
    assert res.status_code == 200
    partners = res.json()
    assert len(partners) >= 1
    # Alice is ONLY scoped to Arnova in partner-engage
    for p in partners:
        assert p["country_id"] == str(arnova.id)


def test_user_cannot_access_partner_outside_country_scope(context):
    """5. User cannot access Partner outside country scope (returns 404 to avoid leaking existence)."""
    alice = context["alice"]
    belmara = context["belmara"]
    partner_app = context["partner_app"]

    with SessionLocal() as session:
        belmara_partner = (
            session.execute(
                select(Partner).where(
                    Partner.owner_app_id == partner_app.id,
                    Partner.country_id == belmara.id,
                )
            )
            .scalars()
            .first()
        )

    assert belmara_partner is not None

    # Alice requests Belmara partner -> 404
    res = client.get(
        f"/v1/partners/{belmara_partner.id}",
        headers={"X-User-Id": str(alice.id)},
    )
    assert res.status_code == 404
    assert res.json()["detail"] == "Partner not found"


def test_user_without_permission_gets_403(context):
    """6. User without permission (Bob has no role in partner-engage) gets 403."""
    bob = context["bob"]
    arnova = context["arnova"]

    # Create attempt
    res_create = client.post(
        "/v1/partners",
        headers={"X-User-Id": str(bob.id)},
        json={
            "name": "Bob's Illegal Partner",
            "partner_type": "Logistics",
            "country_id": str(arnova.id),
        },
    )
    assert res_create.status_code == 403
    assert "partner:create" in res_create.json()["detail"]

    # Read attempt
    res_read = client.get("/v1/partners", headers={"X-User-Id": str(bob.id)})
    assert res_read.status_code == 403
    assert "partner:read" in res_read.json()["detail"]


def test_patch_creates_correct_before_after_audit_snapshot(context):
    """7. PATCH creates correct before/after audit snapshot and increments version."""
    alice = context["alice"]
    arnova = context["arnova"]

    # Create partner
    create_res = client.post(
        "/v1/partners",
        headers={"X-User-Id": str(alice.id)},
        json={
            "name": "Initial Partner Name",
            "partner_type": "Relief",
            "country_id": str(arnova.id),
            "status": "active",
        },
    )
    partner_id = create_res.json()["id"]
    initial_version = create_res.json()["version"]

    # Update partner
    patch_res = client.patch(
        f"/v1/partners/{partner_id}",
        headers={"X-User-Id": str(alice.id)},
        json={
            "name": "Updated Partner Name",
            "contact_email": "updated@relief.org",
            "expected_version": initial_version,
        },
    )
    assert patch_res.status_code == 200
    updated_data = patch_res.json()
    assert updated_data["name"] == "Updated Partner Name"
    assert updated_data["contact_email"] == "updated@relief.org"
    assert updated_data["version"] == initial_version + 1

    with SessionLocal() as session:
        audit = (
            session.execute(
                select(AuditLog)
                .where(
                    AuditLog.entity_type == "partner",
                    AuditLog.entity_id == uuid.UUID(partner_id),
                    AuditLog.action == "partner.updated",
                )
                .order_by(AuditLog.created_at.desc())
            )
            .scalars()
            .first()
        )

        assert audit is not None
        assert audit.before_data["name"] == "Initial Partner Name"
        assert audit.before_data["contact_email"] is None
        assert audit.after_data["name"] == "Updated Partner Name"
        assert audit.after_data["contact_email"] == "updated@relief.org"
        assert audit.after_data["version"] == initial_version + 1
