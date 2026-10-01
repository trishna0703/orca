import enum
import uuid
from datetime import date, datetime, time
from typing import Any
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase


def to_json_serializable(value: Any) -> Any:
    """
    Recursively converts Python/SQLAlchemy types into JSON-serializable primitives.
    Handles UUIDs, datetimes, dates, times, Enums, sets, dicts, lists, and primitives.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, (list, tuple, set)):
        return [to_json_serializable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): to_json_serializable(v) for k, v in value.items()}
    return value


def serialize_entity(entity: Any) -> dict[str, Any]:
    """
    Generic serializer for any SQLAlchemy declarative entity.
    Extracts all mapped column values without internal state (e.g. `_sa_instance_state`)
    and converts all values (UUIDs, datetimes, enums) to clean JSON-serializable formats.
    """
    if entity is None:
        return {}

    # If it's a dict already, sanitize it
    if isinstance(entity, dict):
        return {
            str(k): to_json_serializable(v)
            for k, v in entity.items()
            if not str(k).startswith("_")
        }

    # Inspect SQLAlchemy model instance
    inspection = sa_inspect(entity)
    data: dict[str, Any] = {}
    for col in inspection.mapper.column_attrs:
        raw_val = getattr(entity, col.key)
        data[col.key] = to_json_serializable(raw_val)

    return data
