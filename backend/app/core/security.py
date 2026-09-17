"""Passwords, JWT access tokens, refresh tokens and OTP codes."""

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.errors import UnauthorizedError

_hasher = PasswordHash.recommended()  # argon2id

# Used when the user doesn't exist, so login takes the same time either way.
_DUMMY_HASH = _hasher.hash("timing-equaliser")


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- Passwords (argon2 is CPU-heavy: call these via run_in_threadpool) ---


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, hashed)


# --- Access tokens ---


def create_access_token(user_id: uuid.UUID, role: str) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    now = utcnow()
    expires_in = settings.access_token_minutes * 60
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
        "jti": secrets.token_hex(8),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token") from exc
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid access token")
    return payload


# --- Refresh tokens (opaque; only a SHA-256 hash is stored) ---


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- OTP codes ---


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(email: str, purpose: str, code: str) -> str:
    """HMAC keyed with the server secret: a leaked table can't be brute-forced offline,
    and the hash is bound to the email and purpose."""
    msg = f"{email}:{purpose}:{code}".encode()
    return hmac.new(settings.jwt_secret.encode(), msg, hashlib.sha256).hexdigest()


def otp_matches(email: str, purpose: str, code: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(email, purpose, code), code_hash)
