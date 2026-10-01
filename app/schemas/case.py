import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.models.case import CaseStatus


class CaseCreate(BaseModel):
    title: str = Field(
        ..., max_length=255, min_length=1, description="Title of the case"
    )
    description: str | None = Field(default=None, description="Detailed description")
    country_id: uuid.UUID = Field(
        ..., description="Geographic country scope for this case"
    )
    status: CaseStatus = Field(
        default=CaseStatus.OPEN, description="Initial case status"
    )


class CaseUpdate(BaseModel):
    title: str | None = Field(
        default=None, max_length=255, min_length=1, description="Updated case title"
    )
    description: str | None = Field(
        default=None, description="Updated case description"
    )
    expected_version: int | None = Field(
        default=None, description="Expected version for optimistic concurrency control"
    )


class CaseAssignRequest(BaseModel):
    assigned_to: uuid.UUID = Field(
        ..., description="UUID of the user to assign this case to"
    )
    expected_version: int | None = Field(
        default=None, description="Expected version for optimistic concurrency control"
    )


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    country_id: uuid.UUID
    owner_app_id: uuid.UUID
    title: str
    description: str | None
    status: CaseStatus
    assigned_to: uuid.UUID | None = None
    closed_at: datetime | None = None
    closed_by: uuid.UUID | None = None
    created_at: datetime
    created_by: uuid.UUID
    updated_at: datetime
    updated_by: uuid.UUID | None
    version: int
