from enum import StrEnum


class UserRole(StrEnum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class AuthProvider(StrEnum):
    EMAIL = "email"
    GOOGLE = "google"


class TicketStatus(StrEnum):
    OPEN = "open"
    PENDING_REVIEW = "pending_review"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


# "Your Tickets" vs "History" on the user dashboard.
ACTIVE_TICKET_STATUSES = frozenset(
    {
        TicketStatus.OPEN,
        TicketStatus.PENDING_REVIEW,
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
    }
)


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class OtpPurpose(StrEnum):
    REGISTRATION = "registration"
    PASSWORD_RESET = "password_reset"
