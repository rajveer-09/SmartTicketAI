import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.models import TicketPriority, TicketStatus, UserRole

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole


class TicketCreate(BaseModel):
    title: Title
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=10, max_length=5000)
    ]


class TicketOut(BaseModel):
    """`ai_notes` / `ai_model_used` are only filled in for moderators and admins."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    status: TicketStatus
    category: str | None
    priority: TicketPriority | None
    required_skills: list[str]
    ai_notes: str | None = None
    ai_model_used: str | None = None
    created_by: UserBrief
    assignee: UserBrief | None
    created_at: datetime
    updated_at: datetime
    assigned_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None


class CommentCreate(BaseModel):
    body: Body


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    body: str
    author: UserBrief | None
    created_at: datetime


class TicketDetailOut(TicketOut):
    comments: list[CommentOut]


class StatusUpdate(BaseModel):
    status: Literal[TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED]


class AssignRequest(BaseModel):
    moderator_id: uuid.UUID


class TicketFilters(BaseModel):
    """Shared search filters for every ticket list."""

    q: Annotated[str | None, Field(max_length=200, description="Search in title")] = None
    status: list[TicketStatus] | None = None
    date_from: date | None = None
    date_to: date | None = Field(default=None, description="Inclusive")

    @model_validator(mode="after")
    def _dates_in_order(self) -> "TicketFilters":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be on or before date_to")
        return self
