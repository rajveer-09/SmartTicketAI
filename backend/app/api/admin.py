import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select

from app.core.deps import AdminUser, FiltersDep, SessionDep, require_role
from app.core.pagination import PageDep, paginate
from app.events import commit_and_publish, queue_event
from app.models import Ticket, User, UserRole
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    GlobalSearchResult,
    ModeratorWorkload,
    SearchTerm,
    SkillsUpdate,
)
from app.schemas.common import Page
from app.schemas.tickets import AssignRequest, TicketFilters, TicketOut
from app.services import admin as admin_service
from app.services import tickets as ticket_service

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)

GLOBAL_SEARCH_LIMIT = 10


# --- Tickets ---


@router.get("/tickets")
async def all_tickets(
    admin: AdminUser,
    session: SessionDep,
    page: PageDep,
    filters: FiltersDep,
    assignee_id: uuid.UUID | None = None,
    created_by_id: uuid.UUID | None = None,
    unassigned: bool = False,
) -> Page[TicketOut]:
    stmt = ticket_service.with_people(select(Ticket))
    if assignee_id:
        stmt = stmt.where(Ticket.assignee_id == assignee_id)
    if created_by_id:
        stmt = stmt.where(Ticket.created_by_id == created_by_id)
    if unassigned:
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    stmt = ticket_service.apply_filters(stmt, filters).order_by(Ticket.created_at.desc())
    return await paginate(session, stmt, page, lambda t: ticket_service.ticket_out(t, admin))


@router.post("/tickets/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: uuid.UUID, body: AssignRequest, admin: AdminUser, session: SessionDep
) -> TicketOut:
    """Manually assign or reassign a ticket (including clearing Pending Review)."""
    ticket = await ticket_service.get_ticket_for(session, ticket_id, admin, for_update=True)
    moderator = await admin_service.get_user(session, body.moderator_id)
    await ticket_service.assign_ticket(session, ticket, moderator, admin, source="admin")
    await commit_and_publish(session)
    return ticket_service.ticket_out(ticket, admin)


# --- Users and moderators ---


@router.get("/users")
async def list_users(
    session: SessionDep,
    page: PageDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> Page[AdminUserOut]:
    stmt = select(User)
    if q and q.strip():
        stmt = stmt.where(admin_service.user_search_filter(q.strip()))
    if role:
        stmt = stmt.where(User.role == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    stmt = stmt.order_by(User.created_at.desc())
    return await paginate(session, stmt, page, admin_service.admin_user_out)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(body: AdminUserCreate, session: SessionDep) -> AdminUserOut:
    """Add a user, moderator or admin directly (no OTP: an admin vouches for the email)."""
    user = await admin_service.create_user(
        session, body.full_name, body.email, body.password, body.role, body.skills
    )
    queue_event(session, "user/created", {"user_id": str(user.id), "source": "admin"})
    await commit_and_publish(session)
    return admin_service.admin_user_out(await admin_service.get_user(session, user.id))


@router.get("/users/{user_id}")
async def get_user(user_id: uuid.UUID, session: SessionDep) -> AdminUserOut:
    return admin_service.admin_user_out(await admin_service.get_user(session, user_id))


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID, body: AdminUserUpdate, admin: AdminUser, session: SessionDep
) -> AdminUserOut:
    """Change name, role or active state. Demoting or disabling a moderator sends their
    open tickets back to Pending Review."""
    user = await admin_service.get_user(session, user_id, for_update=True)
    await admin_service.update_user(
        session,
        user,
        admin,
        full_name=body.full_name,
        role=body.role,
        is_active=body.is_active,
    )
    await commit_and_publish(session)
    return admin_service.admin_user_out(await admin_service.get_user(session, user_id))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user(user_id: uuid.UUID, admin: AdminUser, session: SessionDep) -> None:
    """Removes access by deactivating the account. Tickets and history are kept."""
    user = await admin_service.get_user(session, user_id, for_update=True)
    await admin_service.update_user(
        session, user, admin, full_name=None, role=None, is_active=False
    )
    await commit_and_publish(session)


@router.put("/users/{user_id}/skills")
async def replace_skills(
    user_id: uuid.UUID, body: SkillsUpdate, session: SessionDep
) -> AdminUserOut:
    user = await admin_service.get_user(session, user_id, for_update=True)
    await admin_service.replace_skills(session, user, body.skills)
    await commit_and_publish(session)
    return admin_service.admin_user_out(user)


@router.get("/moderators/workload")
async def moderator_workload(session: SessionDep) -> list[ModeratorWorkload]:
    return await admin_service.moderator_workload(session)


# --- Global search ---


@router.get("/search")
async def global_search(
    q: Annotated[SearchTerm, Query()], admin: AdminUser, session: SessionDep
) -> GlobalSearchResult:
    """Top matches across tickets (by title) and users (by name or email)."""
    ticket_stmt = ticket_service.apply_filters(
        ticket_service.with_people(select(Ticket)), TicketFilters(q=q)
    ).order_by(Ticket.created_at.desc())
    tickets = (await session.scalars(ticket_stmt.limit(GLOBAL_SEARCH_LIMIT))).all()

    user_stmt = (
        select(User)
        .where(admin_service.user_search_filter(q))
        .order_by(User.full_name)
        .limit(GLOBAL_SEARCH_LIMIT)
    )
    users = (await session.scalars(user_stmt)).all()

    return GlobalSearchResult(
        tickets=[ticket_service.ticket_out(t, admin) for t in tickets],
        users=[admin_service.admin_user_out(u) for u in users],
    )
