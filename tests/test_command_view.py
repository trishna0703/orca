from datetime import datetime, timezone
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.command_view.handlers import (
    COMMAND_VIEW_CONSUMER_ID,
    handle_case_closed,
    handle_case_created,
)
from app.command_view.models import CommandViewCaseMetric, ProcessedEvent
from app.command_view.repository import CommandViewRepository
from app.db.session import SessionLocal
from app.events.dispatcher import EventDispatcher
from app.events.processor import process_pending_events
from app.events.repository import OutboxRepository
from app.main import app
from app.models.application import Application
from app.models.country import Country
from app.models.outbox_event import OutboxEvent, OutboxStatus
from app.models.user import User
from scripts.process_outbox import build_event_dispatcher
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
        cmd_app = session.execute(
            select(Application).where(Application.key == "command-view")
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
            "care_app": care_app,
            "cmd_app": cmd_app,
            "alice": alice,
            "bob": bob,
            "carol": carol,
            "arnova": arnova,
            "belmara": belmara,
            "calduria": calduria,
        }


def test_end_to_end_case_created_and_closed_projection(context):
    """
    Core integration flow:
    1. Alice creates an Arnova case -> case.created.v1 is added to outbox.
    2. Process pending outbox events -> Command View metric open_count increments by 1.
    3. Alice closes the case -> case.closed.v1 is added to outbox.
    4. Process pending outbox events -> open_count decrements by 1, closed_count increments by 1.
    """
    alice = context["alice"]
    arnova = context["arnova"]
    dispatcher = build_event_dispatcher()

    # Drain any pre-existing pending events to ensure test isolation
    with SessionLocal() as session:
        process_pending_events(session=session, dispatcher=dispatcher)

    # 1. Baseline metric for Arnova
    with SessionLocal() as session:
        repo = CommandViewRepository(session)
        baseline = session.execute(
            select(CommandViewCaseMetric).where(
                CommandViewCaseMetric.country_id == arnova.id
            )
        ).scalar_one_or_none()
        initial_open = baseline.open_count if baseline else 0
        initial_closed = baseline.closed_count if baseline else 0

    # 2. Create Case via Care Companion API
    create_res = client.post(
        "/v1/cases",
        headers={"X-User-Id": str(alice.id)},
        json={"title": "Projection E2E Case", "country_id": str(arnova.id)},
    )
    assert create_res.status_code == 201
    case_id = create_res.json()["id"]

    # 3. Process Outbox
    with SessionLocal() as session:
        stats = process_pending_events(session=session, dispatcher=dispatcher)
        assert stats.processed >= 1

    # 4. Verify Command View metric: open_count + 1
    with SessionLocal() as session:
        metric = session.execute(
            select(CommandViewCaseMetric).where(
                CommandViewCaseMetric.country_id == arnova.id
            )
        ).scalar_one()
        assert metric.open_count == initial_open + 1
        assert metric.closed_count == initial_closed

    # 5. Close Case via Care Companion API
    close_res = client.post(
        f"/v1/cases/{case_id}/close",
        headers={"X-User-Id": str(alice.id)},
    )
    assert close_res.status_code == 200

    # 6. Process Outbox
    with SessionLocal() as session:
        stats = process_pending_events(session=session, dispatcher=dispatcher)
        assert stats.processed >= 1

    # 7. Verify Command View metric: open_count - 1, closed_count + 1
    with SessionLocal() as session:
        metric = session.execute(
            select(CommandViewCaseMetric).where(
                CommandViewCaseMetric.country_id == arnova.id
            )
        ).scalar_one()
        assert metric.open_count == initial_open
        assert metric.closed_count == initial_closed + 1


def test_closing_in_progress_case_projection(context):
    """
    Test in_progress -> closed transition:
    in_progress_count decrements, closed_count increments.
    """
    care_app = context["care_app"]
    belmara = context["belmara"]
    alice = context["alice"]
    dispatcher = build_event_dispatcher()

    # Create synthetic case.closed.v1 event with previous_status = "in_progress"
    with SessionLocal() as session:
        # Ensure a metric row exists with in_progress_count = 1
        repo = CommandViewRepository(session)
        metric = repo.get_or_create_metric_for_update(belmara.id)
        metric.in_progress_count += 1
        session.commit()

        initial_in_progress = metric.in_progress_count
        initial_closed = metric.closed_count

        event = OutboxEvent(
            application_id=care_app.id,
            event_type="case.closed.v1",
            aggregate_type="case",
            aggregate_id=uuid.uuid4(),
            country_id=belmara.id,
            payload={
                "case_id": str(uuid.uuid4()),
                "country_id": str(belmara.id),
                "previous_status": "in_progress",
                "status": "closed",
                "closed_by": str(alice.id),
                "closed_at": datetime.now(timezone.utc).isoformat(),
            },
            status=OutboxStatus.PENDING.value,
        )
        session.add(event)
        session.commit()

        # Process event
        stats = process_pending_events(session=session, dispatcher=dispatcher)
        assert stats.processed >= 1

    with SessionLocal() as session:
        refreshed = session.execute(
            select(CommandViewCaseMetric).where(
                CommandViewCaseMetric.country_id == belmara.id
            )
        ).scalar_one()
        assert refreshed.in_progress_count == initial_in_progress - 1
        assert refreshed.closed_count == initial_closed + 1


