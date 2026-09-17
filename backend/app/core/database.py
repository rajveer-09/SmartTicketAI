from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.db_url import to_async_url


class DatabaseNotConfiguredError(RuntimeError):
    pass


def build_engine(raw_url: str) -> AsyncEngine:
    if not raw_url:
        raise DatabaseNotConfiguredError("DATABASE_URL is not set. Add it to backend/.env.")
    url, connect_args = to_async_url(raw_url)
    return create_async_engine(
        url,
        echo=settings.db_echo,
        pool_pre_ping=True,  # Neon suspends idle computes; drop dead connections
        pool_recycle=300,
        connect_args=connect_args,
    )


@lru_cache
def get_engine() -> AsyncEngine:
    return build_engine(settings.database_url)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, autoflush=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, rolled back on error."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
