from datetime import datetime
from typing import Literal
import uuid
from pydantic import BaseModel, ConfigDict, Field


class CaseCreatedV1Payload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: uuid.UUID
    country_id: uuid.UUID
    title: str | None = None
    status: Literal["open", "in_progress", "closed"] = "open"
    created_by: uuid.UUID | None = None
    created_at: datetime | None = None


class CaseClosedV1Payload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    case_id: uuid.UUID
    country_id: uuid.UUID
    previous_status: Literal["open", "in_progress", "closed"]
    status: Literal["closed"]
    closed_by: uuid.UUID | None = None
    closed_at: datetime | None = None
    version: int | None = None
