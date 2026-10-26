import asyncio
import json

import httpx
import pytest

from services.ai_recommendation.llm_service import (
    LLMError, OpenRouterClient, extract_preferences, generate_explanation,
)
from services.ai_recommendation.recommendation import recommend_regions
from services.ai_recommendation.rag_service import retrieve_evidence


def response(content):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}]})


def run_with_handler(handler, operation, **settings):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenRouterClient(api_key="test-secret", model="test/model", http_client=http,
                                      max_retries=1, retry_base_seconds=0, **settings)
            return await operation(client)
    return asyncio.run(run())


def draft(**overrides):
    return {"weights": None, "priority_domains": [], "min_scores": {},
            "unsupported_conditions": [], "limitations": [], **overrides}


def test_question_extracts_preferences_and_builds_real_request():
    def handler(request):
        payload = json.loads(request.content)
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert payload["response_format"]["type"] == "json_schema"
        assert payload["provider"]["require_parameters"] is True
        return response(json.dumps(draft(priority_domains=["safety", "comfort"],
            limitations=["쾌적 종합점수만으로 실제 미세먼지 수준을 보장할 수 없습니다."])))
    result = run_with_handler(handler, lambda c: extract_preferences("치안이 좋고 공기가 깨끗한 동네 추천해 줘", c))
    assert result.weights.safety == 3
    assert result.weights.comfort == 3
    assert result.weights.economy == 1
    assert result.needs_confirmation is True


def test_ambiguous_question_uses_equal_default_and_unsupported_is_preserved():
    result = run_with_handler(lambda r: response(json.dumps(draft(unsupported_conditions=["월세 80만원"]))),
                             lambda c: extract_preferences("좋은 동네 월세 80만원", c))
    assert list(result.weights.model_dump().values()) == [1, 1, 1, 1, 1]
    assert result.unsupported_conditions == ["월세 80만원"]


@pytest.mark.parametrize("content", ["not json", '{"weights":{"rent":1}}',
    json.dumps(draft(priority_domains=["rent"])), json.dumps(draft(weights={"safety": -1})),
    json.dumps(draft(weights={"economy": 0, "energy": 0, "comfort": 0, "health": 0, "safety": 0})),
    '{"weights":null,"weights":null}'])
def test_invalid_json_and_schema_are_safe_errors(content):
    with pytest.raises(LLMError) as caught:
        run_with_handler(lambda r: response(content), lambda c: extract_preferences("추천", c))
    assert caught.value.code == "invalid_output"
    assert "test-secret" not in str(caught.value)


def test_rate_limit_retries_then_succeeds():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "0"}) if len(calls) == 1 else response(json.dumps(draft()))
    result = run_with_handler(handler, lambda c: extract_preferences("추천", c))
    assert len(calls) == 2
    assert result.weights.safety == 1


@pytest.mark.parametrize("status,code", [(401, "authentication"), (402, "credits"), (429, "rate_limit"), (503, "unavailable")])
def test_http_errors_are_bounded_and_redacted(status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "test-secret raw prompt"}})
    with pytest.raises(LLMError) as caught:
        run_with_handler(handler, lambda c: extract_preferences("추천", c))
    assert caught.value.code == code
    assert len(calls) == (1 if status in [401, 402] else 2)
    assert "test-secret" not in str(caught.value)


def test_timeout_and_http_200_error_envelope():
    def handler(request):
        raise httpx.ReadTimeout("test-secret", request=request)
    with pytest.raises(LLMError, match="timeout"):
        run_with_handler(handler, lambda c: extract_preferences("추천", c))
    with pytest.raises(LLMError) as caught:
        run_with_handler(lambda r: httpx.Response(200, json={"error": {"code": 429, "message": "secret"}}),
                         lambda c: extract_preferences("추천", c))
    assert caught.value.code == "rate_limit"


def recommendation():
    return recommend_regions([{"region_code": "11680", "region_name": "강남구",
        "spatial_unit": "district", "category_scores": {"economy": 80, "energy": 70, "comfort": 75, "health": 90, "safety": 85},
        "sources": [{"source": "팀 합성 데이터", "document_title": "Mock 점수", "reference_year": 2025,
                     "original_spatial_unit": "district", "is_mock": True}]}],
        {"weights": {"economy": 10, "energy": 10, "comfort": 30, "health": 20, "safety": 30}})


