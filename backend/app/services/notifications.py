"""Email sending for background jobs, recorded so a retry never sends twice.

Every send is keyed `{event_id}:{template}:{recipient}` in `sent_emails`.
"""

import html
import logging
import uuid
from typing import Any

import markdown
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import SentEmail, Ticket, TicketStatus, User, UserRole
from app.services.email import send_email

logger = logging.getLogger(__name__)

# Chip colours per status, matching the app's badges.
STATUS_COLOURS: dict[TicketStatus, tuple[str, str]] = {
    TicketStatus.OPEN: ("#eef1f7", "#505b74"),
    TicketStatus.PENDING_REVIEW: ("#fef3c7", "#a16207"),
    TicketStatus.ASSIGNED: ("#e8edfd", "#3b55d9"),
    TicketStatus.IN_PROGRESS: ("#ede9fe", "#6d28d9"),
    TicketStatus.RESOLVED: ("#d1fae5", "#047857"),
    TicketStatus.CLOSED: ("#eef1f7", "#7b8794"),
}

PRIORITY_COLOURS = {
    "low": ("#eef1f7", "#505b74"),
    "medium": ("#e8edfd", "#3b55d9"),
    "high": ("#ffedd5", "#c2410c"),
    "urgent": ("#fee2e2", "#b91c1c"),
}

STATUS_HEADLINES = {
    TicketStatus.PENDING_REVIEW: "We're finding the right person for your ticket",
    TicketStatus.ASSIGNED: "Your ticket has been assigned",
    TicketStatus.IN_PROGRESS: "Someone is working on your ticket",
    TicketStatus.RESOLVED: "Your ticket has been resolved",
    TicketStatus.CLOSED: "Your ticket is closed",
}


def render_notes(notes: str | None) -> str | None:
    """AI notes are Markdown. Escape first (the text is model output), then render,
    so the email shows headings and lists instead of raw '###'."""
    if not notes:
        return None
    return markdown.markdown(html.escape(notes), extensions=["nl2br"])


def initials(name: str) -> str:
    parts = [p for p in (w.strip() for w in name.split()) if p and p[0].isalpha()]
    return "".join(p[0].upper() for p in parts[:2]) or "?"


def ticket_url(ticket_id: uuid.UUID) -> str:
    return f"{settings.frontend_url}/tickets/{ticket_id}"


async def send_once(
    session: AsyncSession,
    *,
    key: str,
    to: str,
    subject: str,
    template: str,
    context: dict[str, Any],
) -> bool:
    """Send unless this exact email was already sent. Returns True if it went out."""
    already = await session.scalar(select(SentEmail.id).where(SentEmail.idempotency_key == key))
    if already:
        logger.info("Skipping duplicate email %s", key)
        return False

    await send_email(to, subject, template, context)

    session.add(SentEmail(idempotency_key=key, recipient=to, template=template))
    try:
        await session.commit()
    except IntegrityError:  # another attempt recorded it at the same moment
        await session.rollback()
    return True


async def notify_assignment(session: AsyncSession, event_id: str, ticket: Ticket) -> bool:
    """Tell the moderator they have a new ticket, including the AI notes."""
    moderator = ticket.assignee
    if moderator is None:
        return False
    priority_bg, priority_fg = PRIORITY_COLOURS.get(
        ticket.priority.value if ticket.priority else "", ("#eef1f7", "#505b74")
    )
    return await send_once(
        session,
        key=f"{event_id}:ticket_assigned:{moderator.email}",
        to=moderator.email,
        subject=f"New ticket assigned: {ticket.title}",
        template="ticket_assigned.html",
        context={
            "moderator_name": moderator.full_name,
            "title": ticket.title,
            "description": ticket.description,
            "category": ticket.category,
            "priority": ticket.priority.value if ticket.priority else None,
            "priority_bg": priority_bg,
            "priority_fg": priority_fg,
            "skills": ticket.required_skills,
            "notes_html": render_notes(ticket.ai_notes),
            "url": ticket_url(ticket.id),
            "preheader": f"New ticket for you: {ticket.title}",
        },
    )


async def notify_status_change(
    session: AsyncSession, event_id: str, ticket: Ticket, new_status: TicketStatus
) -> bool:
    status_bg, status_fg = STATUS_COLOURS.get(new_status, ("#eef1f7", "#505b74"))
    return await send_once(
        session,
        key=f"{event_id}:status_update:{ticket.created_by.email}",
        to=ticket.created_by.email,
        subject=f"Update on your ticket: {ticket.title}",
        template="status_update.html",
        context={
            "user_name": ticket.created_by.full_name,
            "title": ticket.title,
            "status": new_status.value.replace("_", " "),
            "status_bg": status_bg,
            "status_fg": status_fg,
            "headline": STATUS_HEADLINES.get(new_status, "Your ticket was updated"),
            "assignee_name": ticket.assignee.full_name if ticket.assignee else None,
            "url": ticket_url(ticket.id),
            "preheader": f"{ticket.title} is now {new_status.value.replace(chr(95), chr(32))}",
        },
    )


async def notify_new_message(
    session: AsyncSession, event_id: str, ticket: Ticket, author: User, body: str
) -> bool:
    return await send_once(
        session,
        key=f"{event_id}:new_message:{ticket.created_by.email}",
        to=ticket.created_by.email,
        subject=f"New message on your ticket: {ticket.title}",
        template="new_message.html",
        context={
            "user_name": ticket.created_by.full_name,
            "author_name": author.full_name,
            "author_initials": initials(author.full_name),
            "title": ticket.title,
            "message": body,
            "preheader": body[:110],
            "url": ticket_url(ticket.id),
        },
    )


async def notify_admins_pending_review(
    session: AsyncSession, event_id: str, ticket: Ticket, reason: str
) -> int:
    """No moderator could be chosen automatically: ask the admins to assign by hand."""
    admins = (
        await session.scalars(
            select(User).where(User.role == UserRole.ADMIN, User.is_active.is_(True))
        )
    ).all()
    sent = 0
    for admin in admins:
        sent += await send_once(
            session,
            key=f"{event_id}:pending_review:{admin.email}",
            to=admin.email,
            subject=f"Ticket needs manual assignment: {ticket.title}",
            template="pending_review.html",
            context={
                "admin_name": admin.full_name,
                "title": ticket.title,
                "description": ticket.description,
                "reason": reason,
                "url": ticket_url(ticket.id),
                "preheader": f"{ticket.title} is waiting in Pending review",
            },
        )
    return sent


async def notify_welcome(session: AsyncSession, event_id: str, user: User) -> bool:
    return await send_once(
        session,
        key=f"{event_id}:welcome:{user.email}",
        to=user.email,
        subject=f"Welcome to {settings.mail_from_name}",
        template="welcome.html",
        context={
            "full_name": user.full_name,
            "preheader": "Your account is ready — here's how tickets work.",
        },
    )
