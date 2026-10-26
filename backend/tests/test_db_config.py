import asyncio

import pytest

from app.core.config import Settings
from app.db.session import database_url_for_settings


def test_database_url_uses_psycopg_and_decodes_encoded_credentials():
    settings = Settings(
        _env_file=None,
        database_url="postgresql://postgres:p%40ss%3Aword@localhost:5432/udyamai?sslmode=require",
    )

    url = database_url_for_settings(settings)

    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss:word"
    assert url.query["sslmode"] == "require"


def test_production_postgres_url_requires_ssl():
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_secret_key="a" * 40,
        database_url="postgresql://user:password@localhost:5432/udyamai",
    )

    url = database_url_for_settings(settings)

    assert url.drivername == "postgresql+psycopg"
    assert url.query["sslmode"] == "require"


def test_remote_postgres_url_uses_ssl_outside_production():
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:password@db.example.com:5432/udyamai",
    )

    url = database_url_for_settings(settings)

    assert url.query["sslmode"] == "require"


def test_production_rejects_sqlite():
    settings = Settings(
        _env_file=None,
        app_env="production",
        auth_secret_key="a" * 40,
        database_url="sqlite:///./udyamai.db",
    )

    with pytest.raises(ValueError, match="Production requires a PostgreSQL"):
        database_url_for_settings(settings)


def test_invalid_database_url_error_does_not_include_credentials():
    secret = "private-password"
    settings = Settings(
        _env_file=None,
        database_url=f"postgresql://user:{secret}",
    )

    with pytest.raises(ValueError) as error:
        database_url_for_settings(settings)
    assert secret not in str(error.value)


def test_production_startup_fails_safely_when_database_is_unavailable(monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app import main

    secret = "private-database-detail"

    class UnavailableConnection:
        def __enter__(self):
            raise OperationalError("SELECT 1", {}, Exception(secret))

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(main.settings, "app_env", "production")
    monkeypatch.setattr(main.engine, "connect", lambda: UnavailableConnection())

    async def start_application():
        async with main.lifespan(main.app):
            pytest.fail("Startup should not continue without the production database.")

    with pytest.raises(RuntimeError) as error:
        asyncio.run(start_application())
    assert "private-database-detail" not in str(error.value)
