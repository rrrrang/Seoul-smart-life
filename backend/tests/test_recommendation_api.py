import pytest
from fastapi.testclient import TestClient
from backend.app.main import create_app
from recommendation_service.database.repository import SnapshotRepository,RepositoryUnavailable


@pytest.fixture
def client(db_engine,source_dataset):
    repository=SnapshotRepository(db_engine);repository.import_dataset(source_dataset,activate=True)
    with TestClient(create_app(repository=repository)) as client:yield client


def test_real_db_status_regions_scores_and_rankings(client):
    status=client.get("/api/recommendation/status")
    assert status.status_code==200 and status.json()["database"]=="ready"
    districts=client.get("/api/recommendation/districts").json()
    assert len(districts["items"])==25
    regions=client.get("/api/recommendation/regions",params={"sigungu_code":"11110"})
    assert regions.status_code==200 and all(len(r["region_code"])==6 for r in regions.json()["items"])
    scores=client.get("/api/recommendation/scores").json()
    assert scores["count"]==427 and scores["is_mock"] is False
    result=client.post("/api/recommendation/recommendations",json={"weights":dict.fromkeys(["economy","energy","comfort","health","safety"],20),"sigungu_code":"11110"})
    assert result.status_code==200 and result.json()["rank_scope"]=="sigungu"
    assert len(result.json()["recommendation"]["items"])==5


def test_api_compare_detail_and_default_explanation(client):
    weights=dict.fromkeys(["economy","energy","comfort","health","safety"],20)
    detail=client.get("/api/recommendation/regions/110515")
    assert detail.status_code==200 and detail.json()["item"]["domain_metadata"]["comfort"]["original_spatial_units"]==["sigungu"]
    compared=client.post("/api/recommendation/compare",json={"weights":weights,"region_codes":["110515","110530"]})
    assert compared.status_code==200 and len(compared.json()["items"])==2
    explanation=client.post("/api/recommendation/explanations",json={"weights":weights,"region_codes":["110515"]})
    assert explanation.status_code==200 and explanation.json()["explanation"]["generation_status"]=="fallback"


def test_bad_input_and_missing_region_or_release_are_distinct(client):
    assert client.post("/api/recommendation/recommendations",json={"weights":{"safety":100}}).status_code==422
    assert client.get("/api/recommendation/regions/1111051500").status_code==422
    assert client.get("/api/recommendation/regions/999999").status_code==404
    assert client.get("/api/recommendation/scores",params={"release_id":"snapshot-"+"0"*16}).status_code==404
    assert client.get("/api/recommendation/scores",params={"weights":"not json"}).status_code==422


def test_database_failure_is_503_without_mock_or_connection_leak():
    class Broken:
        def load_dataset(self,*args):raise RepositoryUnavailable("DO_NOT_LEAK secret connection")
        def get_status(self):raise RepositoryUnavailable("DO_NOT_LEAK secret connection")
    with TestClient(create_app(repository=Broken())) as client:
        response=client.get("/api/recommendation/scores")
        assert response.status_code==503 and "DO_NOT_LEAK" not in response.text
        assert "is_mock" not in response.json()


def test_no_active_release_is_503(db_engine):
    with TestClient(create_app(repository=SnapshotRepository(db_engine))) as client:
        assert client.get("/api/recommendation/status").status_code==503
        assert client.get("/api/recommendation/scores").status_code==503


def test_llm_failure_retains_database_computed_facts(db_engine,source_dataset):
    from recommendation_service.services.ai_recommendation.llm_service import LLMError
    class FailedClient:
        async def structured(self,*args):raise LLMError("rate_limit",status_code=429)
    repository=SnapshotRepository(db_engine);repository.import_dataset(source_dataset,activate=True)
    with TestClient(create_app(repository=repository,explanation_client=FailedClient())) as client:
        result=client.post("/api/recommendation/explanations",json={"weights":dict.fromkeys(["economy","energy","comfort","health","safety"],20),"region_codes":["110515"]})
        assert result.status_code==200
        explanation=result.json()["explanation"]
        assert explanation["generation_status"]=="fallback"
        assert explanation["diagnostics"][0]["code"]=="rate_limit"
        assert explanation["items"][0]["category_scores"]==source_dataset.regions[0].category_scores.model_dump()
