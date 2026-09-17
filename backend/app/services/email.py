"""Renders and sends the templated HTML emails.

Two ways out, chosen with EMAIL_PROVIDER:

- `smtp`  — Gmail SMTP, fine locally.
- `brevo` — Brevo's HTTPS API. Needed on hosts like Render that block outbound SMTP
            ports (25/465/587); port 443 is never blocked.

Rendering is identical either way, so an email looks the same whichever path it takes.
When nothing is configured (local development) the email is logged instead of sent.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "emails" / "templates"

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"
SEND_TIMEOUT_SECONDS = 30

# Each template's brand band: indigo normally, amber when an admin has to act.
ACCENTS: dict[str, tuple[str, str]] = {
    "pending_review.html": ("#b45309", "#f59e0b"),
}
DEFAULT_ACCENT = ("#3b55d9", "#6b86f0")


@lru_cache
def _templates() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


@lru_cache
def _smtp() -> FastMail:
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


def render(template: str, context: dict[str, Any]) -> str:
    return _templates().get_template(template).render(**context)


async def _send_via_smtp(to: str, subject: str, html: str) -> None:
    message = MessageSchema(subject=subject, recipients=[to], body=html, subtype=MessageType.html)
    await _smtp().send_message(message)


async def _send_via_brevo(to: str, subject: str, html: str) -> None:
    payload = {
        "sender": {"name": settings.mail_from_name, "email": settings.mail_from},
        "to": [{"email": to}],
        "subject": subject,
        "htmlContent": html,
    }
    async with httpx.AsyncClient(timeout=SEND_TIMEOUT_SECONDS) as client:
        response = await client.post(
            BREVO_ENDPOINT,
            json=payload,
            headers={"api-key": settings.brevo_api_key, "accept": "application/json"},
        )
    if response.status_code >= 400:
        # Brevo explains refusals in the body: unverified sender, bad key, quota.
        raise RuntimeError(
            f"Brevo refused the email ({response.status_code}): {response.text[:300]}"
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
            raise RuntimeError(
                "Email is not configured. Set EMAIL_PROVIDER with either BREVO_API_KEY "
                "or the MAIL_* SMTP settings."
            )
        logger.warning("Email not configured; would send %r to %s: %s", template, to, context)
        return

    html = render(template, body)
    try:
        if settings.email_provider == "brevo":
            await _send_via_brevo(to, subject, html)
        else:
            await _send_via_smtp(to, subject, html)
    except Exception:
        logger.exception(
            "Failed to send %r email to %s via %s", template, to, settings.email_provider
        )
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
