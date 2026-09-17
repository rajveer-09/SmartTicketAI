"""Import every model here so Alembic and SQLAlchemy see the full metadata."""

from app.models.auth import OtpCode, RefreshToken
from app.models.base import Base
from app.models.enums import (
    ACTIVE_TICKET_STATUSES,
    AuthProvider,
    OtpPurpose,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.models.system import ModelQuotaState, SentEmail
from app.models.ticket import Ticket, TicketComment
from app.models.user import ModeratorSkill, User

__all__ = [
    "ACTIVE_TICKET_STATUSES",
    "AuthProvider",
    "Base",
    "ModelQuotaState",
    "ModeratorSkill",
    "OtpCode",
    "OtpPurpose",
    "RefreshToken",
    "SentEmail",
    "Ticket",
    "TicketComment",
    "TicketPriority",
    "TicketStatus",
    "User",
    "UserRole",
]
