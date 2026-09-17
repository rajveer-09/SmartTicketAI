import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, Timestamps, UUIDPrimaryKey, pg_enum
from app.models.enums import AuthProvider, UserRole

if TYPE_CHECKING:
    from app.models.ticket import Ticket


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    # Always stored lowercased (enforced in the service layer).
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    # Null for Google-only accounts.
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, "user_role"), default=UserRole.USER, index=True
    )
    auth_provider: Mapped[AuthProvider] = mapped_column(
        pg_enum(AuthProvider, "auth_provider"), default=AuthProvider.EMAIL
    )
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    skills: Mapped[list["ModeratorSkill"]] = relationship(
        back_populates="moderator", cascade="all, delete-orphan", lazy="selectin"
    )
    assigned_tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="assignee", foreign_keys="Ticket.assignee_id"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"


class ModeratorSkill(UUIDPrimaryKey, Base):
    __tablename__ = "moderator_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill", name="uq_moderator_skills_user_skill"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Lowercased, trimmed skill name, e.g. "billing", "networking".
    skill: Mapped[str] = mapped_column(String(64), index=True)

    moderator: Mapped[User] = relationship(back_populates="skills")
