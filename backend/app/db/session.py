from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings, get_settings


def database_url_for_settings(settings: Settings) -> URL:
    try:
        url = make_url(settings.database_url)
    except (ArgumentError, ValueError):
        raise ValueError("DATABASE_URL is not a valid SQLAlchemy URL.") from None

    if url.drivername == "sqlite":
        requires_ssl = settings.app_env.lower() == "production" or url.host not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if requires_ssl:
            raise ValueError("Production requires a PostgreSQL DATABASE_URL.")
        return url

    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    elif url.drivername != "postgresql+psycopg":
        raise ValueError("DATABASE_URL must use SQLite or PostgreSQL with the psycopg driver.")
    if not url.host or not url.database:
        raise ValueError("DATABASE_URL must include a PostgreSQL host and database name.")

    if settings.app_env.lower() == "production":
        query = dict(url.query)
        sslmode = query.get("sslmode")
        if sslmode and (
            not isinstance(sslmode, str)
            or sslmode.lower() not in {"require", "verify-ca", "verify-full"}
        ):
            raise ValueError("Production PostgreSQL connections must use SSL.")
        query.setdefault("sslmode", "require")
        url = url.set(query=query)
    return url


settings = get_settings()
database_url = database_url_for_settings(settings)
connect_args = {"check_same_thread": False} if database_url.drivername == "sqlite" else {}
engine = create_engine(
    database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_timeout=30,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
