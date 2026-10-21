"""Backend-callable orchestration; does not implement HTTP endpoints or DB."""
from collections.abc import Iterable, Mapping

from .llm_service import LLMError, OpenRouterClient, extract_preferences, generate_explanation
from .rag_service import EvidenceRetriever, retrieve_evidence
from .recommendation import recommend_regions
from .schemas import ExtractedPreferences, PipelineResult, RegionScore


async def answer_question(
    question: str, regions: Iterable[RegionScore | Mapping], client: OpenRouterClient, *,
    retriever: EvidenceRetriever | None = None, allow_llm_fallback: bool = False,
) -> PipelineResult:
    """Return provisional recommendations; backend should expose preference confirmation.

    Extraction failure raises by default. Explicit fallback uses equal weights and
    labels the loss of personalization; it never pretends to interpret the question.
    """
    if type(allow_llm_fallback) is not bool:
        raise ValueError("allow_llm_fallback must be an actual boolean")
    try:
        preferences = await extract_preferences(question, client)
    except LLMError as error:
        if not allow_llm_fallback:
            raise
        preferences = ExtractedPreferences(extraction_status="fallback", weight_source="fallback",
            limitations=[f"자연어 추출 실패({error.code}): 동일 기본 가중치를 사용했습니다. 질문의 조건은 적용되지 않았습니다."])
    recommendation = recommend_regions(regions, preferences.recommendation_request())
    evidence = await retrieve_evidence(question, retriever)
    explanation = await generate_explanation(recommendation, client, evidence=evidence)
    return PipelineResult(preferences=preferences, recommendation=recommendation,
                          evidence=evidence, explanation=explanation)
