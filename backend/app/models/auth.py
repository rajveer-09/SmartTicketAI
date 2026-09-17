import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey, pg_enum
from app.models.enums import OtpPurpose


class OtpCode(UUIDPrimaryKey, Base):
    """A one-time password for registration or password reset.

    Registration OTPs carry the pending sign-up (name + already-hashed password) in
    `payload`, because the account is only created after the OTP is verified.
    """

    __tablename__ = "otp_codes"
    __table_args__ = (
        # Lookup of the latest code, and per-email rate limiting.
        Index("ix_otp_codes_email_purpose_created_at", "email", "purpose", "created_at"),
    )

    email: Mapped[str] = mapped_column(String(320))
    purpose: Mapped[OtpPurpose] = mapped_column(pg_enum(OtpPurpose, "otp_purpose"))
    code_hash: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class RefreshToken(UUIDPrimaryKey, Base):
    """Refresh tokens are stored hashed and rotated on every use."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when rotated; reuse of a rotated token means it was stolen.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