def test_idempotent_event_processing(context):
    """
    Verify delivering the same event twice does not mutate metrics twice.
    """
    care_app = context["care_app"]
    calduria = context["calduria"]
    alice = context["alice"]
    event_id = uuid.uuid4()
    case_id = uuid.uuid4()

    with SessionLocal() as session:
        repo = CommandViewRepository(session)
        baseline = session.execute(
            select(CommandViewCaseMetric).where(
                CommandViewCaseMetric.country_id == calduria.id
            )
        ).scalar_one_or_none()
        initial_open = baseline.open_count if baseline else 0

        event = OutboxEvent(
            id=event_id,
            application_id=care_app.id,
            event_type="case.created.v1",
            aggregate_type="case",
            aggregate_id=case_id,
            country_id=calduria.id,
            payload={
                "case_id": str(case_id),
                "country_id": str(calduria.id),
                "status": "open",
            },
        )

        # 1. First execution
        handle_case_created(session=session, event=event)
        session.commit()

    # Verify open_count incremented and processed_events has record
    with SessionLocal() as session:
        m1 = session.execute(
            select(CommandViewCaseMetric).where(
                CommandViewCaseMetric.country_id == calduria.id
            )
        ).scalar_one()
        assert m1.open_count == initial_open + 1

        pe_count = (
            session.execute(
                select(ProcessedEvent).where(
                    ProcessedEvent.event_id == event_id,
                    ProcessedEvent.consumer == COMMAND_VIEW_CONSUMER_ID,
                )
            )
            .scalars()
            .all()
        )
        assert len(pe_count) == 1

        # 2. Second execution with identical event
        handle_case_created(session=session, event=event)
        session.commit()

    # Verify open_count did NOT increment again
    with SessionLocal() as session:
        m2 = session.execute(
            select(CommandViewCaseMetric).where(
                CommandViewCaseMetric.country_id == calduria.id
            )
        ).scalar_one()
        assert m2.open_count == initial_open + 1


def test_handler_failure_rolls_back_and_marks_attempt(context, monkeypatch):
    """
    Simulate a failure inside the projection handler.
    Verify:
    - Projection mutation is rolled back.
    - processed_events record is NOT created.
    - Outbox event attempt_count is incremented.
    """
    care_app = context["care_app"]
    arnova = context["arnova"]
    failing_event_id = uuid.uuid4()

    with SessionLocal() as session:
        event = OutboxEvent(
            id=failing_event_id,
            application_id=care_app.id,
            event_type="case.created.v1",
            aggregate_type="case",
            aggregate_id=uuid.uuid4(),
            country_id=arnova.id,
            payload={
                "case_id": str(uuid.uuid4()),
                "country_id": str(arnova.id),
                "status": "open",
            },
            status=OutboxStatus.PENDING.value,
        )
        session.add(event)
        session.commit()

    dispatcher = EventDispatcher()

    def buggy_handler(*args, **kwargs):
        raise RuntimeError("Database deadlock or projection bug")

    dispatcher.register("case.created.v1", buggy_handler)

    with SessionLocal() as session:
        stats = process_pending_events(
            session=session, dispatcher=dispatcher, batch_size=1
        )
        assert stats.failed == 1

    # Verify outbox event attempt count incremented and not marked processed
    with SessionLocal() as session:
        evt = session.get(OutboxEvent, failing_event_id)
        assert evt.attempt_count == 1
        assert evt.status == OutboxStatus.PENDING.value

        pe = session.get(ProcessedEvent, (failing_event_id, COMMAND_VIEW_CONSUMER_ID))
        assert pe is None


def test_command_view_api_rbac_and_country_scoping(context):
    """
    GET /v1/command-view/case-metrics
    - Alice has 'case-metrics:read' in Command View and country scope for Arnova + Belmara.
    - Bob has NO role in Command View -> 403 Forbidden.
    - Carol has NO role in Command View -> 403 Forbidden.
    - Alice's query returns ONLY metrics for Arnova and Belmara (Calduria excluded in SQL).
    """
    alice = context["alice"]
    bob = context["bob"]
    carol = context["carol"]
    arnova = context["arnova"]
    belmara = context["belmara"]
    calduria = context["calduria"]

    # 1. Bob lacks role/permission in Command View
    res_bob = client.get(
        "/v1/command-view/case-metrics",
        headers={"X-User-Id": str(bob.id)},
    )
    assert res_bob.status_code == 403
    assert "case-metrics:read" in res_bob.json()["detail"]

    # 2. Carol lacks role/permission in Command View
    res_carol = client.get(
        "/v1/command-view/case-metrics",
        headers={"X-User-Id": str(carol.id)},
    )
    assert res_carol.status_code == 403

    # 3. Alice has role and scope for Arnova + Belmara
    res_alice = client.get(
        "/v1/command-view/case-metrics",
        headers={"X-User-Id": str(alice.id)},
    )
    assert res_alice.status_code == 200
    metrics = res_alice.json()
    country_ids = {m["country_id"] for m in metrics}

    # Must contain Arnova and/or Belmara if present, and NEVER Calduria
    assert str(calduria.id) not in country_ids
    for m in metrics:
        assert m["country_id"] in [str(arnova.id), str(belmara.id)]


def test_outbox_processor_deterministic_order():
    """
    Verify outbox repository retrieves pending events ordered strictly by created_at ASC, id ASC.
    """
    with SessionLocal() as session:
        repo = OutboxRepository(session)
        events = repo.list_pending(limit=20)
        for i in range(len(events) - 1):
            assert events[i].created_at <= events[i + 1].created_at
