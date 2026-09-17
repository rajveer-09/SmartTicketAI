"""Sends templated HTML email through Gmail SMTP (fastapi-mail).

When MAIL_* settings are empty (local development), emails are logged instead of sent.
Phase 4 moves these calls into Inngest functions with idempotency keys.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.core.config import settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "emails" / "templates"

# Each template's brand band: indigo normally, amber when an admin has to act.
ACCENTS: dict[str, tuple[str, str]] = {
    "pending_review.html": ("#b45309", "#f59e0b"),
}
DEFAULT_ACCENT = ("#3b55d9", "#6b86f0")


@lru_cache
def _mailer() -> FastMail:
    return FastMail(
        ConnectionConfig(
            MAIL_USERNAME=settings.mail_username,
            MAIL_PASSWORD=settings.mail_password,
            MAIL_FROM=settings.mail_from,
            MAIL_FROM_NAME=settings.mail_from_name,
            MAIL_SERVER=settings.mail_server,
            MAIL_PORT=settings.mail_port,
            MAIL_STARTTLS=settings.mail_port == 587,
            MAIL_SSL_TLS=settings.mail_port == 465,
            USE_CREDENTIALS=True,
            VALIDATE_CERTS=True,
            TEMPLATE_FOLDER=TEMPLATE_DIR,
        )
    )


async def send_email(to: str, subject: str, template: str, context: dict[str, Any]) -> None:
    accent, accent_light = ACCENTS.get(template, DEFAULT_ACCENT)
    body = {
        "app_name": settings.mail_from_name,
        "frontend_url": settings.frontend_url,
        "accent": accent,
        "accent_light": accent_light,
        "preheader": context.get("preheader", subject),
        **context,
    }

    if not settings.mail_enabled:
        if settings.environment == "production":
            raise RuntimeError("MAIL_* settings are required in production")
        logger.warning("MAIL not configured; would send %r to %s: %s", template, to, context)
        return

    message = MessageSchema(
        subject=subject, recipients=[to], template_body=body, subtype=MessageType.html
    )
    try:
        await _mailer().send_message(message, template_name=template)
    except Exception:
        logger.exception("Failed to send %r email to %s", template, to)
        raise


async def send_otp_email(to: str, code: str, purpose: str) -> None:
    is_reset = purpose == "password_reset"
    await send_email(
        to,
        subject="Your password reset code" if is_reset else "Verify your email",
        template="otp.html",
        context={
            "code": code,
            "minutes": settings.otp_ttl_minutes,
            "heading": "Reset your password" if is_reset else "Confirm your email",
            "intro": (
                "Use this code to reset your password."
                if is_reset
                else "Use this code to finish creating your account."
            ),
        },
    )


async def send_welcome_email(to: str, full_name: str) -> None:
    await send_email(
        to,
        subject=f"Welcome to {settings.mail_from_name}",
        template="welcome.html",
        context={"full_name": full_name},
    )
