"""Pick the best moderator for a ticket: most matching skills first, then lowest workload."""

from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Ticket, TicketStatus, User, UserRole

ACTIVE = (TicketStatus.ASSIGNED, TicketStatus.IN_PROGRESS)


@dataclass
class Candidate:
    user: User
    matched: list[str]
    workload: int

    @property
    def score(self) -> tuple[int, int, str]:
        # Most matches first, then the least busy, then a stable name order.
        return (-len(self.matched), self.workload, self.user.full_name.lower())


def normalise(skill: str) -> str:
    return " ".join(skill.strip().lower().split())


def overlap(required: list[str], owned: set[str]) -> list[str]:
    """A required skill matches if it equals an owned skill, or either contains the other
    ('vpn' matches 'vpn troubleshooting')."""
    matched = []
    for raw in required:
        want = normalise(raw)
        if not want:
            continue
        if any(want == have or want in have or have in want for have in owned):
            matched.append(want)
    return matched


async def candidates(session: AsyncSession, required_skills: list[str]) -> list[Candidate]:
    rows = (
        await session.execute(
            select(
                User,
                func.count(case((Ticket.status.in_(ACTIVE), Ticket.id))).label("workload"),
            )
            .outerjoin(Ticket, Ticket.assignee_id == User.id)
            .where(User.role == UserRole.MODERATOR, User.is_active.is_(True))
            .group_by(User.id)
            .options(selectinload(User.skills))
        )
    ).all()

    return [
        Candidate(
            user=user,
            matched=overlap(required_skills, {normalise(s.skill) for s in user.skills}),
            workload=workload,
        )
        for user, workload in rows
    ]


async def pick_moderator(session: AsyncSession, required_skills: list[str]) -> Candidate | None:
    """Best-fit moderator, or None when there are no active moderators at all.
    With no skill match, the least busy moderator is chosen."""
    found = await candidates(session, required_skills)
    if not found:
        return None
    return min(found, key=lambda c: c.score)
