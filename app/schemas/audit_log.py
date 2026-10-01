import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    application_id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    country_id: uuid.UUID | None
    before_data: dict[str, Any] | None
    after_data: dict[str, Any] | None
    metadata_: dict[str, Any] | None = None
    request_id: str | None
    created_at: datetime
