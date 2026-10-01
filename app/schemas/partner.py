from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.partner import PartnerStatus


class PartnerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    partner_type: str = Field(..., min_length=1, max_length=100)
    contact_email: str | None = Field(default=None, max_length=255)
    country_id: uuid.UUID
    status: PartnerStatus = Field(default=PartnerStatus.ACTIVE)


class PartnerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    partner_type: str | None = Field(default=None, min_length=1, max_length=100)
    contact_email: str | None = Field(default=None, max_length=255)
    status: PartnerStatus | None = None
    expected_version: int | None = None


class PartnerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    country_id: uuid.UUID
    owner_app_id: uuid.UUID
    name: str
    partner_type: str
    contact_email: str | None
    status: PartnerStatus
    created_at: datetime
    created_by: uuid.UUID
    updated_at: datetime
    updated_by: uuid.UUID | None
    version: int
