import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.security import (
    create_access_token,
    hash_password,
    hash_token,
    new_refresh_token,
    utcnow,
    verify_password,
)
from app.models import AuthProvider, OtpPurpose, RefreshToken, User, UserRole
from app.schemas.auth import UserOut
from app.services import otp as otp_service

logger = logging.getLogger(__name__)


@dataclass
class IssuedTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    user: User


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        auth_provider=user.auth_provider,
        has_password=user.hashed_password is not None,
        created_at=user.created_at,
    )


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await session.scalar(select(User).where(User.email == email))


# --- Tokens ---


async def issue_tokens(session: AsyncSession, user: User) -> IssuedTokens:
    """Create an access token and a refresh token. The caller commits."""
    access, expires_in = create_access_token(user.id, user.role)
    refresh = new_refresh_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh),
            expires_at=utcnow() + timedelta(days=settings.refresh_token_days),
        )
    )
    await session.flush()
    return IssuedTokens(access, expires_in, refresh, user)


async def rotate_refresh_token(session: AsyncSession, raw_token: str | None) -> IssuedTokens:
    if not raw_token:
        raise UnauthorizedError("Not authenticated")

    now = utcnow()
    stored = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    if stored is None:
        raise UnauthorizedError("Session expired. Please sign in again.")

    if stored.revoked_at is not None:
        if stored.replaced_by_id is not None:
            # A token that was already rotated is being reused: assume it was stolen
            # and end every session for this user.
            logger.warning("Refresh token reuse detected for user %s", stored.user_id)
            await revoke_all_refresh_tokens(session, stored.user_id)
            await session.commit()
        raise UnauthorizedError("Session expired. Please sign in again.")

    if stored.expires_at <= now:
        raise UnauthorizedError("Session expired. Please sign in again.")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account not found or disabled")

    access, expires_in = create_access_token(user.id, user.role)
    refresh = new_refresh_token()
    replacement = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh),
        expires_at=now + timedelta(days=settings.refresh_token_days),
    )
    session.add(replacement)
    await session.flush()
    stored.revoked_at = now
    stored.replaced_by_id = replacement.id
    await session.commit()
    return IssuedTokens(access, expires_in, refresh, user)


async def revoke_refresh_token(session: AsyncSession, raw_token: str | None) -> None:
    if not raw_token:
        return
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token), RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()


async def revoke_all_refresh_tokens(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


# --- Email registration ---


async def start_registration(
    session: AsyncSession, full_name: str, email: str, password: str
) -> str:
    """Store the pending sign-up with an OTP. Returns the code to email. Commits."""
    if await get_user_by_email(session, email):
        raise ConflictError("An account with this email already exists. Try signing in.")

    hashed = await run_in_threadpool(hash_password, password)
    code = await otp_service.issue_otp(
        session,
        email,
        OtpPurpose.REGISTRATION,
        payload={"full_name": full_name, "hashed_password": hashed},
    )
    await session.commit()
    return code


async def complete_registration(session: AsyncSession, email: str, code: str) -> User:
    otp = await otp_service.verify_otp(session, email, OtpPurpose.REGISTRATION, code)
    if await get_user_by_email(session, email):
        await session.commit()
        raise ConflictError("An account with this email already exists. Try signing in.")

    payload = otp.payload or {}
    user = User(
        email=email,
        full_name=payload["full_name"],
        hashed_password=payload["hashed_password"],
        role=UserRole.USER,
        auth_provider=AuthProvider.EMAIL,
    )
    session.add(user)
    otp.payload = None  # don't keep the password hash around
    try:
        await session.flush()
    except IntegrityError as exc:  # two verifications raced
        await session.rollback()
        raise ConflictError("An account with this email already exists. Try signing in.") from exc
    return user


# --- Login ---


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await get_user_by_email(session, email)
    ok = await run_in_threadpool(verify_password, password, user.hashed_password if user else None)
    if user is None or not ok:
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("This account has been disabled")
    return user


# --- Password reset ---


async def start_password_reset(session: AsyncSession, email: str) -> str | None:
    """Returns a code to email, or None when there's no such active account.
    The API response is identical either way, so emails can't be probed."""
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active:
        return None
    code = await otp_service.issue_otp(session, email, OtpPurpose.PASSWORD_RESET)
    await session.commit()
    return code


async def complete_password_reset(
    session: AsyncSession, email: str, code: str, new_password: str
) -> None:
    await otp_service.verify_otp(session, email, OtpPurpose.PASSWORD_RESET, code)
    user = await get_user_by_email(session, email)
    if user is None or not user.is_active:
        await session.commit()
        raise otp_service.InvalidOtpError("This code is invalid or has expired.")

    user.hashed_password = await run_in_threadpool(hash_password, new_password)
    await revoke_all_refresh_tokens(session, user.id)  # sign out everywhere
    await session.commit()


# --- Google ---


@dataclass
class GoogleLoginResult:
    user: User
    created: bool


async def login_with_google(session: AsyncSession, userinfo: dict) -> GoogleLoginResult:
    """Find or create the user for a verified Google identity. Does not commit."""
    sub = userinfo.get("sub")
    email = (userinfo.get("email") or "").strip().lower()
    if not sub or not email:
        raise UnauthorizedError("Google did not return an email address")
    if not userinfo.get("email_verified"):
        raise UnauthorizedError("Your Google email address is not verified")

    user = await session.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = await get_user_by_email(session, email)
        if user is not None:
            # Same email already registered: Google has verified it, so link the accounts.
            user.google_sub = sub

    if user is not None:
        if not user.is_active:
            raise ForbiddenError("This account has been disabled")
        return GoogleLoginResult(user, created=False)

    user = User(
        email=email,
        full_name=(userinfo.get("name") or email.split("@")[0])[:120],
        hashed_password=None,
        role=UserRole.USER,
        auth_provider=AuthProvider.GOOGLE,
        google_sub=sub,
    )
    session.add(user)
    await session.flush()
    return GoogleLoginResult(user, created=True)
