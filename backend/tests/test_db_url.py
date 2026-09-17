from app.core.db_url import to_async_url

NEON_POOLED = (
    "postgresql://alice:secret@ep-cool-lab-123-pooler.us-east-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def test_neon_pooled_url_is_converted_for_asyncpg():
    url, connect_args = to_async_url(NEON_POOLED)

    assert url.drivername == "postgresql+asyncpg"
    assert dict(url.query) == {}
    assert url.password == "secret"
    assert connect_args == {
        "ssl": "require",
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }


def test_neon_direct_url_requires_ssl_without_disabling_cache():
    url, connect_args = to_async_url(
        "postgres://alice:secret@ep-cool-lab-123.us-east-2.aws.neon.tech/neondb"
    )

    assert url.drivername == "postgresql+asyncpg"
    assert connect_args == {"ssl": "require"}


def test_local_url_without_ssl():
    url, connect_args = to_async_url("postgresql+asyncpg://u:p@localhost:5432/db")

    assert url.host == "localhost"
    assert connect_args == {}


def test_other_query_params_are_kept():
    url, _ = to_async_url("postgresql://u:p@localhost/db?sslmode=disable&application_name=api")

    assert dict(url.query) == {"application_name": "api"}
