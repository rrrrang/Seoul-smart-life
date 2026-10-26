import math

import pytest
from pydantic import ValidationError

from services.ai_recommendation.recommendation import (
    calculate_total_score, compare_regions, normalize_weights, recommend_regions,
)
from services.ai_recommendation.schemas import RegionScore


def region(code, **scores):
    return {"region_code": code, "region_name": code, "category_scores": scores}


def test_normalization_and_hand_calculated_score():
    weights = {"economy": 10, "energy": 10, "comfort": 30, "health": 20, "safety": 30}
    normalized = normalize_weights(weights)
    assert normalized.safety == pytest.approx(0.3)
    assert sum(normalized.model_dump().values()) == pytest.approx(1)
    assert calculate_total_score(
        {"economy": 80, "energy": 70, "comfort": 75, "health": 90, "safety": 85}, weights
    ) == pytest.approx(81)


@pytest.mark.parametrize("weights", [
    {"safety": -1}, {"economy": 0, "energy": 0, "comfort": 0, "health": 0, "safety": 0},
    {"safety": float("nan")}, {"safety": float("inf")}, {"rent": 10}, {"safety": True},
])
def test_invalid_weights_are_rejected(weights):
    with pytest.raises((ValueError, ValidationError)):
        normalize_weights(weights)


def test_large_finite_weights_do_not_overflow():
    weights = dict.fromkeys(["economy", "energy", "comfort", "health", "safety"], 1e308)
    result = normalize_weights(weights)
    assert result.safety == pytest.approx(0.2)
    assert math.isfinite(result.safety)


def test_top_five_ties_and_strengths_weaknesses():
    rows = [region(str(n), economy=60, energy=70, comfort=80, health=90, safety=100)
            for n in range(7, 0, -1)]
    result = recommend_regions(rows, {"weights": {"economy": 1, "energy": 1, "comfort": 1, "health": 1, "safety": 1}})
    assert [item.region_code for item in result.items] == ["1", "2", "3", "4", "5"]
    assert result.items[0].total_score == 80
    assert result.items[0].strengths[0].domain == "safety"
    assert result.items[0].weaknesses[0].domain == "economy"
    assert result.items[0].sources == []
    assert "SOURCE_METADATA_MISSING" in result.warnings


def test_missing_score_is_excluded_only_when_needed():
    rows = [region("a", safety=90), region("b", safety=80, health=100)]
    only_safety = {"economy": 0, "energy": 0, "comfort": 0, "health": 0, "safety": 1}
    result = recommend_regions(rows, {"weights": only_safety})
    assert [item.region_code for item in result.items] == ["a", "b"]
    result = recommend_regions(rows, {"weights": only_safety, "min_scores": {"health": 90}})
    assert [item.region_code for item in result.items] == ["b"]
    assert result.excluded[0].reason == "missing_scores"
    with pytest.raises(ValueError):
        calculate_total_score({"safety": None}, only_safety)


def test_zero_score_is_not_missing_and_no_candidate_is_valid():
    weights = {"economy": 0, "energy": 0, "comfort": 0, "health": 0, "safety": 1}
    assert recommend_regions([region("a", safety=0)], {"weights": weights}).items[0].total_score == 0
    assert recommend_regions([], {"weights": weights}).items == []
    assert recommend_regions([region("a", safety=0)], {"weights": weights, "min_scores": {"safety": 1}}).items == []


@pytest.mark.parametrize("value", [-1, 101, float("nan"), float("inf"), True])
def test_bad_scores_are_not_silently_dropped(value):
    with pytest.raises(ValidationError):
        recommend_regions([region("a", safety=value)], {"weights": {"safety": 1}})


def test_duplicates_and_mixed_units_versions_are_rejected():
    a = region("a", safety=90)
    with pytest.raises(ValueError):
        recommend_regions([a, a], {"weights": {"safety": 1}})
    b = {**region("b", safety=90), "spatial_unit": "district"}
    a["spatial_unit"] = "administrative_dong"
    with pytest.raises(ValueError):
        recommend_regions([a, b], {"weights": {"safety": 1}})
    with pytest.raises(ValueError):
        recommend_regions([{**a, "score_version": "v1"}, {**a, "region_code": "b", "score_version": "v2"}], {"weights": {"safety": 1}})


def test_district_sources_cannot_be_claimed_as_dong_scores():
    with pytest.raises(ValidationError):
        RegionScore.model_validate({**region("a", safety=90), "spatial_unit": "administrative_dong",
            "sources": [{"source": "public", "document_title": "crime", "reference_year": 2025,
                         "original_spatial_unit": "district", "is_mock": False}]})


def test_compare_returns_selected_regions_and_differences():
    rows = [region("a", safety=90, health=60), region("b", safety=80, health=75)]
    result = compare_regions(rows, ["a", "b"], {"weights": {"safety": 1, "health": 1, "economy": 0, "energy": 0, "comfort": 0}})
    assert result.baseline_region_code == "a"
    assert result.differences["b"]["safety"] == -10
    assert result.differences["b"]["health"] == 15
    with pytest.raises(ValueError):
        compare_regions(rows, ["missing"], {"weights": {"safety": 1}})


@pytest.mark.parametrize("top_k", [0, 6, True])
def test_invalid_top_k(top_k):
    with pytest.raises(ValidationError):
        recommend_regions([], {"weights": {"safety": 1}, "top_k": top_k})


def test_tiny_positive_weight_still_requires_observation():
    weights = {"economy": 1e308, "energy": 0, "comfort": 0, "health": 0, "safety": 1e-308}
    result = recommend_regions([region("a", economy=100)], {"weights": weights})
    assert result.items == []
    assert result.excluded[0].domains == ["safety"]
    with pytest.raises(ValueError):
        calculate_total_score({"economy": 100}, weights)


def test_copied_invalid_score_model_is_revalidated():
    from services.ai_recommendation.schemas import CategoryScores
    bad = CategoryScores(safety=50).model_copy(update={"safety": 1000})
    with pytest.raises(ValueError):
        calculate_total_score(bad, {"economy":0,"energy":0,"comfort":0,"health":0,"safety":1})


def test_copied_invalid_request_and_nested_scores_are_revalidated():
    from services.ai_recommendation.schemas import CategoryScores, RecommendationRequest
    bad = RecommendationRequest().model_copy(update={"top_k": 0})
    with pytest.raises(ValueError):
        recommend_regions([], bad)
    row = RegionScore.model_validate(region("test", safety=50))
    row.category_scores.__dict__["safety"] = -100
    with pytest.raises(ValueError):
        recommend_regions([row], {"weights":{"economy":0,"energy":0,"comfort":0,"health":0,"safety":1}})
