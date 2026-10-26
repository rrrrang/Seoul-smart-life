import os
from pathlib import Path
import pytest
from sqlalchemy import text
from recommendation_service.database.connection import create_db_engine, test_database_url as get_test_database_url
from recommendation_service.database.schema import initialize_schema
from recommendation_service.services.ai_recommendation.snapshot_service import load_snapshot_dataset


@pytest.fixture(scope="session")
def source_dataset():
    root=Path(__file__).resolve().parents[2]
    return load_snapshot_dataset(root/"ai_modeling",target_month="2026-10",
        domains=["economy","energy","comfort","health","safety"],
        allow_provisional=True,allow_context_scores=True)


@pytest.fixture
def db_engine():
    if not os.getenv("RECOMMENDATION_TEST_DATABASE_URL"):
        pytest.skip("Actual PostgreSQL test URL not set")
    engine=create_db_engine(get_test_database_url())
    initialize_schema(engine)
    with engine.begin() as conn:
        assert conn.execute(text("SELECT current_database()")).scalar_one().endswith("_test")
        conn.execute(text("TRUNCATE recommendation.assignments, recommendation.observations, recommendation.regions, recommendation.releases"))
    try:yield engine
    finally:engine.dispose()
