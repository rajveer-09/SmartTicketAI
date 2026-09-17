import uuid

from sqlalchemy import case, delete, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.models import AuthProvider, ModeratorSkill, Ticket, TicketStatus, User, UserRole
from app.schemas.admin import AdminUserOut, ModeratorWorkload
from app.services import auth as auth_service
from app.services import tickets as ticket_service


class SelfLockoutError(AppError):
    status_code = 400
    code = "self_lockout"


def admin_user_out(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        auth_provider=user.auth_provider,
        is_active=user.is_active,
        skills=sorted(s.skill for s in user.skills),
        created_at=user.created_at,
    )


def user_search_filter(term: str):
    pattern = f"%{ticket_service.escape_like(term)}%"
    return or_(User.email.ilike(pattern, escape="\\"), User.full_name.ilike(pattern, escape="\\"))


async def get_user(session: AsyncSession, user_id: uuid.UUID, *, for_update: bool = False) -> User:
    stmt = select(User).where(User.id == user_id).execution_options(populate_existing=True)
    if for_update:
        stmt = stmt.with_for_update(of=User)
    user = await session.scalar(stmt)
    if user is None:
        raise NotFoundError("User not found")
    return user


async def create_user(
    session: AsyncSession,
    full_name: str,
    email: str,
    password: str,
    role: UserRole,
    skills: list[str],
) -> User:
    if await auth_service.get_user_by_email(session, email):
        raise ConflictError("A user with this email already exists")
    user = User(
        email=email,
        full_name=full_name,
        hashed_password=await run_in_threadpool(hash_password, password),
        role=role,
        auth_provider=AuthProvider.EMAIL,
    )
    user.skills = [ModeratorSkill(skill=s) for s in skills]
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("A user with this email already exists") from exc
    return user


async def update_user(
    session: AsyncSession,
    user: User,
    actor: User,
    *,
    full_name: str | None,
    role: UserRole | None,
    is_active: bool | None,
) -> int:
    """Returns how many tickets were sent back to Pending Review."""
    if user.id == actor.id and (
        (role is not None and role != UserRole.ADMIN) or is_active is False
    ):
        raise SelfLockoutError("You can't remove your own admin access")

    if full_name is not None:
        user.full_name = full_name
    if role is not None:
        user.role = role
    if is_active is not None:
        user.is_active = is_active

    released = 0
    loses_staff = user.role not in ticket_service.STAFF_ROLES or not user.is_active
    if loses_staff:
        released = await ticket_service.release_tickets(session, user, actor)
    if not user.is_active:
        await auth_service.revoke_all_refresh_tokens(session, user.id)
    return released


async def replace_skills(session: AsyncSession, user: User, skills: list[str]) -> None:
    if user.role not in ticket_service.STAFF_ROLES:
        raise ConflictError("Skills can only be set for moderators and admins")
    await session.execute(delete(ModeratorSkill).where(ModeratorSkill.user_id == user.id))
    session.add_all(ModeratorSkill(user_id=user.id, skill=s) for s in skills)
    await session.flush()
    await session.refresh(user, attribute_names=["skills"])


async def moderator_workload(session: AsyncSession) -> list[ModeratorWorkload]:
    S = TicketStatus

    def _count(*statuses: TicketStatus):
        return func.count(case((Ticket.status.in_(statuses), Ticket.id)))

    rows = (
        await session.execute(
            select(
                User,
                _count(S.ASSIGNED, S.IN_PROGRESS).label("active"),
                _count(S.RESOLVED).label("resolved"),
                _count(S.CLOSED).label("closed"),
                func.count(Ticket.id).label("total"),
            )
            .outerjoin(Ticket, Ticket.assignee_id == User.id)
            .where(User.role == UserRole.MODERATOR)
            .group_by(User.id)
            .order_by(User.is_active.desc(), desc("active"), User.full_name)
        )
    ).all()

    return [
        ModeratorWorkload(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
            skills=sorted(s.skill for s in user.skills),
            active=active,
            resolved=resolved,
            closed=closed,
            total=total,
        )
        for user, active, resolved, closed, total in rows
    ]
