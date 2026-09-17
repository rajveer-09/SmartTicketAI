from typing import Annotated
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api import auth as auth_api
from app.core.config import settings
from app.core.database import get_session
from app.core.deps import require_role
from app.core.security import create_access_token
from app.main import create_app
from app.models import AuthProvider, User, UserRole
from tests.conftest import login

# --- Role-based access ---


@pytest.fixture
async def rbac_client(sessionmaker, outbox):
    app = create_app()
    probe = APIRouter()

    @probe.get("/probe/admin")
    async def admin_only(
        user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    ) -> dict:
        return {"ok": user.email}

    @probe.get(
        "/probe/staff", dependencies=[Depends(require_role(UserRole.MODERATOR, UserRole.ADMIN))]
    )
    async def staff_only() -> dict:
        return {"ok": True}

    app.include_router(probe)

    async def _session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.parametrize(
    ("role", "admin_status", "staff_status"),
    [
        (UserRole.USER, 403, 403),
        (UserRole.MODERATOR, 403, 200),
        (UserRole.ADMIN, 200, 200),
    ],
)
async def test_require_role(rbac_client, make_user, role, admin_status, staff_status):
    await make_user("someone@example.com", role=role)
    headers = {"Authorization": f"Bearer {await login(rbac_client, 'someone@example.com')}"}

    assert (await rbac_client.get("/probe/admin", headers=headers)).status_code == admin_status
    assert (await rbac_client.get("/probe/staff", headers=headers)).status_code == staff_status


async def test_role_in_token_is_not_trusted(rbac_client, make_user):
    """A token claiming 'admin' for a plain user must not grant admin access."""
    user = await make_user("plain@example.com", role=UserRole.USER)
    forged, _ = create_access_token(user.id, "admin")
    resp = await rbac_client.get("/probe/admin", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 403


async def test_unauthenticated_is_401_not_403(rbac_client):
    resp = await rbac_client.get("/probe/admin")
    assert resp.status_code == 401


# --- Google login (Google's side is faked) ---


class FakeGoogle:
    def __init__(self, userinfo: dict | None, error: Exception | None = None):
        self.userinfo_data = userinfo
        self.error = error

    async def authorize_access_token(self, request):
        if self.error:
            raise self.error
        return {"access_token": "x", "userinfo": self.userinfo_data}


@pytest.fixture
def fake_google(monkeypatch):
    def _install(userinfo: dict | None, error: Exception | None = None) -> None:
        monkeypatch.setattr(auth_api.oauth, "google", FakeGoogle(userinfo, error), raising=False)

    return _install


def _callback_query(resp) -> dict:
    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert location.startswith(f"{settings.frontend_url}/auth/google/callback")
    return parse_qs(urlparse(location).query)


GOOGLE_USER = {
    "sub": "google-123",
    "email": "New.Person@gmail.com",
    "email_verified": True,
    "name": "New Person",
}


async def test_google_first_login_creates_account(
    db_client, fake_google, outbox, sessionmaker, events
):
    fake_google(GOOGLE_USER)
    resp = await db_client.get("/api/auth/google/callback")

    assert _callback_query(resp) == {}
    assert settings.refresh_cookie_name in resp.cookies
    assert [e.name for e in events] == ["user/created"]
    assert events[0].data["source"] == "google"
    assert outbox.otps == []  # no OTP for Google

    async with sessionmaker() as s:
        user = await s.scalar(select(User).where(User.google_sub == "google-123"))
    assert user.email == "new.person@gmail.com"
    assert user.auth_provider == AuthProvider.GOOGLE
    assert user.hashed_password is None

    # The frontend then exchanges the cookie for an access token.
    refreshed = await db_client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["user"]["email"] == "new.person@gmail.com"


async def test_google_second_login_does_not_resend_welcome(db_client, fake_google, events):
    fake_google(GOOGLE_USER)
    await db_client.get("/api/auth/google/callback")
    await db_client.get("/api/auth/google/callback")
    assert [e.name for e in events] == ["user/created"]


async def test_google_links_existing_email_account(db_client, fake_google, make_user, sessionmaker):
    existing = await make_user("new.person@gmail.com")
    fake_google(GOOGLE_USER)

    resp = await db_client.get("/api/auth/google/callback")
    assert _callback_query(resp) == {}

    async with sessionmaker() as s:
        users = (await s.scalars(select(User))).all()
    assert len(users) == 1
    assert users[0].id == existing.id
    assert users[0].google_sub == "google-123"
    assert users[0].hashed_password is not None  # email login still works


async def test_google_unverified_email_is_rejected(db_client, fake_google, sessionmaker):
    fake_google({**GOOGLE_USER, "email_verified": False})
    resp = await db_client.get("/api/auth/google/callback")

    assert _callback_query(resp) == {"error": ["unauthorized"]}
    async with sessionmaker() as s:
        assert (await s.scalars(select(User))).all() == []


async def test_google_disabled_account_is_rejected(db_client, fake_google, make_user):
    await make_user("new.person@gmail.com", is_active=False)
    fake_google(GOOGLE_USER)
    resp = await db_client.get("/api/auth/google/callback")
    assert _callback_query(resp) == {"error": ["forbidden"]}


async def test_google_oauth_error_redirects_with_error(db_client, fake_google):
    from authlib.integrations.starlette_client import OAuthError

    fake_google(None, error=OAuthError(error="mismatching_state"))
    resp = await db_client.get("/api/auth/google/callback")
    assert _callback_query(resp) == {"error": ["google_auth_failed"]}


async def test_google_login_unconfigured_returns_503(db_client, monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    resp = await db_client.get("/api/auth/google/login")
    assert resp.status_code == 503
