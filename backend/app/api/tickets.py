"""Ticket endpoints shared by all roles. Access is checked per ticket in the service."""

import uuid
from typing import Literal

from fastapi import APIRouter, status
from sqlalchemy import select

from app.core.deps import CurrentUser, FiltersDep, SessionDep
from app.core.pagination import PageDep, paginate
from app.events import commit_and_publish, queue_event
from app.models import ACTIVE_TICKET_STATUSES, Ticket, TicketStatus
from app.schemas.common import Page
from app.schemas.tickets import (
    CommentCreate,
    CommentOut,
    StatusUpdate,
    TicketCreate,
    TicketDetailOut,
    TicketOut,
)
from app.services import tickets as ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ticket(body: TicketCreate, user: CurrentUser, session: SessionDep) -> TicketOut:
    """Saves the ticket and emits `ticket/created`; AI analysis and assignment run later."""
    ticket = ticket_service.create_ticket(session, user, body.title, body.description)
    await session.flush()
    queue_event(
        session,
        "ticket/created",
        {"ticket_id": str(ticket.id), "created_by_id": str(user.id)},
    )
    await commit_and_publish(session)
    ticket = await ticket_service.get_ticket_for(session, ticket.id, user)
    return ticket_service.ticket_out(ticket, user)


@router.get("/mine")
async def my_tickets(
    user: CurrentUser,
    session: SessionDep,
    page: PageDep,
    filters: FiltersDep,
    scope: Literal["open", "history", "all"] = "open",
) -> Page[TicketOut]:
    """User dashboard. `open` = Your Tickets (not closed), `history` = closed tickets."""
    stmt = ticket_service.with_people(select(Ticket).where(Ticket.created_by_id == user.id))
    if scope == "open":
        stmt = stmt.where(Ticket.status.in_(ACTIVE_TICKET_STATUSES))
    elif scope == "history":
        stmt = stmt.where(Ticket.status == TicketStatus.CLOSED)
    stmt = ticket_service.apply_filters(stmt, filters).order_by(Ticket.created_at.desc())
    return await paginate(session, stmt, page, lambda t: ticket_service.ticket_out(t, user))


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> TicketDetailOut:
    ticket = await ticket_service.get_ticket_for(session, ticket_id, user, with_comments=True)
    return ticket_service.ticket_detail_out(ticket, user)


@router.post("/{ticket_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment(
    ticket_id: uuid.UUID, body: CommentCreate, user: CurrentUser, session: SessionDep
) -> CommentOut:
    ticket = await ticket_service.get_ticket_for(session, ticket_id, user)
    comment = await ticket_service.add_comment(session, ticket, user, body.body)
    await commit_and_publish(session)
    comment.author = user
    return CommentOut.model_validate(comment)


@router.patch("/{ticket_id}/status")
async def update_status(
    ticket_id: uuid.UUID, body: StatusUpdate, user: CurrentUser, session: SessionDep
) -> TicketOut:
    """Assignee (or admin): assigned → in_progress → resolved.
    Ticket owner (or admin): resolved → closed."""
    ticket = await ticket_service.get_ticket_for(session, ticket_id, user, for_update=True)
    ticket_service.change_status_by_user(session, ticket, body.status, user)
    await commit_and_publish(session)
    return ticket_service.ticket_out(ticket, user)
