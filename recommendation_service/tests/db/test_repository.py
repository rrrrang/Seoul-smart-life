from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import pytest
from sqlalchemy import select,func,event,text
from recommendation_service.database.repository import SnapshotRepository,ReleaseConflict,ReleaseNotFound,RepositoryUnavailable
from recommendation_service.database.schema import releases,regions,observations,assignments


def another(dataset):
    return dataset.model_copy(deep=True,update={"snapshot_version":"snapshot-"+uuid4().hex[:16]})


def test_database_roundtrip_preserves_every_score_and_provenance(db_engine,source_dataset):
    repo=SnapshotRepository(db_engine)
    key=repo.import_dataset(source_dataset,activate=True)
    assert key==source_dataset.snapshot_version
    assert repo.load_dataset().model_dump()==source_dataset.model_dump()


def test_comfort_uses_25_observations_and_427_assignments(db_engine,source_dataset):
    repo=SnapshotRepository(db_engine);repo.import_dataset(source_dataset,activate=True)
    with db_engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(regions)).scalar_one()==427
        assert conn.execute(select(func.count()).select_from(observations)).scalar_one()==1733
        assert conn.execute(select(func.count()).select_from(assignments)).scalar_one()==2135
        assert conn.execute(select(func.count()).select_from(observations).where(observations.c.domain=="comfort")).scalar_one()==25


def test_same_release_is_idempotent(db_engine,source_dataset):
    repo=SnapshotRepository(db_engine)
    repo.import_dataset(source_dataset,activate=True);repo.import_dataset(source_dataset,activate=True)
    assert repo.get_status()["release_count"]==1


def test_same_id_different_payload_rejected(db_engine,source_dataset):
    repo=SnapshotRepository(db_engine);repo.import_dataset(source_dataset,activate=True)
    changed=source_dataset.model_copy(deep=True)
    changed.regions[0].category_scores.economy=25
    with pytest.raises(ReleaseConflict):repo.import_dataset(changed,activate=True)
    assert repo.load_dataset().model_dump()==source_dataset.model_dump()


def test_failed_import_keeps_previous_active_release(db_engine,source_dataset):
    repo=SnapshotRepository(db_engine);repo.import_dataset(source_dataset,activate=True)
    new=another(source_dataset)
    def fail(conn,cursor,statement,params,context,many):
        if statement.startswith("INSERT INTO recommendation.assignments"):
            raise RuntimeError("injected database failure")
    event.listen(db_engine,"before_cursor_execute",fail)
    try:
        with pytest.raises(RuntimeError):repo.import_dataset(new,activate=True)
    finally:event.remove(db_engine,"before_cursor_execute",fail)
    assert repo.load_dataset().snapshot_version==source_dataset.snapshot_version
    assert repo.get_status()["release_count"]==1


def test_concurrent_activation_has_single_active_release(db_engine,source_dataset):
    repo=SnapshotRepository(db_engine)
    first=repo.import_dataset(source_dataset);second=repo.import_dataset(another(source_dataset))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(repo.activate_release,[first,second]))
    with db_engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(releases).where(releases.c.is_active)).scalar_one()==1
    assert repo.load_dataset().snapshot_version in [first,second]


def test_reader_never_mixes_releases(db_engine,source_dataset):
    repo=SnapshotRepository(db_engine);repo.import_dataset(source_dataset,activate=True)
    newer=another(source_dataset);newer.regions[0].category_scores.economy=24
    repo.import_dataset(newer)
    changed=False
    def switch(conn,cursor,statement,params,context,many):
        nonlocal changed
        if not changed and statement.startswith("SELECT") and "releases.is_active" in statement:
            changed=True;repo.activate_release(newer.snapshot_version)
    event.listen(db_engine,"after_cursor_execute",switch)
    try:loaded=repo.load_dataset()
    finally:event.remove(db_engine,"after_cursor_execute",switch)
    assert loaded.snapshot_version in [source_dataset.snapshot_version,newer.snapshot_version]
    expected=source_dataset if loaded.snapshot_version==source_dataset.snapshot_version else newer
    assert loaded.model_dump()==expected.model_dump()


def test_missing_release_and_empty_active_are_explicit(db_engine):
    repo=SnapshotRepository(db_engine)
    with pytest.raises(RepositoryUnavailable):repo.load_dataset()
    with pytest.raises(ReleaseNotFound):repo.load_dataset("snapshot-"+"0"*16)


def test_comfort_cannot_merge_conflicting_district_evidence(db_engine,source_dataset):
    dataset=source_dataset.model_copy(deep=True)
    dataset.regions[0].category_scores.comfort=99
    with pytest.raises(ValueError):SnapshotRepository(db_engine).import_dataset(dataset)


def test_database_payload_tampering_is_detected(db_engine,source_dataset):
    repo=SnapshotRepository(db_engine);repo.import_dataset(source_dataset,activate=True)
    with db_engine.begin() as conn:
        conn.execute(observations.update().where(observations.c.domain=="economy",observations.c.score_code==source_dataset.regions[0].region_code).values(score=25))
    with pytest.raises(ReleaseConflict):repo.load_dataset()
