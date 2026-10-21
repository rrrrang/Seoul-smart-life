import asyncio
import json
from pathlib import Path

import httpx
import pytest

from services.ai_recommendation.llm_service import LLMError, OpenRouterClient
from services.ai_recommendation.schemas import EvidenceChunk, EvidenceResult, RecommendationRequest
from services.ai_recommendation.snapshot_service import load_snapshot_dataset, recommend_snapshots
from services.ai_recommendation.snapshot_llm import answer_snapshot_question, generate_snapshot_explanation

ROOT = Path(__file__).resolve().parents[2]
MODELING = ROOT / "ai_modeling"
if not (MODELING / "economy/results/economy_scores.json").exists():
    MODELING = ROOT / ".publish-repo/ai_modeling"


@pytest.fixture(scope="module")
def dataset():
    return load_snapshot_dataset(MODELING, target_month="2026-10", domains=["economy", "energy", "health", "safety"],
                                 allow_provisional=True, allow_context_scores=True)


def run(handler, operation):
    async def invoke():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenRouterClient(api_key="test-secret", model="test/model", http_client=http,
                                      max_retries=0, max_tokens=4096)
            return await operation(client)
    return asyncio.run(invoke())


def reply(payload):
    return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}]})


def extraction(weights=None, priorities=None, unsupported=None):
    return {"weights": weights, "priority_domains": priorities or [], "min_scores": {},
            "unsupported_conditions": unsupported or [], "limitations": []}


def select_from_request(request):
    context = json.loads(json.loads(request.content)["messages"][1]["content"])
    return {"items": [{"region_code": item["region_code"],
                       "strength_domains": [item["strengths"][0]["domain"]],
                       "weakness_domains": [item["weaknesses"][0]["domain"]],
                       "evidence_ids": []} for item in context["recommendation"]["items"]]}


def test_actual_snapshot_explanation_keeps_original_scores_codes_and_provenance(dataset):
    rec = recommend_snapshots(dataset, weights={"economy": 1, "energy": 1, "health": 1, "safety": 1})
    before = rec.model_dump_json()
    result = run(lambda request: reply(select_from_request(request)), lambda client: generate_snapshot_explanation(rec, client))
    assert result.generation_status == "llm"
    assert result.selected_max_points == 80
    assert result.unavailable_domains == ["comfort"]
    assert result.snapshot_version == rec.snapshot_version
    assert [item.region_code for item in result.items] == [item.region_code for item in rec.items]
    for explained, original in zip(result.items, rec.items):
        assert explained.sigungu_code == original.sigungu_code
        assert explained.personalized_score_100 == original.personalized_score_100
        assert explained.domain_points_20 == original.domain_points_20
        assert explained.five_domain_total_points is None
        assert explained.domain_metadata == original.domain_metadata
        assert any("추정" in text for text in explained.limitations)
        assert any("관할" in text for text in explained.limitations)
        assert any("4개 영역" in text and "100점" in text for text in explained.limitations)
        assert "/20" not in explained.advantages + explained.disadvantages
        assert explained.citations == []
    assert before == rec.model_dump_json()


def test_offline_actual_explanation_and_api_failure_use_same_preserved_facts(dataset):
    rec = recommend_snapshots(dataset, weights={"safety": 1})
    offline = asyncio.run(generate_snapshot_explanation(rec))
    failed = run(lambda request: httpx.Response(401), lambda client: generate_snapshot_explanation(rec, client))
    assert offline.generation_status == failed.generation_status == "fallback"
    assert failed.items[0].personalized_score_100 == rec.items[0].personalized_score_100
    assert failed.items[0].domain_metadata == rec.items[0].domain_metadata
    assert failed.diagnostics[0]["code"] == "authentication"
    assert "test-secret" not in failed.model_dump_json()
    assert "하나" in failed.items[0].limitations[0] or any("하나" in text for text in failed.items[0].limitations)


@pytest.mark.parametrize("corruption", ["rank", "evidence", "reversed"])
def test_actual_explanation_rejects_fabricated_outputs(dataset, corruption):
    rec = recommend_snapshots(dataset, weights={"economy": 1, "health": 2, "safety": 3})
    def handler(request):
        plan = select_from_request(request)
        if corruption == "rank":
            plan["items"][0]["rank"] = 999
        elif corruption == "evidence":
            plan["items"][0]["evidence_ids"] = ["fabricated-document"]
        else:
            plan["items"][0]["strength_domains"] = plan["items"][0]["weakness_domains"]
        return reply(plan)
    result = run(handler, lambda client: generate_snapshot_explanation(rec, client))
    assert result.generation_status == "fallback"
    assert result.items[0].rank == 1
    assert result.items[0].personalized_score_100 == rec.items[0].personalized_score_100


def test_actual_question_flow_with_explicit_supported_weights(dataset):
    calls = []
    weights = {"economy": 1, "energy": 1, "comfort": 0, "health": 2, "safety": 3}
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload["response_format"]["json_schema"]["name"])
        if calls[-1] == "PreferenceDraft":
            return reply(extraction(weights=weights, priorities=["safety", "health"]))
        return reply(select_from_request(request))
    result = run(handler, lambda client: answer_snapshot_question("치안 3 건강 2 경제 1 에너지 1 쾌적 0", dataset, client))
    assert result.status == "provisional"
    assert result.preferences.weight_source == "explicit"
    assert result.effective_request.weights.comfort == 0
    assert len(result.recommendation.items) == 5
    assert result.explanation.generation_status == "llm"
    assert result.evidence.status == "no_evidence"
    assert calls == ["PreferenceDraft", "ExplanationPlan"]