def test_explanation_is_grounded_and_preserves_score_rank_sources():
    rec = recommendation()
    before = rec.model_dump_json()
    plan = {"items": [{"region_code": "11680", "strength_domains": ["health"],
                       "weakness_domains": ["energy"], "evidence_ids": [],
                       "advantages": "건강 점수는 90점으로 이 지역 내 상대적 강점입니다.",
                       "disadvantages": "에너지 점수는 70점으로 이 지역 내 상대적으로 낮습니다."}]}
    result = run_with_handler(lambda r: response(json.dumps(plan)), lambda c: generate_explanation(rec, c))
    assert result.generation_status == "llm"
    assert result.items[0].total_score == 81
    assert result.items[0].rank == 1
    assert result.items[0].sources[0].reference_year == 2025
    assert result.items[0].spatial_unit == "district"
    assert result.items[0].score_version == "unspecified"
    assert "건강" in result.items[0].advantages
    assert "에너지" in result.items[0].disadvantages
    assert result.items[0].citations == []
    assert rec.model_dump_json() == before


@pytest.mark.parametrize("plan", [
    {"items": [{"region_code": "11680", "strength_domains": ["health"], "weakness_domains": ["energy"], "evidence_ids": ["fabricated"]}]},
    {"items": [{"region_code": "other", "strength_domains": ["health"], "weakness_domains": ["energy"], "evidence_ids": [],
                       "advantages": "건강 점수는 90점으로 이 지역 내 상대적 강점입니다.",
                       "disadvantages": "에너지 점수는 70점으로 이 지역 내 상대적으로 낮습니다."}]},
    {"items": [{"region_code": "11680", "strength_domains": ["energy"], "weakness_domains": ["health"], "evidence_ids": []}]},
    {"items": [{"region_code": "11680", "strength_domains": ["health"], "weakness_domains": ["energy"], "evidence_ids": [], "summary": "범죄가 없습니다. 999점"}]},
])
def test_fabricated_evidence_facts_or_reversed_strengths_fall_back(plan):
    result = run_with_handler(lambda r: response(json.dumps(plan)), lambda c: generate_explanation(recommendation(), c))
    assert result.generation_status == "fallback"
    assert result.items[0].total_score == 81
    assert "999" not in result.model_dump_json()


def test_full_question_recommendation_explanation_json_flow():
    async def operation(client):
        preferences = await extract_preferences("치안이 좋고 공기가 깨끗한 동네 추천해 줘", client)
        from services.ai_recommendation.mock_data import get_mock_regions
        rec = recommend_regions(get_mock_regions(), {"weights": preferences.weights.model_dump()})
        evidence = await retrieve_evidence("지표 정의")
        explanation = await generate_explanation(rec, client, evidence=evidence)
        return preferences, rec, explanation
    def handler(request):
        payload = json.loads(request.content)
        if payload["response_format"]["json_schema"]["name"] == "PreferenceDraft":
            return response(json.dumps(draft(priority_domains=["safety", "comfort"])))
        context = json.loads(payload["messages"][1]["content"])
        return response(json.dumps({"items": [{"region_code": r["region_code"],
            "strength_domains": [r["strengths"][0]["domain"]],
            "weakness_domains": [r["weaknesses"][0]["domain"]], "evidence_ids": [],
            "advantages": "점수가 모두 같아 뚜렷한 강점이 없습니다." if r["profile_kind"] == "tied" else "경제 에너지 쾌적 건강 치안의 제공 점수를 비교한 상대적 강점입니다.",
            "disadvantages": "점수가 모두 같아 뚜렷한 약점이 없습니다." if r["profile_kind"] == "tied" else "경제 에너지 쾌적 건강 치안의 제공 점수를 비교한 상대적 약점입니다."}
            for r in context["recommendation"]["items"]]}))
    preferences, rec, explanation = run_with_handler(handler, operation)
    assert len(rec.items) == 5
    assert explanation.generation_status == "llm"
    assert [r.region_code for r in explanation.items] == [r.region_code for r in rec.items]
    assert json.loads(explanation.model_dump_json())["items"][0]["is_mock"] is True


