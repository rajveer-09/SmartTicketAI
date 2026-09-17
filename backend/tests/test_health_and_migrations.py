"""Tests that need a real Postgres (TEST_DATABASE_URL). Skipped otherwise."""

import asyncio

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app.core import database
from app.core.config import settings
from app.models import Base
from tests.conftest import alembic_config


async def test_health_reports_unavailable_without_database(client, monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    database.get_engine.cache_clear()
    try:
        resp = await client.get("/api/health")
    finally:
        database.get_engine.cache_clear()

    assert resp.status_code == 503
    assert resp.json() == {"status": "degraded", "database": "error"}


@pytest.mark.usefixtures("test_engine")
async def test_health_ok_with_database(client, monkeypatch):
    monkeypatch.setattr(settings, "database_url", settings.test_database_url)
    database.get_engine.cache_clear()
    try:
        resp = await client.get("/api/health")
        await database.dispose_engine()
    finally:
        database.get_engine.cache_clear()

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}


async def test_migrations_match_models_and_downgrade_cleanly(test_engine):
    def _diff(sync_conn):
        ctx = MigrationContext.configure(sync_conn, opts={"compare_type": True})
        return compare_metadata(ctx, Base.metadata)

    async with test_engine.connect() as conn:
        diff = await conn.run_sync(_diff)
    assert diff == [], f"Migration and models differ: {diff}"

    cfg = alembic_config(settings.test_database_url)
    # env.py calls asyncio.run(), so run Alembic outside this event loop.
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    # Enum types were recreated with new OIDs; drop pooled connections that cached the old ones.
    await test_engine.dispose()
