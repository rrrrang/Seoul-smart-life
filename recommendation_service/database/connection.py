"""Validated PostgreSQL connections. Never log connection URLs or credentials."""
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url


def create_db_engine(url: str) -> Engine:
    if not isinstance(url, str) or not url.strip():
        raise ValueError("PostgreSQL URL is required")
    try:
        parsed = make_url(url)
    except Exception:
        raise ValueError("Invalid PostgreSQL configuration") from None
    if parsed.drivername != "postgresql+psycopg" or not parsed.database:
        raise ValueError("Use an explicit postgresql+psycopg database URL")
    return create_engine(parsed, pool_pre_ping=True, pool_size=5, max_overflow=5,
                         connect_args={"connect_timeout": 5}, hide_parameters=True)


def test_database_url() -> str:
    value = os.environ.get("RECOMMENDATION_TEST_DATABASE_URL", "")
    if not value:
        raise ValueError("An explicit test database URL is required")
    try:
        parsed = make_url(value)
    except Exception:
        raise ValueError("Invalid test database configuration") from None
    if not parsed.database or not parsed.database.endswith("_test"):
        raise ValueError("Test database name must end with _test")
    if parsed.drivername != "postgresql+psycopg":
        raise ValueError("Test database must use PostgreSQL psycopg")
    return value
