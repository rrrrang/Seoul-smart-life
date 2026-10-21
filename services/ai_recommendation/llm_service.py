"""OpenRouter structured calls with bounded retries and grounded explanations."""
import asyncio
import copy
import json
import math
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from .prompts import EXPLANATION_PROMPT, PREFERENCE_PROMPT
from .schemas import (
    DOMAINS, EvidenceResult, ExplanationPlan, ExplanationResult, ExtractedPreferences,
    PreferenceDraft, RecommendationResult, RegionExplanation, Weights,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
LABELS = {"economy": "경제", "energy": "에너지", "comfort": "쾌적", "health": "건강", "safety": "치안"}


class LLMError(RuntimeError):
    """Safe error: never includes provider body, prompt, credentials or request."""
    def __init__(self, code: str, *, status_code: int | None = None, retry_after: float | None = None,
                 details: dict | None = None):
        self.code = code
        self.status_code = status_code
        self.retry_after = retry_after
        self.details = details or {}
        super().__init__(f"OpenRouter error: {code}")

    def as_dict(self) -> dict:
        result = {"error": str(self), "code": self.code}
        if self.status_code is not None:
            result["status_code"] = self.status_code
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        if self.details:
            result["details"] = self.details
        return result


def _strict_json(text):
    def pairs(entries):
        result = {}
        for key, value in entries:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def bad_constant(value):
        raise ValueError("non-finite JSON number")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=bad_constant)


