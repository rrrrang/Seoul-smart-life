"""Shared contracts; no database, HTTP, or service dependencies."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

DOMAINS = ("economy", "energy", "comfort", "health", "safety")
Domain = Literal["economy", "energy", "comfort", "health", "safety"]
SpatialUnit = Literal["district", "administrative_dong", "unknown"]
Number = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0)]
Score = Annotated[float, Field(strict=True, allow_inf_nan=False, ge=0, le=100)]
NonEmpty = Annotated[str, Field(strict=True, min_length=1, max_length=300)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, str_strip_whitespace=True, revalidate_instances="always")


class Weights(Contract):
    economy: Number = 1
    energy: Number = 1
    comfort: Number = 1
    health: Number = 1
    safety: Number = 1

    @model_validator(mode="after")
    def positive_sum(self):
        if not any(self.model_dump().values()):
            raise PydanticCustomError("zero_weight_sum", "weight sum must be positive")
        return self


class CategoryScores(Contract):
    economy: Score | None = None
    energy: Score | None = None
    comfort: Score | None = None
    health: Score | None = None
    safety: Score | None = None


class SourceMetadata(Contract):
    source: NonEmpty
    document_title: NonEmpty
    reference_year: Annotated[int, Field(strict=True, ge=1900, le=2100)] | None = None
    original_spatial_unit: SpatialUnit = "unknown"
    is_mock: bool = True


class RegionScore(Contract):
    region_code: NonEmpty
    region_name: NonEmpty
    category_scores: CategoryScores
    spatial_unit: SpatialUnit = "unknown"
    score_version: NonEmpty = "unspecified"
    sources: list[SourceMetadata] = Field(default_factory=list)
    is_mock: bool = True

    @model_validator(mode="after")
    def preserve_spatial_provenance(self):
        for source in self.sources:
            if (source.original_spatial_unit != "unknown" and self.spatial_unit != "unknown"
                    and source.original_spatial_unit != self.spatial_unit):
                raise ValueError("source spatial unit does not match scored region; pass district context separately")
            if not self.is_mock and source.is_mock:
                raise ValueError("mock source cannot be marked as real scores")
        return self


class RecommendationRequest(Contract):
    weights: Weights = Field(default_factory=Weights)
    top_k: Annotated[int, Field(strict=True, ge=1, le=5)] = 5
    min_scores: CategoryScores = Field(default_factory=CategoryScores)


class DomainInsight(Contract):
    domain: Domain
    score: Score
    contribution: Number


class RecommendationItem(RegionScore):
    rank: Annotated[int, Field(strict=True, ge=1)]
    total_score: Score
    contributions: dict[Domain, Number]
    strengths: list[DomainInsight]
    weaknesses: list[DomainInsight]


class ExcludedRegion(Contract):
    region_code: NonEmpty
    reason: Literal["missing_scores", "constraint_mismatch"]
    domains: list[Domain]


class RecommendationResult(Contract):
    normalized_weights: Weights
    items: list[RecommendationItem]
    excluded: list[ExcludedRegion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    score_version: str = "unspecified"
    spatial_unit: SpatialUnit = "unknown"
    is_mock: bool = True


class ComparisonResult(Contract):
    baseline_region_code: NonEmpty
    regions: list[RegionScore]
    recommendation: RecommendationResult
    differences: dict[str, dict[Domain, float | None]]


class ExplicitWeights(Weights):
    """LLM numeric weights must specify every domain; never invent omitted values."""
    economy: Number
    energy: Number
    comfort: Number
    health: Number
    safety: Number


class PreferenceDraft(Contract):
    weights: ExplicitWeights | None
    priority_domains: list[Domain]
    min_scores: CategoryScores
    unsupported_conditions: list[NonEmpty]
    limitations: list[NonEmpty]


class ExtractedPreferences(RecommendationRequest):
    priority_domains: list[Domain] = Field(default_factory=list)
    unsupported_conditions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    needs_confirmation: bool = True
    extraction_status: Literal["llm", "fallback"] = "llm"
    weight_source: Literal["explicit", "priority", "default", "fallback"] = "default"

    def recommendation_request(self) -> RecommendationRequest:
        return RecommendationRequest(weights=self.weights, top_k=self.top_k, min_scores=self.min_scores)


class EvidenceChunk(Contract):
    chunk_id: NonEmpty
    text: Annotated[str, Field(strict=True, min_length=1, max_length=8000)]
    source: NonEmpty
    document_title: NonEmpty
    reference_year: Annotated[int, Field(strict=True, ge=1900, le=2100)]
    region_code: NonEmpty | None = None


class EvidenceResult(Contract):
    status: Literal["found", "no_evidence"]
    chunks: list[EvidenceChunk]

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == "found") != bool(self.chunks):
            raise ValueError("evidence status must match chunks")
        ids = [c.chunk_id for c in self.chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate evidence IDs")
        return self


class ExplanationSelection(Contract):
    region_code: NonEmpty
    strength_domains: list[Domain] = Field(min_length=1, max_length=2)
    weakness_domains: list[Domain] = Field(min_length=1, max_length=2)
    evidence_ids: list[NonEmpty] = Field(max_length=10)


class ExplanationPlan(Contract):
    items: list[ExplanationSelection] = Field(max_length=5)


class RegionExplanation(Contract):
    region_code: NonEmpty
    region_name: NonEmpty
    rank: int
    total_score: Score
    spatial_unit: SpatialUnit
    score_version: NonEmpty
    advantages: str
    disadvantages: str
    limitations: list[str]
    sources: list[SourceMetadata]
    citations: list[EvidenceChunk]
    is_mock: bool


class ExplanationResult(Contract):
    generation_status: Literal["llm", "fallback", "empty"]
    items: list[RegionExplanation]
    warnings: list[str] = Field(default_factory=list)
    # Filled only from sanitized LLMError.as_dict(), never raw provider text.
    diagnostics: list[dict] = Field(default_factory=list)


class PipelineResult(Contract):
    preferences: ExtractedPreferences
    recommendation: RecommendationResult
    evidence: EvidenceResult
    explanation: ExplanationResult
