"""Shared FastAPI dependencies: database session, current user, role checks.

Every non-public router must depend on `CurrentUser` or `require_role(...)`.
"""

import uuid
from collections.abc import Callable, Coroutine
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models import TicketStatus, User, UserRole
from app.schemas.tickets import TicketFilters

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise UnauthorizedError("Not authenticated")
    payload = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError as exc:
        raise UnauthorizedError("Invalid access token") from exc

    # Always load from the database, so role changes and deactivation apply immediately.
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account not found or disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: UserRole) -> Callable[..., Coroutine[Any, Any, User]]:
    """Usage: `user: Annotated[User, Depends(require_role(UserRole.ADMIN))]`
    or `APIRouter(dependencies=[Depends(require_role(UserRole.ADMIN))])`."""
    allowed = frozenset(roles)

    async def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise ForbiddenError("You do not have permission to perform this action")
        return user

    return _check


AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
ModeratorUser = Annotated[User, Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))]


def ticket_filters(
    q: Annotated[str | None, Query(max_length=200, description="Search in title")] = None,
    status: Annotated[list[TicketStatus] | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query(description="Inclusive")] = None,
) -> TicketFilters:
    try:
        return TicketFilters(q=q, status=status, date_from=date_from, date_to=date_to)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


FiltersDep = Annotated[TicketFilters, Depends(ticket_filters)]