def test_unavailable_air_preference_stops_before_recommendation_and_explanation(dataset):
    calls = []
    def handler(request):
        calls.append(request)
        return reply(extraction(priorities=["safety", "comfort"]))
    result = run(handler, lambda client: answer_snapshot_question("치안과 공기가 좋은 곳", dataset, client))
    assert result.status == "needs_confirmation"
    assert result.unavailable_requested_domains == ["comfort"]
    assert result.recommendation is None
    assert result.explanation is None
    assert len(calls) == 1


def test_implicit_defaults_are_scoped_explicitly_without_rejecting_supported_preferences(dataset):
    def handler(request):
        payload = json.loads(request.content)
        if payload["response_format"]["json_schema"]["name"] == "PreferenceDraft":
            return reply(extraction(priorities=["safety"]))
        return reply(select_from_request(request))
    result = run(handler, lambda client: answer_snapshot_question("치안이 좋은 곳", dataset, client))
    assert result.status == "provisional"
    assert result.preferences.weights.comfort == 1
    assert result.effective_request.weights.comfort == 0
    assert result.effective_request.weights.safety == 3
    assert "DEFAULT_WEIGHTS_LIMITED_TO_AVAILABLE_DOMAINS" in result.warnings


def test_confirmed_request_skips_extraction_and_retains_choice(dataset):
    calls = []
    def handler(request):
        calls.append(json.loads(request.content)["response_format"]["json_schema"]["name"])
        return reply(select_from_request(request))
    confirmed = RecommendationRequest(weights={"economy": 0, "energy": 0, "comfort": 0, "health": 0, "safety": 1})
    result = run(handler, lambda client: answer_snapshot_question("치안 추천", dataset, client, confirmed_request=confirmed))
    assert result.status == "confirmed"
    assert result.preferences is None
    assert result.effective_request == confirmed
    assert result.recommendation.selected_domains == ["safety"]
    assert calls == ["ExplanationPlan"]


def test_authentication_failure_requires_explicit_fallback(dataset):
    with pytest.raises(LLMError):
        run(lambda request: httpx.Response(401), lambda client: answer_snapshot_question("추천", dataset, client))
    result = run(lambda request: httpx.Response(401),
                 lambda client: answer_snapshot_question("추천", dataset, client, allow_llm_fallback=True))
    assert result.preferences.extraction_status == "fallback"
    assert result.effective_request.weights.comfort == 0
    assert len(result.recommendation.items) == 5
    assert result.explanation.generation_status == "fallback"


@pytest.mark.parametrize("value", ["false", "true", 1, None])
def test_actual_pipeline_rejects_truthy_non_boolean_options(dataset, value):
    with pytest.raises(ValueError, match="boolean"):
        run(lambda request: pytest.fail("no external call"),
            lambda client: answer_snapshot_question("추천", dataset, client, allow_llm_fallback=value))


def test_unsupported_rent_condition_requires_confirmation(dataset):
    result = run(lambda request: reply(extraction(unsupported=["월세 80만원 이하"])),
                 lambda client: answer_snapshot_question("월세 80만원 이하", dataset, client))
    assert result.status == "needs_confirmation"
    assert result.preferences.unsupported_conditions == ["월세 80만원 이하"]
    assert result.recommendation is None


def test_real_evidence_metadata_is_preserved_when_selected(dataset):
    rec = recommend_snapshots(dataset, weights={"safety": 1})
    doc = EvidenceChunk(chunk_id="actual-doc", text="테스트가 제공한 문서 본문", source="provided-document.pdf",
                        document_title="제공 문서", reference_year=2025)
    def handler(request):
        plan = select_from_request(request)
        for item in plan["items"]:
            item["evidence_ids"] = ["actual-doc"]
        return reply(plan)
    result = run(handler, lambda client: generate_snapshot_explanation(rec, client,
        evidence=EvidenceResult(status="found", chunks=[doc])))
    assert result.items[0].citations == [doc]
    assert "NO_DOCUMENT_EVIDENCE" not in result.warnings


def test_actual_question_top_k_is_respected(dataset):
    def handler(request):
        payload = json.loads(request.content)
        if payload["response_format"]["json_schema"]["name"] == "PreferenceDraft":
            return reply(extraction(priorities=["safety"]))
        return reply(select_from_request(request))
    result = run(handler, lambda client: answer_snapshot_question("치안 좋은 곳", dataset, client, top_k=2))
    assert len(result.recommendation.items) == 2
    assert len(result.explanation.items) == 2


def test_invalid_question_top_k_fails_before_llm(dataset):
    with pytest.raises(ValueError):
        run(lambda request: pytest.fail("no external call"),
            lambda client: answer_snapshot_question("추천", dataset, client, top_k=True))


def test_two_domain_structured_insights_match_explanation(dataset):
    rec = recommend_snapshots(dataset, weights={"economy": 1, "safety": 1})
    first = rec.items[0]
    assert first.category_scores.economy > first.category_scores.safety
    assert [i.domain for i in first.strengths] == ["economy"]
    assert [i.domain for i in first.weaknesses] == ["safety"]
    result = run(lambda request: reply(select_from_request(request)), lambda client: generate_snapshot_explanation(rec, client))
    assert result.items[0].strengths == first.strengths
    assert result.items[0].weaknesses == first.weaknesses


def test_single_domain_has_no_misleading_structured_strengths_or_weaknesses(dataset):
    rec = recommend_snapshots(dataset, weights={"safety": 1})
    assert rec.items[0].strengths == []
    assert rec.items[0].weaknesses == []
    result = asyncio.run(generate_snapshot_explanation(rec))
    assert result.items[0].strengths == []
    assert result.items[0].weaknesses == []
