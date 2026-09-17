"""Domain events (ticket/created, ticket/status_changed, ...).

Services queue events on the session; they are published only after the transaction
commits, so a rolled-back change never triggers emails or AI work.

Publishing hands them to Inngest, which runs the AI agent, assignment and emails.
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PENDING_KEY = "pending_events"


@dataclass(frozen=True)
class Event:
    name: str
    data: dict[str, Any]


def queue_event(session: AsyncSession, name: str, data: dict[str, Any]) -> None:
    session.info.setdefault(_PENDING_KEY, []).append(Event(name, data))


async def publish(events: list[Event]) -> None:
    import inngest

    from app.inngest.client import inngest_client

    for event in events:
        logger.info("event %s %s", event.name, event.data)
    await inngest_client.send([inngest.Event(name=e.name, data=e.data) for e in events])


async def commit_and_publish(session: AsyncSession) -> None:
    await session.commit()
    events: list[Event] = session.info.pop(_PENDING_KEY, [])
    if events:
        try:
            await publish(events)
        except Exception:
            # The data change is already committed; don't fail the request over it.
            logger.exception("Failed to publish %d event(s)", len(events))


def discard_events(session: AsyncSession) -> None:
    session.info.pop(_PENDING_KEY, None)