def test_no_key_and_empty_question_are_rejected_before_network():
    with pytest.raises(ValueError):
        OpenRouterClient(api_key="", model="test/model")
    with pytest.raises(ValueError):
        run_with_handler(lambda r: pytest.fail("network should not be called"), lambda c: extract_preferences(" ", c))


def test_long_retry_after_is_returned_without_early_retry():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "120"})
    with pytest.raises(LLMError) as caught:
        run_with_handler(handler, lambda c: extract_preferences("추천", c))
    assert len(calls) == 1
    assert caught.value.retry_after == 120


def test_redirect_does_not_forward_credentials():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(307, headers={"Location": "https://attacker.example"})
    with pytest.raises(LLMError):
        run_with_handler(handler, lambda c: extract_preferences("추천", c))
    assert calls == ["https://openrouter.ai/api/v1/chat/completions"]


def test_oversized_response_is_rejected():
    with pytest.raises(LLMError) as caught:
        run_with_handler(lambda r: response("x" * 140000), lambda c: extract_preferences("추천", c))
    assert caught.value.code == "invalid_output"


def test_cancellation_propagates():
    def handler(request):
        raise asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        run_with_handler(handler, lambda c: extract_preferences("추천", c))


def test_tied_domains_are_not_described_as_definitely_lower():
    rec = recommend_regions([{"region_code": "a", "region_name": "가상동",
        "category_scores": dict.fromkeys(["economy", "energy", "comfort", "health", "safety"], 80)}], {})
    result = asyncio.run(generate_explanation(rec))
    assert "모두 같" in result.items[0].disadvantages


def test_empty_recommendation_does_not_call_llm():
    result = run_with_handler(lambda r: pytest.fail("must not call LLM"),
        lambda c: generate_explanation(recommend_regions([], {}), c))
    assert result.generation_status == "empty"


def test_malformed_compressed_response_is_safe_error_and_explanation_falls_back():
    def handler(request):
        raise httpx.DecodingError("sensitive provider detail", request=request)
    with pytest.raises(LLMError) as caught:
        run_with_handler(handler, lambda c: extract_preferences("추천", c))
    assert caught.value.code == "invalid_output"
    assert "sensitive" not in str(caught.value)
    result = run_with_handler(handler, lambda c: generate_explanation(recommendation(), c))
    assert result.generation_status == "fallback"


def test_total_deadline_bounds_slow_provider():
    async def handler(request):
        await asyncio.sleep(0.1)
        return response(json.dumps(draft()))
    with pytest.raises(LLMError) as caught:
        run_with_handler(handler, lambda c: extract_preferences("추천", c), total_timeout_seconds=0.01)
    assert caught.value.code == "timeout"


@pytest.mark.parametrize("wrapper", ["```json\n{}\n```", "```\n{}\n```"])
def test_single_json_code_fence_is_accepted_without_relaxing_schema(wrapper):
    content = wrapper.format(json.dumps(draft(priority_domains=["safety"])))
    result = run_with_handler(lambda r: response(content), lambda c: extract_preferences("치안", c))
    assert result.weights.safety == 3


@pytest.mark.parametrize("content", [
    '설명입니다\n```json\n{}\n```',
    '```json\n{"weights":null,"weights":null}\n```',
    '```json\n{"priority_domains":["rent"]}\n```',
])
def test_code_fence_does_not_accept_prose_duplicates_or_wrong_fields(content):
    with pytest.raises(LLMError):
        run_with_handler(lambda r: response(content), lambda c: extract_preferences("추천", c))


def test_truncated_reasoning_response_has_safe_diagnostics():
    body = {"choices": [{"finish_reason": "length", "message": {"content": ""}}],
            "usage": {"completion_tokens": 2000, "completion_tokens_details": {"reasoning_tokens": 1990}}}
    with pytest.raises(LLMError) as caught:
        run_with_handler(lambda r: httpx.Response(200, json=body), lambda c: extract_preferences("추천", c))
    assert caught.value.details == {"stage": "finish_reason", "output_schema": "PreferenceDraft",
        "finish_reason": "length", "completion_tokens": 2000, "reasoning_tokens": 1990}


