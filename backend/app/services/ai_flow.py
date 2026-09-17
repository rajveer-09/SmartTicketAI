"""The steps the AI agent runs for a new ticket.

Each function opens its own session, does one thing and commits, so Inngest can retry
any single step without repeating the others.
"""

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai import gemini, prompts
from app.core.database import get_sessionmaker
from app.events import commit_and_publish
from app.models import Ticket, TicketPriority, TicketStatus, User
from app.services import matching
from app.services import tickets as ticket_service
from app.services.notifications import notify_admins_pending_review

logger = logging.getLogger(__name__)

MAX_SKILLS = 5
SKILL_MAX_LENGTH = 64


def session_scope():
    return get_sessionmaker()()


async def load_ticket(session: AsyncSession, ticket_id: uuid.UUID) -> Ticket | None:
    return await session.scalar(
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(selectinload(Ticket.created_by), selectinload(Ticket.assignee))
    )


def clean_skills(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    skills: list[str] = []
    for item in raw:
        skill = matching.normalise(str(item))[:SKILL_MAX_LENGTH]
        if skill and skill not in skills:
            skills.append(skill)
    return skills[:MAX_SKILLS]


def clean_priority(raw: Any) -> TicketPriority | None:
    try:
        return TicketPriority(str(raw).strip().lower())
    except ValueError:
        return None


async def analyze(ticket_id: str) -> dict[str, Any]:
    """Ask Gemini for category, priority and required skills, and save them."""
    async with session_scope() as session:
        ticket = await load_ticket(session, uuid.UUID(ticket_id))
        if ticket is None:
            return {"ok": False, "reason": "ticket_not_found"}
        if ticket.status != TicketStatus.OPEN:
            return {"ok": False, "reason": "already_processed"}

        try:
            result = await gemini.generate(
                session,
                prompts.analysis_prompt(ticket.title, ticket.description),
                system=prompts.ANALYSIS_SYSTEM,
                schema=prompts.ANALYSIS_SCHEMA,
            )
            data = result.json()
        except gemini.AIUnavailableError as exc:
            logger.warning("AI analysis unavailable for ticket %s: %s", ticket_id, exc.attempts)
            return {"ok": False, "reason": "ai_unavailable"}
        except (ValueError, TypeError) as exc:  # unparsable JSON
            logger.warning("AI returned unusable analysis for %s: %s", ticket_id, exc)
            return {"ok": False, "reason": "bad_response"}

        ticket.category = str(data.get("category", ""))[:64] or None
        ticket.priority = clean_priority(data.get("priority"))
        ticket.required_skills = clean_skills(data.get("required_skills"))
        ticket.ai_model_used = result.model
        await session.commit()

        return {
            "ok": True,
            "category": ticket.category,
            "priority": ticket.priority.value if ticket.priority else None,
            "required_skills": ticket.required_skills,
            "model": result.model,
        }


async def write_notes(ticket_id: str) -> dict[str, Any]:
    """Generate the helpful notes the moderator sees."""
    async with session_scope() as session:
        ticket = await load_ticket(session, uuid.UUID(ticket_id))
        if ticket is None:
            return {"ok": False, "reason": "ticket_not_found"}
        if ticket.ai_notes:
            return {"ok": True, "skipped": True}

        try:
            result = await gemini.generate(
                session,
                prompts.notes_prompt(
                    ticket.title,
                    ticket.description,
                    ticket.category or "unknown",
                    ticket.priority.value if ticket.priority else "unknown",
                ),
                system=prompts.NOTES_SYSTEM,
                max_output_tokens=1024,
            )
        except gemini.AIUnavailableError as exc:
            logger.warning("AI notes unavailable for ticket %s: %s", ticket_id, exc.attempts)
            return {"ok": False, "reason": "ai_unavailable"}

        ticket.ai_notes = result.text
        await session.commit()
        return {"ok": True, "model": result.model}


async def assign(ticket_id: str) -> dict[str, Any]:
    """Assign the best-fit moderator, or fall back to Pending Review."""
    async with session_scope() as session:
        ticket = await load_ticket(session, uuid.UUID(ticket_id))
        if ticket is None:
            return {"ok": False, "reason": "ticket_not_found"}
        if ticket.status != TicketStatus.OPEN:
            return {"ok": False, "reason": "already_processed"}

        best = await matching.pick_moderator(session, list(ticket.required_skills or []))
        if best is None:
            return {"ok": False, "reason": "no_moderator"}

        await ticket_service.assign_ticket(session, ticket, best.user, None, source="ai")
        await commit_and_publish(session)
        return {
            "ok": True,
            "moderator_id": str(best.user.id),
            "matched_skills": best.matched,
            "workload": best.workload,
        }


async def mark_pending_review(ticket_id: str, reason: str, event_id: str) -> dict[str, Any]:
    """Nothing could be decided automatically: park the ticket and email the admins."""
    async with session_scope() as session:
        ticket = await load_ticket(session, uuid.UUID(ticket_id))
        if ticket is None:
            return {"ok": False, "reason": "ticket_not_found"}

        if ticket.status == TicketStatus.OPEN:
            ticket_service.transition(
                session, ticket, TicketStatus.PENDING_REVIEW, None, reason=reason
            )
            await commit_and_publish(session)

        sent = await notify_admins_pending_review(session, event_id, ticket, reason)
        return {"ok": True, "reason": reason, "admins_notified": sent}


async def load_user(session: AsyncSession, user_id: str) -> User | None:
    return await session.get(User, uuid.UUID(user_id))
