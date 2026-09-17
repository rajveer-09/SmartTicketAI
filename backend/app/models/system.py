from datetime import datetime

from sqlalchemy import DateTime, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDPrimaryKey


class ModelQuotaState(Base):
    """Which Gemini models are out of quota, and until when (for model fallback)."""

    __tablename__ = "model_quota_state"

    model_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    exhausted_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()")
    )


class SentEmail(UUIDPrimaryKey, Base):
    """Idempotency log: an Inngest retry never sends the same email twice.

    `idempotency_key` is built as "{event_id}:{template}:{recipient}".
    """

    __tablename__ = "sent_emails"

    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    recipient: Mapped[str] = mapped_column(String(320), index=True)
    template: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
