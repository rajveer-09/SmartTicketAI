from datetime import timedelta

from sqlalchemy import select, update

from app.core.config import settings
from app.core.security import hash_password, utcnow, verify_password
from app.models import OtpCode, RefreshToken, User, UserRole
from tests.conftest import login

REGISTER = {"full_name": "Asha Rao", "email": "Asha@Example.com", "password": "s3cure-pass"}
EMAIL = "asha@example.com"


def _refresh_cookie(resp) -> str:
    return resp.cookies[settings.refresh_cookie_name]


# --- Registration ---


async def test_register_then_verify_creates_account_and_signs_in(
    db_client, outbox, sessionmaker, events
):
    resp = await db_client.post("/api/auth/register", json=REGISTER)
    assert resp.status_code == 202
    assert outbox.otps[-1][0] == EMAIL  # email normalised

    async with sessionmaker() as s:
        assert await s.scalar(select(User).where(User.email == EMAIL)) is None  # not yet

    resp = await db_client.post(
        "/api/auth/register/verify", json={"email": EMAIL, "code": outbox.last_code(EMAIL)}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["email"] == EMAIL
    assert body["user"]["role"] == "user"
    assert body["access_token"]
    assert _refresh_cookie(resp)
    assert [e.name for e in events] == ["user/created"]

    async with sessionmaker() as s:
        user = await s.scalar(select(User).where(User.email == EMAIL))
        otp = await s.scalar(select(OtpCode).where(OtpCode.email == EMAIL))
    assert verify_password("s3cure-pass", user.hashed_password)
    assert otp.consumed_at is not None
    assert otp.payload is None  # pending password hash is cleared


async def test_register_existing_email_conflicts(db_client, make_user):
    await make_user(EMAIL)
    resp = await db_client.post("/api/auth/register", json=REGISTER)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


async def test_register_validates_input(db_client):
    resp = await db_client.post(
        "/api/auth/register", json={"full_name": "", "email": "nope", "password": "short"}
    )
    assert resp.status_code == 422
    fields = {d["field"] for d in resp.json()["error"]["details"]}
    assert {"body.full_name", "body.email", "body.password"} <= fields


async def test_wrong_otp_counts_attempts_and_locks(db_client, outbox):
    await db_client.post("/api/auth/register", json=REGISTER)
    right = outbox.last_code(EMAIL)
    wrong = "000000" if right != "000000" else "111111"

    for remaining in range(settings.otp_max_attempts - 1, -1, -1):
        resp = await db_client.post("/api/auth/register/verify", json={"email": EMAIL, "code": wrong})
        assert resp.status_code == 400
        assert resp.json()["error"]["details"]["attempts_remaining"] == remaining

    # Even the right code is refused once the limit is reached.
    resp = await db_client.post("/api/auth/register/verify", json={"email": EMAIL, "code": right})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "invalid_otp"


async def test_expired_otp_is_rejected(db_client, outbox, sessionmaker):
    await db_client.post("/api/auth/register", json=REGISTER)
    async with sessionmaker() as s:
        await s.execute(update(OtpCode).values(expires_at=utcnow() - timedelta(seconds=1)))
        await s.commit()

    resp = await db_client.post(
        "/api/auth/register/verify", json={"email": EMAIL, "code": outbox.last_code(EMAIL)}
    )
    assert resp.status_code == 400
    assert "expired" in resp.json()["error"]["message"]


async def test_resend_invalidates_previous_code(db_client, outbox):
    await db_client.post("/api/auth/register", json=REGISTER)
    first = outbox.last_code(EMAIL)
    await db_client.post("/api/auth/register", json=REGISTER)
    second = outbox.last_code(EMAIL)

    if first != second:
        resp = await db_client.post("/api/auth/register/verify", json={"email": EMAIL, "code": first})
        assert resp.status_code == 400
    resp = await db_client.post("/api/auth/register/verify", json={"email": EMAIL, "code": second})
    assert resp.status_code == 201


async def test_otp_requests_are_rate_limited(db_client):
    for _ in range(settings.otp_rate_limit_count):
        assert (await db_client.post("/api/auth/register", json=REGISTER)).status_code == 202
    resp = await db_client.post("/api/auth/register", json=REGISTER)
    assert resp.status_code == 429
    assert resp.json()["error"]["code"] == "rate_limited"


# --- Login / me ---


async def test_login_and_me(db_client, make_user):
    await make_user(EMAIL)
    token = await login(db_client, "ASHA@example.com")

    resp = await db_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == EMAIL
    assert resp.json()["has_password"] is True


async def test_login_failures_share_one_message(db_client, make_user):
    await make_user(EMAIL)
    await make_user("google@example.com", password=None, google_sub="g-1")

    for email, password in [
        (EMAIL, "wrong-password"),
        ("nobody@example.com", "password123"),
        ("google@example.com", "password123"),  # Google-only account has no password
    ]:
        resp = await db_client.post("/api/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 401
        assert resp.json()["error"]["message"] == "Invalid email or password"


async def test_disabled_account_cannot_log_in(db_client, make_user):
    await make_user(EMAIL, is_active=False)
    resp = await db_client.post("/api/auth/login", json={"email": EMAIL, "password": "password123"})
    assert resp.status_code == 403


async def test_me_requires_valid_token(db_client):
    assert (await db_client.get("/api/auth/me")).status_code == 401
    resp = await db_client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


async def test_deactivated_user_token_stops_working(db_client, make_user, sessionmaker):
    user = await make_user(EMAIL)
    token = await login(db_client, EMAIL)
    async with sessionmaker() as s:
        await s.execute(update(User).where(User.id == user.id).values(is_active=False))
        await s.commit()

    resp = await db_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# --- Refresh / logout ---


async def test_refresh_rotates_token(db_client, make_user):
    await make_user(EMAIL)
    resp = await db_client.post("/api/auth/login", json={"email": EMAIL, "password": "password123"})
    first = _refresh_cookie(resp)

    resp = await db_client.post("/api/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    second = _refresh_cookie(resp)
    assert second != first


async def test_reusing_rotated_refresh_token_revokes_all_sessions(
    db_client, make_user, sessionmaker
):
    await make_user(EMAIL)
    resp = await db_client.post("/api/auth/login", json={"email": EMAIL, "password": "password123"})
    stolen = _refresh_cookie(resp)
    assert (await db_client.post("/api/auth/refresh")).status_code == 200  # legit rotation

    db_client.cookies.clear()
    db_client.cookies.set(settings.refresh_cookie_name, stolen, path="/api/auth")
    resp = await db_client.post("/api/auth/refresh")
    assert resp.status_code == 401

    async with sessionmaker() as s:
        active = await s.scalars(select(RefreshToken).where(RefreshToken.revoked_at.is_(None)))
        assert active.all() == []


async def test_logout_revokes_refresh_token(db_client, make_user):
    await make_user(EMAIL)
    resp = await db_client.post("/api/auth/login", json={"email": EMAIL, "password": "password123"})
    token = _refresh_cookie(resp)

    assert (await db_client.post("/api/auth/logout")).status_code == 204
    db_client.cookies.clear()
    db_client.cookies.set(settings.refresh_cookie_name, token, path="/api/auth")
    resp = await db_client.post("/api/auth/refresh")
    assert resp.status_code == 401


async def test_refresh_without_cookie_is_unauthorized(db_client):
    assert (await db_client.post("/api/auth/refresh")).status_code == 401


# --- Password reset ---


async def test_password_reset_flow_signs_out_everywhere(db_client, make_user, outbox, sessionmaker):
    await make_user(EMAIL)
    await db_client.post("/api/auth/login", json={"email": EMAIL, "password": "password123"})

    resp = await db_client.post("/api/auth/forgot-password", json={"email": EMAIL})
    assert resp.status_code == 202
    code = outbox.last_code(EMAIL)
    assert outbox.otps[-1][2] == "password_reset"

    resp = await db_client.post(
        "/api/auth/reset-password",
        json={"email": EMAIL, "code": code, "new_password": "brand-new-pass"},
    )
    assert resp.status_code == 200, resp.text

    assert (await db_client.post("/api/auth/refresh")).status_code == 401  # old session gone
    assert await login(db_client, EMAIL, "brand-new-pass")
    resp = await db_client.post("/api/auth/login", json={"email": EMAIL, "password": "password123"})
    assert resp.status_code == 401


async def test_forgot_password_does_not_reveal_unknown_emails(db_client, outbox):
    resp = await db_client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 202
    assert outbox.otps == []


async def test_registration_code_cannot_reset_password(db_client, make_user, outbox, sessionmaker):
    """OTP hashes are bound to their purpose."""
    user = await make_user(EMAIL)
    await db_client.post("/api/auth/forgot-password", json={"email": EMAIL})
    code = outbox.last_code(EMAIL)
    async with sessionmaker() as s:
        # Relabel the reset code as a registration code: its hash no longer matches.
        await s.execute(update(OtpCode).values(purpose="registration"))
        await s.execute(
            update(User).where(User.id == user.id).values(hashed_password=hash_password("x" * 8))
        )
        await s.commit()

    resp = await db_client.post(
        "/api/auth/reset-password", json={"email": EMAIL, "code": code, "new_password": "whatever1"}
    )
    assert resp.status_code == 400


# --- Roles ---


async def test_role_is_reported_from_database(db_client, make_user):
    await make_user("mod@example.com", role=UserRole.MODERATOR)
    token = await login(db_client, "mod@example.com")
    resp = await db_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.json()["role"] == "moderator"
