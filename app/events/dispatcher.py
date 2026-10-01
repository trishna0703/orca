from collections.abc import Callable
import logging
from typing import Any, Protocol
from sqlalchemy.orm import Session

from app.models.outbox_event import OutboxEvent

logger = logging.getLogger(__name__)


class EventHandler(Protocol):
    def __call__(
        self,
        *,
        session: Session,
        event: OutboxEvent,
    ) -> None: ...


class EventDispatcher:
    """
    Platform-level generic event dispatcher.
    Decoupled from specific consumers and entities.
    Registers handlers by event_type and executes all registered handlers for an event.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}

    def register(self, event_type: str, handler: EventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def get_handlers(self, event_type: str) -> list[EventHandler]:
        return self._handlers.get(event_type, [])

    def dispatch(self, *, session: Session, event: OutboxEvent) -> bool:
        """
        Dispatches an event to all registered handlers for event.event_type.
        Returns True if at least one handler executed, False if skipped/unhandled.
        If a registered handler raises an exception, the exception propagates.
        """
        handlers = self.get_handlers(event.event_type)
        if not handlers:
            logger.debug(
                "No registered handlers for event_type '%s' (event_id=%s). Skipped.",
                event.event_type,
                event.id,
            )
            return False

        for handler in handlers:
            handler(session=session, event=event)

        return True
