import asyncio
import pytest
from pydantic import ValidationError
from recommendation_service.services.ai_recommendation.application import RecommendationApplication,RegionNotFound
from recommendation_service.services.ai_recommendation.api_schemas import SliderRequest,CompareRequest,ExplainRequest
from recommendation_service.services.ai_recommendation.snapshot_service import recommend_snapshots


class MemoryRepository:
    def __init__(self,dataset):self.dataset=dataset
    def load_dataset(self,release_id=None):return self.dataset.model_copy(deep=True)


def app(dataset):return RecommendationApplication(MemoryRepository(dataset))


def test_application_reuses_weighted_engine_and_filters_before_ranking(source_dataset):
    request=SliderRequest(weights=dict.fromkeys(source_dataset.available_domains,20),sigungu_code="11110")
    actual=app(source_dataset).recommend(request)
    selected=source_dataset.model_copy(update={"regions":[r for r in source_dataset.regions if r.sigungu_code=="11110"]})
    expected=recommend_snapshots(selected,weights=request.weights.model_dump())
    assert actual["recommendation"]==expected.model_dump(mode="json")
    assert actual["rank_scope"]=="sigungu"


@pytest.mark.parametrize("weights",[{}, {"safety":100},dict.fromkeys(["economy","energy","comfort","health","safety"],0),
    {"economy":-1,"energy":1,"comfort":1,"health":1,"safety":1},
    {"economy":101,"energy":1,"comfort":1,"health":1,"safety":1},
    {"economy":float("nan"),"energy":1,"comfort":1,"health":1,"safety":1}])
def test_api_slider_contract_rejects_bad_or_missing_weights(weights):
    with pytest.raises(ValidationError):SliderRequest(weights=weights)


def test_api_slider_contract_rejects_bad_codes_and_top_k(source_dataset):
    weights=dict.fromkeys(source_dataset.available_domains,20)
    with pytest.raises(ValidationError):SliderRequest(weights=weights,top_k=6)
    with pytest.raises(ValidationError):SliderRequest(weights=weights,sigungu_code="1111051500")
    with pytest.raises(ValidationError):CompareRequest(weights=weights,region_codes=["110515","110515"])


def test_district_summary_is_explicit_and_null_is_not_zero(source_dataset):
    service=app(source_dataset)
    result=service.scores(None,"11110")
    assert result["count"]==sum(r.sigungu_code=="11110" for r in source_dataset.regions)
    assert result["items"][0]["region_code"]=="110515"
    assert "details" not in result["items"][0]["domain_metadata"]["economy"]
    assert result["snapshot_version"]==source_dataset.snapshot_version
    districts=service.districts()
    assert len(districts["items"])==25
    assert districts["aggregation"]=="mean_of_dong_scores"
    assert all(d["region_count"]>0 for d in districts["items"])


def test_comparison_and_single_explanation_have_explicit_rank_scope(source_dataset):
    service=app(source_dataset);weights=dict.fromkeys(source_dataset.available_domains,20)
    codes=[r.region_code for r in source_dataset.regions[:2]]
    compared=service.compare(CompareRequest(weights=weights,region_codes=codes))
    assert compared["rank_scope"]=="selected_regions"
    assert compared["snapshot_version"]==source_dataset.snapshot_version
    explanation=asyncio.run(service.explain(ExplainRequest(weights=weights,region_codes=[codes[0]]),None))
    assert explanation["rank_scope"]=="selected_regions"
    assert explanation["explanation"]["generation_status"]=="fallback"
    with pytest.raises(RegionNotFound):service.region("999999",None)


def test_application_reads_release_from_postgres(db_engine,source_dataset):
    from recommendation_service.database.repository import SnapshotRepository
    repo=SnapshotRepository(db_engine);repo.import_dataset(source_dataset,activate=True)
    weights=dict.fromkeys(source_dataset.available_domains,20)
    assert RecommendationApplication(repo).recommend(SliderRequest(weights=weights))["recommendation"]==recommend_snapshots(source_dataset,weights=weights).model_dump(mode="json")


def test_async_explanation_moves_database_work_off_event_loop(source_dataset):
    import threading
    event_thread=threading.get_ident()
    class ThreadAwareRepository(MemoryRepository):
        def load_dataset(self,release_id=None):
            assert threading.get_ident()!=event_thread
            return super().load_dataset(release_id)
    service=RecommendationApplication(ThreadAwareRepository(source_dataset))
    request=ExplainRequest(weights=dict.fromkeys(source_dataset.available_domains,20),region_codes=["110515"])
    assert asyncio.run(service.explain(request,None))["explanation"]["generation_status"]=="fallback"


@pytest.mark.parametrize("weights",[
    dict(economy=100,energy=100,comfort=100,health=100,safety=100),
    dict(economy=0,energy=0,comfort=0,health=0,safety=100),
    dict(economy=20,energy=10,comfort=50,health=10,safety=10),
])
def test_database_and_file_rankings_match_for_slider_profiles(db_engine,source_dataset,weights):
    from recommendation_service.database.repository import SnapshotRepository
    repo=SnapshotRepository(db_engine);repo.import_dataset(source_dataset,activate=True)
    actual=RecommendationApplication(repo).recommend(SliderRequest(weights=weights))["recommendation"]
    assert actual==recommend_snapshots(source_dataset,weights=weights).model_dump(mode="json")


def test_district_missing_values_keep_coverage_and_are_not_zero(source_dataset):
    dataset=source_dataset.model_copy(deep=True)
    rows=[r for r in dataset.regions if r.sigungu_code=="11110"]
    for row in rows:row.category_scores.energy=None
    rows[0].category_scores.economy=None
    result=app(dataset).districts()
    district=next(d for d in result["items"] if d["sigungu_code"]=="11110")
    assert district["valid_region_counts"]["economy"]==len(rows)-1
    assert district["category_scores"]["economy"]==pytest.approx(sum(r.category_scores.economy for r in rows[1:])/(len(rows)-1))
    assert district["valid_region_counts"]["energy"]==0
    assert district["category_scores"]["energy"] is None
    assert district["personalized_score_100"] is None
