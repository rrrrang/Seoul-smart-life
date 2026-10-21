"""Actual-score LLM flow. Preserve scope, provenance, and computed ranking.

LLM selects validated domains/evidence only. Python renders factual sentences.
Missing user-requested domains require confirmation rather than substitution.
"""
from typing import Literal

from pydantic import Field

from .llm_service import LABELS, LLMError, OpenRouterClient, _validated_plan, extract_preferences
from .prompts import EXPLANATION_PROMPT
from .rag_service import EvidenceRetriever, retrieve_evidence
from .schemas import (
    DOMAINS, Contract, Domain, DomainInsight, EvidenceChunk, EvidenceResult,
    ExplanationPlan, ExtractedPreferences, RecommendationRequest, Weights,
)
from .snapshot_service import (
    SnapshotDataset, SnapshotRecommendation, SnapshotRecommendationItem, recommend_snapshots, _snapshot_insights,
)


class SnapshotRegionExplanation(SnapshotRecommendationItem):
    advantages: str
    disadvantages: str
    limitations: list[str]
    citations: list[EvidenceChunk]


class SnapshotExplanationResult(Contract):
    generation_status: Literal["llm", "fallback", "empty"]
    selected_domains: list[Domain]
    selected_max_points: int
    unavailable_domains: list[Domain]
    snapshot_version: str
    target_month: str
    items: list[SnapshotRegionExplanation]
    warnings: list[str] = Field(default_factory=list)
    diagnostics: list[dict] = Field(default_factory=list)
    is_mock: bool = False


class SnapshotQuestionResult(Contract):
    status: Literal["provisional", "confirmed", "needs_confirmation"]
    preferences: ExtractedPreferences | None
    effective_request: RecommendationRequest | None
    unavailable_requested_domains: list[Domain]
    recommendation: SnapshotRecommendation | None
    evidence: EvidenceResult
    explanation: SnapshotExplanationResult | None
    warnings: list[str] = Field(default_factory=list)


def _selection_context(recommendation):
    context = recommendation.model_copy(deep=True)
    for row in context.items:
        values = row.category_scores.model_dump()
        visible = [d for d in context.selected_domains if values[d] is not None]
        if not visible:
            raise ValueError("selected score evidence is missing")
        strong, weak = _snapshot_insights(values, row.contributions, context.selected_domains)
        # The provider selection schema needs one candidate even for a flat profile.
        # This placeholder is never exposed as an actual strength or weakness.
        representative = [DomainInsight(domain=visible[0], score=values[visible[0]],
                                        contribution=row.contributions[visible[0]])]
        row.strengths, row.weaknesses = strong or representative, weak or representative
    return context


