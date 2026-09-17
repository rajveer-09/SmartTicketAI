from fastapi import FastAPI, Query
from httpx import ASGITransport, AsyncClient

from app.core.errors import NotFoundError, register_error_handlers
from app.core.security import hash_password, verify_password
from app.models import Base
from app.schemas.common import Page


def _error_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    async def missing() -> None:
        raise NotFoundError("Ticket not found")

    @app.get("/typed")
    async def typed(n: int = Query()) -> int:
        return n

    return app


async def test_app_error_has_standard_shape():
    async with AsyncClient(transport=ASGITransport(app=_error_app()), base_url="http://t") as c:
        resp = await c.get("/missing")

    assert resp.status_code == 404
    assert resp.json() == {
        "error": {"code": "not_found", "message": "Ticket not found", "details": None}
    }


async def test_validation_error_has_standard_shape():
    async with AsyncClient(transport=ASGITransport(app=_error_app()), base_url="http://t") as c:
        resp = await c.get("/typed", params={"n": "abc"})

    body = resp.json()
    assert resp.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["field"] == "query.n"


async def test_unknown_route_uses_standard_shape(client):
    resp = await client.get("/does-not-exist")

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_page_computes_page_count():
    assert Page[int](items=[1, 2], total=45, page=1, size=20).pages == 3
    assert Page[int](items=[], total=0, page=1, size=20).pages == 0


def test_password_hashing_round_trip():
    hashed = hash_password("correct horse battery staple")

    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", hashed)
    assert not verify_password("wrong", hashed)


def test_metadata_contains_all_tables():
    assert set(Base.metadata.tables) == {
        "users",
        "moderator_skills",
        "tickets",
        "ticket_comments",
        "otp_codes",
        "refresh_tokens",
        "model_quota_state",
        "sent_emails",
    }
