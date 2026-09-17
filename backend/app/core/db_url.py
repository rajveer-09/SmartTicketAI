"""Turn a Postgres URL (for example the one Neon's console gives you) into what
SQLAlchemy + asyncpg expect.

Neon hands out URLs like:
    postgresql://user:pass@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require&channel_binding=require

asyncpg does not understand `sslmode` / `channel_binding` query params, so they are
removed and SSL is passed through connect_args instead. Neon's pooled endpoint
(`-pooler` in the host) runs PgBouncer in transaction mode, which breaks asyncpg's
prepared-statement cache, so the cache is disabled there.
"""

from typing import Any

from sqlalchemy.engine import URL, make_url

_LIBPQ_ONLY_PARAMS = {"sslmode", "channel_binding", "ssl"}
_SSL_OFF = {"disable", "allow"}


def to_async_url(raw_url: str) -> tuple[URL, dict[str, Any]]:
    url = make_url(raw_url)
    if url.drivername in {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2"}:
        url = url.set(drivername="postgresql+asyncpg")

    query = dict(url.query)
    sslmode = query.get("sslmode") or query.get("ssl")
    url = url.set(query={k: v for k, v in query.items() if k not in _LIBPQ_ONLY_PARAMS})

    connect_args: dict[str, Any] = {}
    host = url.host or ""
    is_neon = host.endswith(".neon.tech")

    if (sslmode and sslmode not in _SSL_OFF) or (is_neon and not sslmode):
        connect_args["ssl"] = "require"

    if "-pooler" in host:
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0

    return url, connect_args