def test_validation_diagnostics_never_include_model_input_or_unknown_field_names():
    content = json.dumps(draft(priority_domains=["test-secret"], **{"secret-field-name": "sensitive question"}))
    with pytest.raises(LLMError) as caught:
        run_with_handler(lambda r: response(content), lambda c: extract_preferences("추천", c))
    payload = caught.value.as_dict()
    assert payload["details"]["stage"] == "schema_validation"
    assert {e["type"] for e in payload["details"]["validation_errors"]} == {"literal_error", "extra_forbidden"}
    assert "test-secret" not in json.dumps(payload)
    assert "secret-field-name" not in json.dumps(payload)
    assert "sensitive question" not in json.dumps(payload)


@pytest.mark.parametrize("body,stage", [
    ("invalid json", "response_json"), ({"choices": []}, "response_envelope"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": None}}]}, "content_empty"),
    ({"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]}, "content_json"),
])
def test_parse_failures_are_distinguishable(body, stage):
    def handler(request):
        return httpx.Response(200, content=body) if isinstance(body, str) else httpx.Response(200, json=body)
    with pytest.raises(LLMError) as caught:
        run_with_handler(handler, lambda c: extract_preferences("추천", c))
    assert caught.value.details["stage"] == stage


def test_output_budget_can_be_configured_for_reasoning_models():
    def handler(request):
        assert json.loads(request.content)["max_tokens"] == 4096
        return response(json.dumps(draft()))
    result = run_with_handler(handler, lambda c: extract_preferences("추천", c), max_tokens=4096)
    assert result.extraction_status == "llm"


@pytest.mark.parametrize("value", [0, True, -1, 20000])
def test_invalid_output_budget_is_rejected(value):
    with pytest.raises(ValueError):
        OpenRouterClient(api_key="test", model="test/model", max_tokens=value)


def test_zero_weight_output_is_corrected_once_without_silent_defaulting():
    calls = []
    def handler(request):
        payload = json.loads(request.content)
        calls.append(payload)
        if len(calls) == 1:
            return response(json.dumps(draft(weights=dict.fromkeys(["economy", "energy", "comfort", "health", "safety"], 0))))
        assert json.loads(payload["messages"][1]["content"]) == {"question": "치안과 쾌적을 선호해"}
        assert "weights=null" in payload["messages"][0]["content"]
        return response(json.dumps(draft(priority_domains=["safety", "comfort"])))
    result = run_with_handler(handler, lambda c: extract_preferences("치안과 쾌적을 선호해", c))
    assert len(calls) == 2
    assert result.weights.safety == 3
    assert result.weights.comfort == 3
    assert result.weights.economy == 1
    assert result.extraction_status == "llm"


def test_repeated_zero_weight_output_stops_after_one_correction():
    calls = []
    def handler(request):
        calls.append(request)
        return response(json.dumps(draft(weights=dict.fromkeys(["economy", "energy", "comfort", "health", "safety"], 0))))
    with pytest.raises(LLMError) as caught:
        run_with_handler(handler, lambda c: extract_preferences("추천", c))
    assert len(calls) == 2
    assert caught.value.details["validation_errors"] == [{"field": "weights", "type": "zero_weight_sum"}]


@pytest.mark.parametrize("output", [draft(weights={"safety": -1}), draft(priority_domains=["rent"])])
def test_other_invalid_outputs_do_not_trigger_weight_correction(output):
    calls = []
    def handler(request):
        calls.append(request)
        return response(json.dumps(output))
    with pytest.raises(LLMError):
        run_with_handler(handler, lambda c: extract_preferences("추천", c))
    assert len(calls) == 1


def test_explanation_fallback_preserves_safe_output_failure_diagnostic():
    body = {"choices": [{"finish_reason": "length", "message": {"content": ""}}],
            "usage": {"completion_tokens": 4096, "completion_tokens_details": {"reasoning_tokens": 4000}}}
    result = run_with_handler(lambda r: httpx.Response(200, json=body),
                             lambda c: generate_explanation(recommendation(), c))
    assert result.generation_status == "fallback"
    assert result.diagnostics[0]["details"]["stage"] == "finish_reason"
    assert result.diagnostics[0]["details"]["reasoning_tokens"] == 4000
    assert result.items[0].total_score == 81


def test_grounding_failures_have_distinct_safe_diagnostics():
    plan = {"items": [{"region_code": "11680", "strength_domains": ["health"],
                       "weakness_domains": ["energy"], "evidence_ids": ["unprovided-doc"],
                       "advantages": "건강 점수는 90점입니다.", "disadvantages": "에너지 점수는 70점입니다."}]}
    result = run_with_handler(lambda r: response(json.dumps(plan)),
                             lambda c: generate_explanation(recommendation(), c))
    assert result.diagnostics[0]["details"] == {"stage": "plan_validation", "reason": "invalid_evidence_selection"}
    assert "unprovided-doc" not in json.dumps(result.diagnostics)


NEMOTRON = "nvidia/nemotron-3-ultra-550b-a55b:free"


def tool_response(arguments, name="PreferenceDraft", reason="tool_calls", count=1):
    call = {"id": "call_test", "type": "function", "function": {"name": name, "arguments": arguments}}
    return httpx.Response(200, json={"choices": [{"finish_reason": reason,
        "message": {"content": None, "tool_calls": [call] * count}}]})


def run_nemotron(handler, operation):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = OpenRouterClient(api_key="test-secret", model=NEMOTRON, http_client=http, max_retries=0)
            return await operation(client)
    return asyncio.run(run())


def test_nemotron_uses_forced_tool_and_validates_preferences():
    def handler(request):
        payload = json.loads(request.content)
        assert "response_format" not in payload
        tool = payload["tools"][0]["function"]
        assert tool["name"] == "PreferenceDraft"
        assert tool["parameters"]["additionalProperties"] is False
        assert payload["tool_choice"] == {"type": "function", "function": {"name": "PreferenceDraft"}}
        return tool_response(json.dumps(draft(priority_domains=["safety"])))
    result = run_nemotron(handler, lambda c: extract_preferences("치안이 좋은 동네", c))
    assert result.weights.safety == 3


@pytest.mark.parametrize("arguments,name,reason,count", [
    ("not json", "PreferenceDraft", "tool_calls", 1),
    (json.dumps(draft()), "other", "tool_calls", 1),
    (json.dumps(draft()), "PreferenceDraft", "length", 1),
    (json.dumps(draft()), "PreferenceDraft", "tool_calls", 0),
    (json.dumps(draft()), "PreferenceDraft", "tool_calls", 2),
    (json.dumps(draft(priority_domains=["rent"])), "PreferenceDraft", "tool_calls", 1),
    ('{"weights":null,"weights":null}', "PreferenceDraft", "tool_calls", 1),
])
def test_nemotron_invalid_tool_calls_are_rejected(arguments, name, reason, count):
    with pytest.raises(LLMError) as caught:
        run_nemotron(lambda r: tool_response(arguments, name, reason, count),
                     lambda c: extract_preferences("추천", c))
    assert caught.value.code == "invalid_output"
    assert "test-secret" not in str(caught.value.as_dict())


def test_nemotron_explanation_preserves_computed_facts():
    rec = recommendation()
    plan = {"items": [{"region_code": "11680", "strength_domains": ["health"],
                       "weakness_domains": ["energy"], "evidence_ids": [],
                       "advantages": "건강 점수는 90점으로 이 지역 내 상대적 강점입니다.",
                       "disadvantages": "에너지 점수는 70점으로 이 지역 내 상대적으로 낮습니다."}]}
    result = run_nemotron(lambda r: tool_response(json.dumps(plan), "ExplanationPlan"),
                          lambda c: generate_explanation(rec, c))
    assert result.generation_status == "llm"
    assert result.items[0].rank == 1
    assert result.items[0].total_score == rec.items[0].total_score


def test_llm_explicit_weights_require_all_five_keys():
    with pytest.raises(LLMError) as caught:
        run_with_handler(lambda r: response(json.dumps(draft(weights={"safety":100}))),
                         lambda c: extract_preferences("safety 100, others 0", c))
    assert caught.value.code == "invalid_output"
