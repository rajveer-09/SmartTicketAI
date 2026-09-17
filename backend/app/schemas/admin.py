import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from app.models import AuthProvider, UserRole
from app.schemas.auth import FullName, NormalizedEmail, Password
from app.schemas.tickets import TicketOut

MAX_SKILLS = 50


def _normalise_skills(skills: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for raw in skills:
        skill = " ".join(raw.strip().lower().split())
        if not skill:
            continue
        if len(skill) > 64:
            raise ValueError(f"Skill too long (max 64 characters): {skill[:20]}...")
        seen.setdefault(skill, None)
    return list(seen)


SkillList = Annotated[list[str], Field(max_length=MAX_SKILLS), AfterValidator(_normalise_skills)]


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    auth_provider: AuthProvider
    is_active: bool
    skills: list[str]
    created_at: datetime


class AdminUserCreate(BaseModel):
    full_name: FullName
    email: NormalizedEmail
    password: Password
    role: UserRole = UserRole.USER
    skills: SkillList = []


class AdminUserUpdate(BaseModel):
    full_name: FullName | None = None
    role: UserRole | None = None
    is_active: bool | None = None


class SkillsUpdate(BaseModel):
    skills: SkillList


class ModeratorWorkload(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: UserRole
    is_active: bool
    skills: list[str]
    active: int = Field(description="Assigned + in progress")
    resolved: int
    closed: int
    total: int


class GlobalSearchResult(BaseModel):
    tickets: list[TicketOut]
    users: list[AdminUserOut]


SearchTerm = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
