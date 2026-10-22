import math
import os
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError, DataError
from recommendation_service.database.schema import initialize_schema, metadata, releases, regions, observations, assignments, SchemaMismatch
from recommendation_service.database.connection import create_db_engine, test_database_url as get_test_database_url


@pytest.fixture
def engine():
    if not os.getenv("RECOMMENDATION_TEST_DATABASE_URL"):
        pytest.skip("Actual PostgreSQL test URL not set")
    db = create_db_engine(get_test_database_url())
    initialize_schema(db)
    try:
        yield db
    finally:
        db.dispose()


def test_schema_declares_four_tables_and_no_public_dependencies():
    assert {t.name for t in metadata.tables.values()} == {"releases","regions","observations","assignments"}
    assert all(t.schema == "recommendation" for t in metadata.tables.values())
    assert all(fk.target_fullname.startswith("recommendation.") for t in metadata.tables.values() for fk in t.foreign_keys)


def test_schema_can_initialize_twice_without_data_loss(engine):
    initialize_schema(engine)
    initialize_schema(engine)
    assert set(inspect(engine).get_table_names(schema="recommendation")) == {"releases","regions","observations","assignments"}


def seed(conn):
    from uuid import uuid4
    key = "snapshot-" + uuid4().hex[:16]
    conn.execute(releases.insert().values(release_id=key,target_month="2026-10",state="draft",is_active=False,
        payload_hash="a"*64,dataset_metadata={},declared_regions=1))
    conn.execute(regions.insert().values(release_id=key,region_code="110515",region_name="test",sigungu_code="11110"))
    return key


@pytest.mark.parametrize("score",[-1,101,float("nan"),float("inf"),float("-inf")])
def test_score_range_and_region_identity_constraints(engine,score):
    with engine.connect() as conn:
        tx=conn.begin()
        try:
            key=seed(conn)
            with pytest.raises(IntegrityError):
                conn.execute(observations.insert().values(release_id=key,domain="safety",score_level="dong",score_code="110515",score=score,evidence={}))
        finally:tx.rollback()


@pytest.mark.parametrize("code",["1111051500","11110","abcdef"])
def test_invalid_region_identity_rejected(engine,code):
    with engine.connect() as conn:
        tx=conn.begin()
        try:
            key=seed(conn)
            with pytest.raises((IntegrityError, DataError)):
                conn.execute(regions.insert().values(release_id=key,region_code=code,region_name="test",sigungu_code="11110"))
        finally:tx.rollback()


def test_assignment_foreign_keys(engine):
    with engine.connect() as conn:
        tx=conn.begin()
        try:
            key=seed(conn)
            with pytest.raises(IntegrityError):
                conn.execute(assignments.insert().values(release_id=key,region_code="110515",sigungu_code="11110",domain="comfort",score_level="sigungu",score_code="11110"))
        finally:tx.rollback()


def test_only_one_active_release(engine):
    with engine.connect() as conn:
        tx=conn.begin()
        try:
            conn.execute(releases.update().values(is_active=False))
            first=seed(conn);second=seed(conn)
            conn.execute(releases.update().where(releases.c.release_id==first).values(state="ready",is_active=True))
            with pytest.raises(IntegrityError):
                conn.execute(releases.update().where(releases.c.release_id==second).values(state="ready",is_active=True))
        finally:tx.rollback()


def test_existing_incompatible_schema_rejected(engine):
    with engine.begin() as conn:
        # Transactional DDL rollback restores this test-only table.
        conn.execute(text("ALTER TABLE recommendation.regions RENAME COLUMN region_name TO invalid_name"))
        try:
            with pytest.raises(SchemaMismatch):initialize_schema(conn)
        finally:
            conn.execute(text("ALTER TABLE recommendation.regions RENAME COLUMN invalid_name TO region_name"))