async def generate_snapshot_explanation(
    recommendation: SnapshotRecommendation, client: OpenRouterClient | None = None, *,
    evidence: EvidenceResult | None = None,
) -> SnapshotExplanationResult:
    rec = SnapshotRecommendation.model_validate(recommendation).model_copy(deep=True)
    evidence = EvidenceResult.model_validate(evidence or EvidenceResult(status="no_evidence", chunks=[])).model_copy(deep=True)
    common = dict(selected_domains=rec.selected_domains, selected_max_points=rec.selected_max_points,
                  unavailable_domains=rec.unavailable_domains, snapshot_version=rec.snapshot_version,
                  target_month=rec.target_month, is_mock=rec.is_mock)
    if not rec.items:
        return SnapshotExplanationResult(**common, generation_status="empty", items=[], warnings=["NO_MATCHING_REGIONS"])
    context = _selection_context(rec)
    chosen, diagnostics, warnings = {}, [], list(rec.warnings)
    status = "fallback"
    if client is not None:
        # Send a bounded evidence summary, not repeated medical/raw data tables.
        payload = {"selected_domains": rec.selected_domains, "selected_max_points": rec.selected_max_points,
            "unavailable_domains": rec.unavailable_domains, "items": [{
                "region_code": row.region_code, "rank": row.rank,
                "personalized_score_100": row.personalized_score_100,
                "category_scores": row.category_scores.model_dump(), "domain_points_20": row.domain_points_20,
                "strengths": [i.model_dump() for i in row.strengths],
                "weaknesses": [i.model_dump() for i in row.weaknesses],
                "domain_metadata": {d: row.domain_metadata[d].model_dump(exclude={"details"})
                                    for d in rec.selected_domains},
            } for row in context.items]}
        try:
            plan = await client.structured(EXPLANATION_PROMPT +
                "\n추정·시범·관할 참고점수를 실제 행정동 관측값으로 해석하지 마세요. "
                "personalized_score_100은 선택 영역 기준이며 전체 다섯 영역 점수가 아닙니다.",
                {"recommendation": payload, "evidence": evidence.model_dump()}, ExplanationPlan)
            chosen = _validated_plan(plan, context, evidence)
            status = "llm"
        except LLMError as error:
            diagnostics.append(error.as_dict())
            warnings.append(f"LLM_{error.code.upper()}")
    else:
        warnings.append("LLM_NOT_CONFIGURED")
    if not evidence.chunks:
        warnings.append("NO_DOCUMENT_EVIDENCE")
    documents = {doc.chunk_id: doc for doc in evidence.chunks}
    items = []
    for row in context.items:
        selection = chosen.get(row.region_code)
        strong = selection.strength_domains if selection else [i.domain for i in row.strengths]
        weak = selection.weakness_domains if selection else [i.domain for i in row.weaknesses]
        values = row.category_scores.model_dump()
        def describe(domains):
            return ", ".join(f"{LABELS[d]} {values[d]:.1f}/100점"
                             for d in dict.fromkeys(domains))
        limits = ["강점·약점은 선택한 영역 내 점수의 상대 비교이며 실제 거주 만족도나 인과효과를 뜻하지 않습니다."]
        if len(rec.selected_domains) == 1:
            advantages = f"선택한 영역의 제공 점수는 {describe(strong)}입니다."
            disadvantages = "영역을 하나만 선택하여 다른 생활환경과의 장단점은 비교할 수 없습니다."
            limits.append("선택 영역이 하나이므로 영역 간 강점·약점 비교를 제공하지 않습니다.")
        elif len({values[d] for d in rec.selected_domains}) == 1:
            advantages = "선택한 영역 점수가 모두 같아 뚜렷한 상대적 강점이 없습니다."
            disadvantages = "선택한 영역 점수가 모두 같아 뚜렷한 상대적 약점이 없습니다."
        else:
            advantages = f"제공된 점수에서 상대적 강점은 {describe(strong)}입니다."
            disadvantages = f"제공된 점수에서 상대적으로 낮은 영역은 {describe(weak)}입니다."
        if len(rec.selected_domains) < len(DOMAINS):
            limits.append(f"현재 {len(rec.selected_domains)}개 영역 기준의 개인화 100점이며, 전체 다섯 영역 평가가 아닙니다.")
        if "comfort" in rec.unavailable_domains:
            limits.append("쾌적 자료는 미제공이며 평가하지 않았습니다. 건강 점수로 대체하지 않습니다.")
        for domain in rec.selected_domains:
            source = row.domain_metadata[domain]
            periods = ", ".join(f"{key}={value}" for key, value in source.source_periods.items())
            limits.append(f"{LABELS[domain]}: {source.interpretation} 기준기간: {periods}. 상태: {source.status}.")
            if not source.production_approved:
                limits.append(f"{LABELS[domain]} 점수는 정식 운영 승인 전 또는 미확인 제공본입니다.")
        citations = [documents[key] for key in dict.fromkeys(selection.evidence_ids)] if selection else []
        if not citations:
            limits.append("이 지역의 검색 문서 근거는 선택되지 않았으며, 제공된 점수 메타데이터 범위로 설명했습니다.")
        if rec.is_mock:
            limits.append("테스트용 합성 자료입니다.")
        # Copy every score, source, year, unit, code, and flag from the original result.
        original = next(item for item in rec.items if item.region_code == row.region_code)
        data = original.model_dump()
        data["strengths"], data["weaknesses"] = _snapshot_insights(
            original.category_scores.model_dump(), original.contributions, rec.selected_domains)
        items.append(SnapshotRegionExplanation(**data, advantages=advantages,
            disadvantages=disadvantages, limitations=limits, citations=citations))
    return SnapshotExplanationResult(**common, generation_status=status, items=items,
        warnings=list(dict.fromkeys(warnings)), diagnostics=diagnostics)


