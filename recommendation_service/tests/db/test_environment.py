import json
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_compose_is_local_postgres_with_persistent_storage():
    config = json.loads((ROOT / "compose.recommendation.yml").read_text(encoding="utf-8"))
    database = config["services"]["recommendation-db"]
    assert database["image"].startswith("postgres:16")
    assert database["ports"] == ["127.0.0.1:55432:5432"]
    assert database["volumes"] == ["recommendation_pgdata:/var/lib/postgresql/data"]
    assert database["environment"]["POSTGRES_PASSWORD"].startswith("${RECOMMENDATION_DB_PASSWORD:?")
    assert database["healthcheck"]["test"][0] == "CMD-SHELL"


def test_environment_requires_explicit_test_database(monkeypatch):
    from recommendation_service.database.connection import test_database_url
    monkeypatch.delenv("RECOMMENDATION_TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("RECOMMENDATION_DATABASE_URL", "postgresql+psycopg://user:secret@localhost/live")
    with pytest.raises(ValueError, match="test database"):
        test_database_url()
    monkeypatch.setenv("RECOMMENDATION_TEST_DATABASE_URL", "postgresql+psycopg://user:secret@localhost/live")
    with pytest.raises(ValueError, match="_test"):
        test_database_url()


def test_actual_postgresql_is_reachable():
    from recommendation_service.database.connection import create_db_engine, test_database_url
    from sqlalchemy import text
    if not os.getenv("RECOMMENDATION_TEST_DATABASE_URL"):
        pytest.skip("Explicit PostgreSQL test URL not set; actual server not verified")
    engine = create_db_engine(test_database_url())
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT version() LIKE 'PostgreSQL%'")).scalar_one()
    finally:
        engine.dispose()
