import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models.application import Application
from app.models.case import Case, CaseStatus
from app.models.country import Country
from app.models.user import User
from scripts.seed import seed_data

client = TestClient(app)


@pytest.fixture(scope="module")
def setup_seed():
    with SessionLocal() as session:
        seed_data(session)


@pytest.fixture(scope="module")
def seed_entities(setup_seed):
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

        # Create one test case in Arnova, one in Belmara, one in Calduria
        case_arnova = Case(
            title="Arnova Case 1",
            country_id=arnova.id,
            owner_app_id=care_app.id,
            created_by=alice.id,
        )
        case_belmara = Case(
            title="Belmara Case 1",
            country_id=belmara.id,
            owner_app_id=care_app.id,
            created_by=alice.id,
        )
        case_calduria = Case(
            title="Calduria Case 1",
            country_id=calduria.id,
            owner_app_id=care_app.id,
            created_by=bob.id,
        )
        session.add_all([case_arnova, case_belmara, case_calduria])
        session.commit()
        session.refresh(case_arnova)
        session.refresh(case_belmara)
        session.refresh(case_calduria)

        return {
            "app": care_app,
            "alice": alice,
            "bob": bob,
            "carol": carol,
            "arnova": arnova,
            "belmara": belmara,
            "calduria": calduria,
            "case_arnova": case_arnova,
            "case_belmara": case_belmara,
            "case_calduria": case_calduria,
        }


def test_missing_auth_header():
    response = client.get("/v1/cases")
    assert response.status_code == 401
    assert "Missing development authentication header" in response.json()["detail"]


def test_permission_enforcement_create(seed_entities):
    """
    Carol is a viewer (has case:read, lacks case:create) -> should receive 403 Forbidden on POST.
    """
    carol = seed_entities["carol"]
    belmara = seed_entities["belmara"]

    payload = {
        "title": "Carol's unauthorized case",
        "description": "Should fail",
        "country_id": str(belmara.id),
        "status": "open",
    }
    response = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(carol.id)},
        json=payload,
    )
    assert response.status_code == 403
    assert "case:create" in response.json()["detail"]


def test_country_scope_enforcement_create(seed_entities):
    """
    Bob has case:create, but is ONLY scoped to Calduria.
    Attempting to create a Case in Arnova must return 403 Forbidden.
    """
    bob = seed_entities["bob"]
    arnova = seed_entities["arnova"]

    payload = {
        "title": "Bob's out-of-scope case",
        "description": "Should fail due to country scope",
        "country_id": str(arnova.id),
        "status": "open",
    }
    response = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(bob.id)},
        json=payload,
    )
    assert response.status_code == 403
    assert "not authorized for country_id" in response.json()["detail"]


def test_authorized_case_creation(seed_entities):
    """
    Bob creates a Case in Calduria (within his country scope and with case:create).
    Server must populate created_by = bob.id and owner_app_id = care-companion id.
    """
    bob = seed_entities["bob"]
    calduria = seed_entities["calduria"]
    care_app = seed_entities["app"]

    payload = {
        "title": "Bob's Calduria Clinic Visit",
        "description": "Legitimate creation",
        "country_id": str(calduria.id),
        "status": "open",
    }
    response = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(bob.id)},
        json=payload,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Bob's Calduria Clinic Visit"
    assert data["country_id"] == str(calduria.id)
    assert data["created_by"] == str(bob.id)
    assert data["owner_app_id"] == str(care_app.id)
    assert data["version"] == 1


def test_list_cases_country_scope_filtering(seed_entities):
    """
    Alice has scope for Arnova + Belmara.
    Bob has scope for Calduria.
    Carol has scope for Belmara.

    Queries must return ONLY the cases belonging to allowed countries.
    """
    alice = seed_entities["alice"]
    bob = seed_entities["bob"]
    carol = seed_entities["carol"]

    case_arnova = seed_entities["case_arnova"]
    case_belmara = seed_entities["case_belmara"]
    case_calduria = seed_entities["case_calduria"]

    # 1. Alice listing (Arnova + Belmara)
    res_alice = client.get("/v1/cases", headers={"X-User-Id": str(alice.id)})
    assert res_alice.status_code == 200
    alice_case_ids = {c["id"] for c in res_alice.json()}
    assert str(case_arnova.id) in alice_case_ids
    assert str(case_belmara.id) in alice_case_ids
    assert str(case_calduria.id) not in alice_case_ids

    # 2. Bob listing (Calduria only)
    res_bob = client.get("/v1/cases", headers={"X-User-Id": str(bob.id)})
    assert res_bob.status_code == 200
    bob_case_ids = {c["id"] for c in res_bob.json()}
    assert str(case_calduria.id) in bob_case_ids
    assert str(case_arnova.id) not in bob_case_ids
    assert str(case_belmara.id) not in bob_case_ids

    # 3. Carol listing (Belmara only)
    res_carol = client.get("/v1/cases", headers={"X-User-Id": str(carol.id)})
    assert res_carol.status_code == 200
    carol_case_ids = {c["id"] for c in res_carol.json()}
    assert str(case_belmara.id) in carol_case_ids
    assert str(case_arnova.id) not in carol_case_ids
    assert str(case_calduria.id) not in carol_case_ids


def test_get_case_by_id_scoped(seed_entities):
    """
    Alice requests Calduria case -> 404 (does not leak existence).
    Alice requests Arnova case -> 200.
    Bob requests Calduria case -> 200.
    """
    alice = seed_entities["alice"]
    bob = seed_entities["bob"]
    case_arnova = seed_entities["case_arnova"]
    case_calduria = seed_entities["case_calduria"]

    # Alice requests her own scope (Arnova)
    res_alice_ok = client.get(
        f"/v1/cases/{case_arnova.id}",
        headers={"X-User-Id": str(alice.id)},
    )
    assert res_alice_ok.status_code == 200
    assert res_alice_ok.json()["id"] == str(case_arnova.id)

    # Alice requests outside her scope (Calduria) -> 404
    res_alice_forbidden = client.get(
        f"/v1/cases/{case_calduria.id}",
        headers={"X-User-Id": str(alice.id)},
    )
    assert res_alice_forbidden.status_code == 404
    assert res_alice_forbidden.json()["detail"] == "Case not found"

    # Bob requests Calduria -> 200
    res_bob_ok = client.get(
        f"/v1/cases/{case_calduria.id}",
        headers={"X-User-Id": str(bob.id)},
    )
    assert res_bob_ok.status_code == 200
    assert res_bob_ok.json()["id"] == str(case_calduria.id)
