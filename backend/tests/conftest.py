import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api import auth as auth_api
from app.core import database
from app.core.config import settings
from app.core.database import build_engine, get_session
from app.core.security import hash_password
from app.main import create_app
from app.models import AuthProvider, Base, User, UserRole
from app.services import notifications

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(db_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"db_url={db_url}"]})()
    return cfg


@pytest.fixture(scope="session", autouse=True)
def use_test_database():
    """Point the whole app at TEST_DATABASE_URL, including background jobs that open
    their own sessions. Without this a test could write to the real database."""
    if not settings.test_database_url:
        yield
        return
    patch = pytest.MonkeyPatch()
    patch.setattr(settings, "database_url", settings.test_database_url)
    database.get_engine.cache_clear()
    database.get_sessionmaker.cache_clear()
    yield
    patch.undo()
    database.get_engine.cache_clear()
    database.get_sessionmaker.cache_clear()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """App client with no database override (for tests that don't touch the DB)."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """Engine for TEST_DATABASE_URL, migrated to head. Skips when it is not set."""
    if not settings.test_database_url:
        pytest.skip("TEST_DATABASE_URL is not set")
    engine = build_engine(settings.test_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await asyncio.to_thread(command.upgrade, alembic_config(settings.test_database_url), "head")
    yield engine
    await engine.dispose()


@pytest.fixture
async def sessionmaker(test_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    async with test_engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    return async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)


@dataclass
class Outbox:
    """Captures OTP emails (sent directly) and every templated email (sent by jobs)."""

    otps: list[tuple[str, str, str]] = field(default_factory=list)  # (email, code, purpose)
    sent: list[tuple[str, str, dict]] = field(default_factory=list)  # (to, template, context)

    def last_code(self, email: str) -> str:
        return next(code for to, code, _ in reversed(self.otps) if to == email)

    def templates(self, template: str) -> list[tuple[str, str, dict]]:
        return [m for m in self.sent if m[1] == template]


@pytest.fixture
def outbox(monkeypatch: pytest.MonkeyPatch) -> Outbox:
    box = Outbox()

    async def fake_otp(to: str, code: str, purpose: str) -> None:
        box.otps.append((to, code, str(purpose)))

    async def fake_send(to: str, subject: str, template: str, context: dict) -> None:
        box.sent.append((to, template, context))

    monkeypatch.setattr(auth_api, "send_otp_email", fake_otp)
    monkeypatch.setattr(notifications, "send_email", fake_send)
    return box


@pytest.fixture
async def db_client(
    sessionmaker: async_sessionmaker[AsyncSession], outbox: Outbox, events: list
) -> AsyncIterator[AsyncClient]:
    """App client wired to the (truncated) test database, with email captured."""
    app = create_app()

    async def _session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def make_user(sessionmaker: async_sessionmaker[AsyncSession]):
    async def _make(
        email: str = "user@example.com",
        password: str | None = "password123",
        role: UserRole = UserRole.USER,
        is_active: bool = True,
        google_sub: str | None = None,
    ) -> User:
        async with sessionmaker() as session:
            user = User(
                email=email,
                full_name=email.split("@")[0].title(),
                hashed_password=hash_password(password) if password else None,
                role=role,
                auth_provider=AuthProvider.GOOGLE if google_sub else AuthProvider.EMAIL,
                google_sub=google_sub,
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            return user

    return _make


async def login(client: AsyncClient, email: str, password: str = "password123") -> str:
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> list:
    """Captures domain events published after commit."""
    from app import events as events_module

    captured: list = []

    async def fake_publish(batch) -> None:
        captured.extend(batch)

    monkeypatch.setattr(events_module, "publish", fake_publish)
    return captured


def auth_headers(user: User) -> dict[str, str]:
    from app.core.security import create_access_token

    token, _ = create_access_token(user.id, user.role)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def make_ticket(sessionmaker: async_sessionmaker[AsyncSession]):
    from datetime import datetime

    from app.models import Ticket, TicketStatus

    async def _make(
        owner: User,
        title: str = "Printer is on fire",
        *,
        status: TicketStatus = TicketStatus.OPEN,
        assignee: User | None = None,
        created_at: datetime | None = None,
        ai_notes: str | None = None,
    ) -> Ticket:
        async with sessionmaker() as session:
            ticket = Ticket(
                title=title,
                description="Something is wrong and needs fixing.",
                status=status,
                created_by_id=owner.id,
                assignee_id=assignee.id if assignee else None,
                ai_notes=ai_notes,
            )
            if created_at:
                ticket.created_at = created_at
            session.add(ticket)
            await session.commit()
            return ticket

    return _make


def event_names(events) -> list[str]:
    return [e.name for e in events]
