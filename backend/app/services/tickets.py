"""Ticket rules: who can see and change a ticket, and which status moves are allowed.

Every status change goes through `transition()`, which emits `ticket/status_changed`.
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import utcnow
from app.events import queue_event
from app.models import Ticket, TicketComment, TicketStatus, User, UserRole
from app.schemas.tickets import CommentOut, TicketDetailOut, TicketFilters, TicketOut

S = TicketStatus

ALLOWED_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    S.OPEN: frozenset({S.ASSIGNED, S.PENDING_REVIEW}),
    S.PENDING_REVIEW: frozenset({S.ASSIGNED}),
    # -> pending_review only when the assignee is removed or demoted (release_tickets).
    S.ASSIGNED: frozenset({S.IN_PROGRESS, S.PENDING_REVIEW}),
    S.IN_PROGRESS: frozenset({S.RESOLVED, S.PENDING_REVIEW}),
    S.RESOLVED: frozenset({S.CLOSED}),
    S.CLOSED: frozenset(),
}

ACTIVE_ASSIGNMENT = (S.ASSIGNED, S.IN_PROGRESS)
SOLVED = (S.RESOLVED, S.CLOSED)
STAFF_ROLES = (UserRole.MODERATOR, UserRole.ADMIN)


# --- Loading and visibility ---


def with_people(stmt: Select[Any]) -> Select[Any]:
    return stmt.options(selectinload(Ticket.created_by), selectinload(Ticket.assignee))


def can_view(ticket: Ticket, user: User) -> bool:
    return (
        user.role == UserRole.ADMIN
        or ticket.created_by_id == user.id
        or (user.role == UserRole.MODERATOR and ticket.assignee_id == user.id)
    )


def sees_ai_notes(ticket: Ticket, user: User) -> bool:
    return user.role == UserRole.ADMIN or (
        user.role == UserRole.MODERATOR and ticket.assignee_id == user.id
    )


def ticket_out(ticket: Ticket, viewer: User) -> TicketOut:
    out = TicketOut.model_validate(ticket)
    if not sees_ai_notes(ticket, viewer):
        out.ai_notes = None
        out.ai_model_used = None
    return out


def ticket_detail_out(ticket: Ticket, viewer: User) -> TicketDetailOut:
    base = ticket_out(ticket, viewer)
    return TicketDetailOut(
        **base.model_dump(),
        comments=[CommentOut.model_validate(c) for c in ticket.comments],
    )


async def get_ticket_for(
    session: AsyncSession,
    ticket_id: uuid.UUID,
    user: User,
    *,
    with_comments: bool = False,
    for_update: bool = False,
) -> Ticket:
    """Load a ticket the user may see. Tickets they can't see are reported as 404."""
    stmt = with_people(select(Ticket).where(Ticket.id == ticket_id))
    if with_comments:
        stmt = stmt.options(selectinload(Ticket.comments).selectinload(TicketComment.author))
    if for_update:
        stmt = stmt.with_for_update(of=Ticket).execution_options(populate_existing=True)
    ticket = await session.scalar(stmt)
    if ticket is None or not can_view(ticket, user):
        raise NotFoundError("Ticket not found")
    return ticket


def apply_filters(stmt: Select[Any], filters: TicketFilters) -> Select[Any]:
    if filters.q:
        stmt = stmt.where(Ticket.title.ilike(f"%{escape_like(filters.q.strip())}%", escape="\\"))
    if filters.status:
        stmt = stmt.where(Ticket.status.in_(filters.status))
    if filters.date_from:
        stmt = stmt.where(Ticket.created_at >= filters.date_from)
    if filters.date_to:
        stmt = stmt.where(Ticket.created_at < filters.date_to + timedelta(days=1))
    return stmt


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --- Creating and commenting ---


def create_ticket(session: AsyncSession, user: User, title: str, description: str) -> Ticket:
    ticket = Ticket(
        title=title,
        description=description,
        status=S.OPEN,
        created_by_id=user.id,
    )
    session.add(ticket)
    return ticket


