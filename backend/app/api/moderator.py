from typing import Literal

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import FiltersDep, ModeratorUser, SessionDep
from app.core.pagination import PageDep, paginate
from app.models import Ticket
from app.schemas.common import Page
from app.schemas.tickets import TicketOut
from app.services import tickets as ticket_service

router = APIRouter(prefix="/moderator", tags=["moderator"])


@router.get("/tickets")
async def moderator_tickets(
    user: ModeratorUser,
    session: SessionDep,
    page: PageDep,
    filters: FiltersDep,
    scope: Literal["assigned", "solved"] = "assigned",
) -> Page[TicketOut]:
    """Moderator dashboard. `assigned` = assigned + in progress, `solved` = resolved + closed.
    Admins get their own assignments here too."""
    statuses = ticket_service.ACTIVE_ASSIGNMENT if scope == "assigned" else ticket_service.SOLVED
    stmt = ticket_service.with_people(
        select(Ticket).where(Ticket.assignee_id == user.id, Ticket.status.in_(statuses))
    )
    order = Ticket.created_at.desc() if scope == "assigned" else Ticket.resolved_at.desc()
    stmt = ticket_service.apply_filters(stmt, filters).order_by(order)
    return await paginate(session, stmt, page, lambda t: ticket_service.ticket_out(t, user))
