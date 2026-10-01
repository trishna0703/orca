from collections.abc import Sequence
import uuid
from sqlalchemy.orm import Session

from app.command_view.models import CommandViewCaseMetric
from app.command_view.repository import CommandViewRepository


class CommandViewService:
    """
    Read service for Command View metrics, enforcing geographic scope in SQL.
    Does NOT query the domain `cases` table.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CommandViewRepository(session)

    def get_case_metrics(
        self,
        *,
        allowed_country_ids: set[uuid.UUID] | Sequence[uuid.UUID],
    ) -> list[CommandViewCaseMetric]:
        return self.repository.list_scoped(allowed_country_ids=allowed_country_ids)
