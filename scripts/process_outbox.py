"""
CLI entry point to process pending Outbox events and project to Command View.
Usage:
    uv run python -m scripts.process_outbox
"""

import sys
from app.command_view.handlers import handle_case_closed, handle_case_created
from app.db.session import SessionLocal
from app.events.dispatcher import EventDispatcher
from app.events.processor import process_pending_events


def build_event_dispatcher() -> EventDispatcher:
    dispatcher = EventDispatcher()
    dispatcher.register("case.created.v1", handle_case_created)
    dispatcher.register("case.closed.v1", handle_case_closed)
    return dispatcher


def main() -> None:
    print("Starting Outbox Event Processor...")
    dispatcher = build_event_dispatcher()

    with SessionLocal() as session:
        stats = process_pending_events(
            session=session,
            dispatcher=dispatcher,
            batch_size=100,
            for_update=True,
            skip_locked=True,
        )

    print(
        f"Processing completed: processed={stats.processed} failed={stats.failed} skipped={stats.skipped}"
    )


if __name__ == "__main__":
    main()
