from datetime import timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, RateLimitedError
from app.core.security import generate_otp, hash_otp, otp_matches, utcnow
from app.models import OtpCode, OtpPurpose


class InvalidOtpError(AppError):
    code = "invalid_otp"


async def issue_otp(
    session: AsyncSession,
    email: str,
    purpose: OtpPurpose,
    payload: dict[str, Any] | None = None,
) -> str:
    """Create a new OTP (invalidating older ones) and return the plaintext code.
    The caller commits and sends the email."""
    now = utcnow()
    window_start = now - timedelta(minutes=settings.otp_rate_limit_window_minutes)
    recent = await session.scalar(
        select(func.count())
        .select_from(OtpCode)
        .where(
            OtpCode.email == email,
            OtpCode.purpose == purpose,
            OtpCode.created_at >= window_start,
        )
    )
    if (recent or 0) >= settings.otp_rate_limit_count:
        raise RateLimitedError(
            "Too many codes requested. Please wait a few minutes and try again.",
            details={"retry_after_minutes": settings.otp_rate_limit_window_minutes},
        )

    # Only the newest code is ever valid.
    await session.execute(
        update(OtpCode)
        .where(
            OtpCode.email == email,
            OtpCode.purpose == purpose,
            OtpCode.consumed_at.is_(None),
        )
        .values(consumed_at=now)
    )

    code = generate_otp()
    session.add(
        OtpCode(
            email=email,
            purpose=purpose,
            code_hash=hash_otp(email, purpose, code),
            payload=payload,
            expires_at=now + timedelta(minutes=settings.otp_ttl_minutes),
            created_at=now,
        )
    )
    return code


async def verify_otp(session: AsyncSession, email: str, purpose: OtpPurpose, code: str) -> OtpCode:
    """Consume a valid code, or raise. Commits failed attempts so the limit holds."""
    now = utcnow()
    otp = await session.scalar(
        select(OtpCode)
        .where(
            OtpCode.email == email,
            OtpCode.purpose == purpose,
            OtpCode.consumed_at.is_(None),
        )
        .order_by(OtpCode.created_at.desc())
        .limit(1)
        .with_for_update()
    )

    if otp is None or otp.expires_at <= now:
        raise InvalidOtpError("This code is invalid or has expired. Request a new one.")
    if otp.attempts >= settings.otp_max_attempts:
        raise InvalidOtpError("Too many incorrect attempts. Request a new code.")

    if not otp_matches(email, purpose, code, otp.code_hash):
        otp.attempts += 1
        remaining = settings.otp_max_attempts - otp.attempts
        await session.commit()
        raise InvalidOtpError(
            "Incorrect code."
            if remaining > 0
            else "Too many incorrect attempts. Request a new code.",
            details={"attempts_remaining": max(remaining, 0)},
        )

    otp.consumed_at = now
    return otp
