import enum
import uuid
from datetime import datetime, timezone
import pytest

from app.audit.serializers import serialize_entity, to_json_serializable
from app.models.case import Case, CaseStatus


class SampleEnum(enum.Enum):
    ALPHA = "alpha"
    BETA = "beta"


def test_to_json_serializable_primitives():
    assert to_json_serializable("hello") == "hello"
    assert to_json_serializable(123) == 123
    assert to_json_serializable(12.34) == 12.34
    assert to_json_serializable(True) is True
    assert to_json_serializable(None) is None


def test_to_json_serializable_uuid_and_datetime():
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    assert to_json_serializable(uid) == str(uid)
    assert to_json_serializable(now) == now.isoformat()


def test_to_json_serializable_enum():
    assert to_json_serializable(SampleEnum.ALPHA) == "alpha"
    assert to_json_serializable(CaseStatus.IN_PROGRESS) == "in_progress"


def test_to_json_serializable_collections():
    uid = uuid.uuid4()
    data = {"key": uid, "list": [SampleEnum.BETA, 456]}
    serialized = to_json_serializable(data)
    assert serialized == {"key": str(uid), "list": ["beta", 456]}


def test_serialize_entity_excludes_internal_state():
    case = Case(
        id=uuid.uuid4(),
        title="Audit Test Case",
        description="Testing serialization",
        status=CaseStatus.OPEN,
        country_id=uuid.uuid4(),
        owner_app_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        version=1,
    )
    result = serialize_entity(case)

    # Must contain entity columns
    assert result["title"] == "Audit Test Case"
    assert result["description"] == "Testing serialization"
    assert result["status"] == "open"
    assert result["id"] == str(case.id)
    assert result["country_id"] == str(case.country_id)
    assert result["owner_app_id"] == str(case.owner_app_id)
    assert result["created_by"] == str(case.created_by)
    assert result["version"] == 1

    # Must NOT contain internal SQLAlchemy state
    assert "_sa_instance_state" not in result
    for k in result:
        assert not k.startswith("_")