async def answer_snapshot_question(
    question: str, dataset: SnapshotDataset, client: OpenRouterClient, *,
    confirmed_request: RecommendationRequest | None = None,
    retriever: EvidenceRetriever | None = None, allow_llm_fallback: bool = False,
    top_k: int | None = None,
) -> SnapshotQuestionResult:
    if type(allow_llm_fallback) is not bool:
        raise ValueError("allow_llm_fallback must be an actual boolean")
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ValueError("question must contain 1 to 2000 characters")
    if top_k is not None:
        RecommendationRequest(top_k=top_k)
    dataset = SnapshotDataset.model_validate(dataset)
    warnings = []
    unavailable = [d for d in DOMAINS if d not in dataset.available_domains]
    preferences = None
    if confirmed_request is not None:
        request = RecommendationRequest.model_validate(confirmed_request)
        if top_k is not None and top_k != request.top_k:
            raise ValueError("top_k conflicts with the confirmed request")
        status = "confirmed"
    else:
        try:
            preferences = await extract_preferences(question, client)
        except LLMError as error:
            if not allow_llm_fallback:
                raise
            preferences = ExtractedPreferences(extraction_status="fallback", weight_source="fallback",
                weights={d: 1 if d in dataset.available_domains else 0 for d in DOMAINS},
                limitations=[f"자연어 추출 실패({error.code}): 제공 영역에 동일 기본 가중치를 사용했습니다. 질문 조건은 적용되지 않았습니다."])
            warnings.append("PREFERENCES_DEFAULTED_AFTER_LLM_FAILURE")
        requested = [d for d in unavailable if d in preferences.priority_domains
                     or getattr(preferences.min_scores, d) is not None
                     or (preferences.weight_source == "explicit" and getattr(preferences.weights, d) > 0)]
        if requested or preferences.unsupported_conditions:
            return SnapshotQuestionResult(status="needs_confirmation", preferences=preferences,
                effective_request=None, unavailable_requested_domains=requested, recommendation=None,
                evidence=EvidenceResult(status="no_evidence", chunks=[]), explanation=None,
                warnings=["UNSUPPORTED_CONDITIONS_REQUIRE_CONFIRMATION"])
        weights = preferences.weights.model_dump()
        if any(weights[d] > 0 for d in unavailable):
            # Only implicit background defaults are scoped to available domains.
            # Explicit user requests for missing domains were stopped above.
            warnings.append("DEFAULT_WEIGHTS_LIMITED_TO_AVAILABLE_DOMAINS")
        request = RecommendationRequest(weights=Weights.model_validate({
            d: weights[d] if d in dataset.available_domains else 0 for d in DOMAINS}),
            top_k=preferences.top_k if top_k is None else top_k, min_scores=preferences.min_scores)
        status = "provisional"
    rec = recommend_snapshots(dataset, weights=request.weights.model_dump(), top_k=request.top_k,
        min_scores=request.min_scores.model_dump(exclude_none=True))
    evidence = await retrieve_evidence(question, retriever)
    explanation = await generate_snapshot_explanation(rec, client, evidence=evidence)
    return SnapshotQuestionResult(status=status, preferences=preferences, effective_request=request,
        unavailable_requested_domains=[], recommendation=rec, evidence=evidence,
        explanation=explanation, warnings=warnings)