def _provider_schema(model):
    schema = copy.deepcopy(model.model_json_schema())
    def visit(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(schema)
    return schema


def _parse_response(raw: bytes, output_model: type[ModelT]) -> ModelT:
    """Identify failure stages without exposing any response text or input values."""
    stage = "response_json"
    details = {"output_schema": output_model.__name__}
    try:
        body = _strict_json(raw.decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("expected object")
        stage = "response_envelope"
        if "error" in body:
            status = body["error"].get("code", 502)
            status = status if type(status) is int else 502
            raise LLMError(_error_code(status), status_code=status)
        choice = body["choices"][0]
        reason = choice.get("finish_reason")
        stage = "finish_reason"
        if reason not in (None, "stop"):
            details["finish_reason"] = reason if reason in ("length", "content_filter", "tool_calls", "error") else "other"
            usage = body.get("usage")
            if isinstance(usage, dict):
                token_details = usage.get("completion_tokens_details")
                reasoning = token_details.get("reasoning_tokens") if isinstance(token_details, dict) else None
                for name, value in (("completion_tokens", usage.get("completion_tokens")), ("reasoning_tokens", reasoning)):
                    if type(value) is int and 0 <= value <= 1000000000:
                        details[name] = value
            raise ValueError("incomplete response")
        stage = "content_empty"
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise ValueError("missing content")
        stage = "content_json"
        content = content.strip()
        # Accept only one complete JSON code fence; never extract JSON from prose.
        fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```", content, flags=re.IGNORECASE)
        if fence:
            content = fence.group(1)
        parsed = _strict_json(content)
        stage = "schema_validation"
        return output_model.model_validate(parsed)
    except ValidationError as error:
        # Pydantic messages/input/context and unknown extra-field names may contain secrets.
        known_fields = set()
        def fields(node):
            if isinstance(node, dict):
                known_fields.update(node.get("properties", {}))
                for value in node.values():
                    fields(value)
            elif isinstance(node, list):
                for value in node:
                    fields(value)
        fields(output_model.model_json_schema())
        details["validation_errors"] = [{
            "field": ".".join(str(part) if type(part) is int or part in known_fields else "<unknown>"
                              for part in entry["loc"]),
            "type": entry["type"],
        } for entry in error.errors(include_input=False, include_context=False, include_url=False)[:10]]
        raise LLMError("invalid_output", details={"stage": stage, **details}) from None
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, RecursionError):
        raise LLMError("invalid_output", details={"stage": stage, **details}) from None


def _error_code(status):
    return {401: "authentication", 402: "credits", 403: "forbidden", 408: "timeout", 429: "rate_limit"}.get(
        status, "unavailable" if status >= 500 else "api_error")


def _retry_after(header):
    if not header:
        return None
    try:
        value = float(header)
    except ValueError:
        try:
            date = parsedate_to_datetime(header)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            value = (date - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0, value) if math.isfinite(value) else None


class OpenRouterClient:
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, *, api_key: str, model: str, http_client: httpx.AsyncClient | None = None,
                 timeout_seconds: float = 20, total_timeout_seconds: float = 60,
                 max_retries: int = 2, retry_base_seconds: float = 0.5, max_retry_delay: float = 5,
                 max_tokens: int = 2000):
        if not isinstance(api_key, str) or not api_key.strip() or any(c.isspace() for c in api_key):
            raise ValueError("a non-empty API key without whitespace is required")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("an explicit structured-output model is required")
        if type(max_retries) is not int or not 0 <= max_retries <= 3:
            raise ValueError("max_retries must be 0 to 3")
        if type(max_tokens) is not int or not 256 <= max_tokens <= 16384:
            raise ValueError("max_tokens must be 256 to 16384")
        for name, value in (("timeout", timeout_seconds), ("total_timeout", total_timeout_seconds),
                            ("retry_base", retry_base_seconds), ("retry_delay", max_retry_delay)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"invalid {name}")
        if timeout_seconds == 0 or total_timeout_seconds == 0:
            raise ValueError("timeouts must be positive")
        self._api_key = api_key
        self.model = model.strip()
        self.http_client = http_client
        self.timeout_seconds = timeout_seconds
        self.total_timeout_seconds = total_timeout_seconds
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.max_retry_delay = max_retry_delay
        self.max_tokens = max_tokens

    async def structured(self, system: str, data: dict, output_model: type[ModelT]) -> ModelT:
        payload = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(data, ensure_ascii=False, allow_nan=False)}],
            "provider": {"require_parameters": True},
            "response_format": {"type": "json_schema", "json_schema": {
                "name": output_model.__name__, "strict": True, "schema": _provider_schema(output_model)}}}
        try:
            async with asyncio.timeout(self.total_timeout_seconds):
                if self.http_client is not None:
                    return await self._request(self.http_client, payload, output_model)
                async with httpx.AsyncClient(trust_env=False, follow_redirects=False) as http:
                    return await self._request(http, payload, output_model)
        except TimeoutError:
            raise LLMError("timeout") from None

    async def _request(self, http, payload, output_model):
        for attempt in range(self.max_retries + 1):
            retry_delay = None
            try:
                async with http.stream("POST", self.URL, json=payload,
                        headers={"Authorization": f"Bearer {self._api_key}"},
                        timeout=self.timeout_seconds, follow_redirects=False) as response:
                    if response.status_code != 200:
                        retry_delay = _retry_after(response.headers.get("Retry-After"))
                        raise LLMError(_error_code(response.status_code), status_code=response.status_code,
                                       retry_after=retry_delay)
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 131072:
                            raise LLMError("invalid_output", details={"stage": "response_size",
                                "output_schema": output_model.__name__})
                    return _parse_response(bytes(raw), output_model)
            except httpx.TimeoutException:
                error = LLMError("timeout")
            except httpx.DecodingError:
                error = LLMError("invalid_output", details={"stage": "response_decoding", "output_schema": output_model.__name__})
            except httpx.TransportError:
                error = LLMError("network")
            except LLMError as caught:
                error = caught
                retry_delay = caught.retry_after
            if error.code not in ("timeout", "network", "rate_limit", "unavailable") or attempt == self.max_retries:
                raise error from None
            delay = retry_delay if retry_delay is not None else min(self.retry_base_seconds * 2 ** attempt, self.max_retry_delay)
            # Do not retry before a provider's long Retry-After. Return it to the caller.
            if delay > self.max_retry_delay:
                raise error from None
            await asyncio.sleep(delay)
        raise LLMError("unavailable")


async def extract_preferences(text: str, client: OpenRouterClient) -> ExtractedPreferences:
    if not isinstance(text, str) or not text.strip() or len(text) > 2000:
        raise ValueError("text must contain 1 to 2000 characters")
    data = {"question": text.strip()}
    try:
        draft = await client.structured(PREFERENCE_PROMPT, data, PreferenceDraft)
    except LLMError as error:
        if not (error.code == "invalid_output"
                and error.details.get("stage") == "schema_validation"
                and error.details.get("output_schema") == "PreferenceDraft"
                and error.details.get("validation_errors") == [{"field": "weights", "type": "zero_weight_sum"}]):
            raise
        correction = "\n이전 응답의 weights 합계가 0이라 거부됐습니다. 질문을 다시 분석하세요. " \
                     "숫자 비중이 명시되지 않았다면 weights=null과 priority_domains를 반환하세요. " \
                     "명시된 비중이 있다면 원문을 보존하고 임의의 숫자를 만들지 마세요."
        # Exactly one schema correction, distinct from transient HTTP retries.
        # No invalid response values are accepted, coerced, or sent back to the model.
        draft = await client.structured(PREFERENCE_PROMPT + correction, data, PreferenceDraft)
    priorities = list(dict.fromkeys(draft.priority_domains))
    weights = draft.weights or Weights.model_validate({d: 3 if d in priorities else 1 for d in DOMAINS})
    limitations = list(draft.limitations)
    if any(word in text for word in ("공기", "미세먼지")):
        limitations.append("쾌적 종합점수는 미세먼지 개별 관측값을 대신하지 않습니다.")
    return ExtractedPreferences(weights=weights, priority_domains=priorities, min_scores=draft.min_scores,
        unsupported_conditions=draft.unsupported_conditions, limitations=list(dict.fromkeys(limitations)))


def _validated_plan(plan: ExplanationPlan, recommendation, evidence):
    lookup = {item.region_code: item for item in recommendation.items}
    chosen = {item.region_code: item for item in plan.items}
    if len(chosen) != len(plan.items) or set(chosen) != set(lookup):
        raise LLMError("invalid_output", details={"stage": "plan_validation", "reason": "region_set_mismatch"})
    documents = {chunk.chunk_id: chunk for chunk in evidence.chunks}
    for code, selection in chosen.items():
        row = lookup[code]
        if not set(selection.strength_domains) <= {i.domain for i in row.strengths}:
            raise LLMError("invalid_output", details={"stage": "plan_validation", "reason": "invalid_strength_selection"})
        if not set(selection.weakness_domains) <= {i.domain for i in row.weaknesses}:
            raise LLMError("invalid_output", details={"stage": "plan_validation", "reason": "invalid_weakness_selection"})
        if any(identifier not in documents or documents[identifier].region_code not in (None, code)
               for identifier in selection.evidence_ids):
            raise LLMError("invalid_output", details={"stage": "plan_validation", "reason": "invalid_evidence_selection"})
    return chosen


async def generate_explanation(
    recommendation: RecommendationResult, client: OpenRouterClient | None = None, *,
    evidence: EvidenceResult | None = None,
) -> ExplanationResult:
    recommendation = RecommendationResult.model_validate(recommendation)
    evidence = evidence or EvidenceResult(status="no_evidence", chunks=[])
    if not recommendation.items:
        return ExplanationResult(generation_status="empty", items=[], warnings=["NO_MATCHING_REGIONS"])
    chosen = {}
    warnings = []
    diagnostics = []
    status = "fallback"
    if client is not None:
        try:
            plan = await client.structured(EXPLANATION_PROMPT,
                {"recommendation": recommendation.model_dump(), "evidence": evidence.model_dump()}, ExplanationPlan)
            chosen = _validated_plan(plan, recommendation, evidence)
            status = "llm"
        except LLMError as error:
            warnings.append(f"LLM_{error.code.upper()}")
            diagnostics.append(error.as_dict())
    else:
        warnings.append("LLM_NOT_CONFIGURED")
    if not evidence.chunks:
        warnings.append("NO_DOCUMENT_EVIDENCE")
    documents = {chunk.chunk_id: chunk for chunk in evidence.chunks}
    items = []
    for row in recommendation.items:
        selection = chosen.get(row.region_code)
        strengths = selection.strength_domains if selection else [i.domain for i in row.strengths]
        weaknesses = selection.weakness_domains if selection else [i.domain for i in row.weaknesses]
        def describe(domains):
            return ", ".join(f"{LABELS[d]} {getattr(row.category_scores, d):g}점" for d in dict.fromkeys(domains))
        limits = ["강점·약점은 이 지역 내 영역 점수의 상대적 비교입니다.",
                  "종합 영역 점수만으로 실제 범죄·미세먼지·의료 이용 상태를 단정할 수 없습니다."]
        if row.is_mock:
            limits.append("테스트용 가상 점수이며 실제 서울시 통계가 아닙니다.")
        if not row.sources or any(s.reference_year is None for s in row.sources):
            limits.append("점수 출처 또는 기준연도 정보가 부족합니다.")
        if row.spatial_unit == "unknown":
            limits.append("공간 단위가 확인되지 않았습니다.")
        if not evidence.chunks:
            limits.append("검색 가능한 공공데이터 설명 문서 근거가 없습니다.")
        known_scores = [s for s in row.category_scores.model_dump().values() if s is not None]
        if len(known_scores) < len(DOMAINS):
            limits.append("일부 영역 점수가 결측이며 관측된 영역만 상대 비교했습니다.")
        equal = len(set(known_scores)) == 1
        advantage = "관측된 영역 점수가 모두 같아 뚜렷한 상대적 강점이 없습니다." if equal else f"제공된 점수에서 상대적 강점은 {describe(strengths)}입니다."
        disadvantage = "관측된 영역 점수가 모두 같아 뚜렷한 상대적 약점이 없습니다." if equal else f"제공된 점수에서 상대적으로 낮은 영역은 {describe(weaknesses)}입니다."
        citations = [documents[i] for i in dict.fromkeys(selection.evidence_ids)] if selection else []
        items.append(RegionExplanation(region_code=row.region_code, region_name=row.region_name,
            rank=row.rank, total_score=row.total_score,
            spatial_unit=row.spatial_unit, score_version=row.score_version,
            advantages=advantage, disadvantages=disadvantage,
            limitations=limits, sources=row.sources, citations=citations, is_mock=row.is_mock))
    return ExplanationResult(generation_status=status, items=items, warnings=warnings, diagnostics=diagnostics)