async def add_comment(
    session: AsyncSession, ticket: Ticket, author: User, body: str
) -> TicketComment:
    is_creator = ticket.created_by_id == author.id
    is_staff = author.role == UserRole.ADMIN or ticket.assignee_id == author.id

    if not (is_creator or is_staff):
        raise ForbiddenError("You can't comment on this ticket")
    if ticket.status == S.CLOSED and not is_staff:
        raise ConflictError("This ticket is closed")

    comment = TicketComment(ticket_id=ticket.id, author_id=author.id, body=body)
    session.add(comment)
    await session.flush()

    if not is_creator and ticket.status in SOLVED:
        queue_event(
            session,
            "ticket/comment_after_resolution",
            {
                "ticket_id": str(ticket.id),
                "comment_id": str(comment.id),
                "author_id": str(author.id),
            },
        )
    return comment


# --- Status ---


def transition(
    session: AsyncSession,
    ticket: Ticket,
    new_status: TicketStatus,
    actor: User | None,
    *,
    reason: str | None = None,
) -> None:
    """The only place a ticket's status changes. `actor` is None for system changes."""
    old = ticket.status
    if new_status not in ALLOWED_TRANSITIONS[old]:
        raise ConflictError(
            f"Can't move a ticket from {old.value} to {new_status.value}",
            details={"from": old.value, "to": new_status.value},
        )

    now = utcnow()
    ticket.status = new_status
    if new_status == S.ASSIGNED:
        ticket.assigned_at = now
    elif new_status == S.RESOLVED:
        ticket.resolved_at = now
    elif new_status == S.CLOSED:
        ticket.closed_at = now

    queue_event(
        session,
        "ticket/status_changed",
        {
            "ticket_id": str(ticket.id),
            "from": old.value,
            "to": new_status.value,
            "actor_id": str(actor.id) if actor else None,
            "reason": reason,
        },
    )


def change_status_by_user(
    session: AsyncSession, ticket: Ticket, new_status: TicketStatus, actor: User
) -> None:
    """Status moves people make by hand (assignment has its own endpoint)."""
    is_admin = actor.role == UserRole.ADMIN
    is_assignee = ticket.assignee_id == actor.id and actor.role in STAFF_ROLES
    is_creator = ticket.created_by_id == actor.id

    if new_status in (S.IN_PROGRESS, S.RESOLVED):
        allowed = is_admin or is_assignee
    elif new_status == S.CLOSED:
        allowed = is_admin or is_creator
    else:
        allowed = False

    if not allowed:
        raise ForbiddenError("You can't change this ticket to that status")
    transition(session, ticket, new_status, actor)


# --- Assignment ---


async def assign_ticket(
    session: AsyncSession,
    ticket: Ticket,
    moderator: User,
    actor: User | None,
    *,
    source: str = "admin",
) -> None:
    """Assign (or reassign) a ticket. Used by admins now and by the AI agent in Phase 4."""
    if moderator.role not in STAFF_ROLES or not moderator.is_active:
        raise ConflictError("Tickets can only be assigned to an active moderator or admin")
    if ticket.status in SOLVED:
        raise ConflictError(f"Can't assign a {ticket.status.value} ticket")

    previous = ticket.assignee_id
    ticket.assignee_id = moderator.id
    ticket.assignee = moderator

    if ticket.status in (S.OPEN, S.PENDING_REVIEW):
        transition(session, ticket, S.ASSIGNED, actor, reason=f"assigned by {source}")
    else:
        ticket.assigned_at = utcnow()

    queue_event(
        session,
        "ticket/assigned",
        {
            "ticket_id": str(ticket.id),
            "moderator_id": str(moderator.id),
            "previous_assignee_id": str(previous) if previous else None,
            "actor_id": str(actor.id) if actor else None,
            "source": source,
        },
    )


async def release_tickets(session: AsyncSession, user: User, actor: User) -> int:
    """When a moderator is demoted or removed, send their open work back for review."""
    tickets = await session.scalars(
        select(Ticket)
        .where(Ticket.assignee_id == user.id, Ticket.status.in_(ACTIVE_ASSIGNMENT))
        .with_for_update()
    )
    count = 0
    for ticket in tickets:
        ticket.assignee_id = None
        transition(session, ticket, S.PENDING_REVIEW, actor, reason="assignee removed")
        count += 1
    return count
