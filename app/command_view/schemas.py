from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict


class CaseMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    country_id: uuid.UUID
    open_count: int
    in_progress_count: int
    closed_count: int
    updated_at: datetime
