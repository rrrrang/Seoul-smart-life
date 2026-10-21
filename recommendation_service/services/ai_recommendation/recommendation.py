"""Pure Python/Pandas/NumPy recommendation. Never calls an LLM or DB."""
from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from .schemas import (
    DOMAINS, CategoryScores, ComparisonResult, DomainInsight, ExcludedRegion,
    RecommendationItem, RecommendationRequest, RecommendationResult, RegionScore, Weights,
)


def normalize_weights(weights: Weights | Mapping) -> Weights:
    validated = Weights.model_validate(weights)
    vector = np.array(list(validated.model_dump().values()), dtype=float)
    # Scaling first avoids overflow for large, otherwise valid finite weights.
    scaled = vector / vector.max()
    normalized = scaled / scaled.sum()
    return Weights.model_validate(dict(zip(DOMAINS, normalized.tolist())))


def calculate_total_score(category_scores: CategoryScores | Mapping, weights: Weights | Mapping) -> float:
    scores = CategoryScores.model_validate(category_scores).model_dump()
    original = Weights.model_validate(weights)
    normalized = normalize_weights(original).model_dump()
    missing = [d for d in DOMAINS if getattr(original, d) > 0 and scores[d] is None]
    if missing:
        raise ValueError(f"missing required scores: {', '.join(missing)}")
    value = np.dot([normalized[d] for d in DOMAINS], [scores[d] or 0 for d in DOMAINS])
    return float(np.clip(value, 0, 100))


def _regions(rows: Iterable[RegionScore | Mapping]) -> list[RegionScore]:
    result = [RegionScore.model_validate(row) for row in rows]
    codes = [row.region_code for row in result]
    if len(codes) != len(set(codes)):
        raise ValueError("duplicate region_code")
    if len({row.spatial_unit for row in result}) > 1:
        raise ValueError("mixed spatial units cannot be ranked together")
    if len({row.score_version for row in result}) > 1:
        raise ValueError("mixed score versions cannot be ranked together")
    return result


def _insights(row: RegionScore, weights: Weights):
    scores = row.category_scores.model_dump()
    contributions = {d: round((scores[d] or 0) * getattr(weights, d), 6) for d in DOMAINS}
    available = [d for d in DOMAINS if scores[d] is not None]
    # Relative strengths/weaknesses are score-based, not inferred city statistics.
    best = sorted(available, key=lambda d: (-scores[d], DOMAINS.index(d)))[:2]
    worst = sorted(available, key=lambda d: (scores[d], DOMAINS.index(d)))[:2]
    def entries(domains):
        return [DomainInsight(domain=d, score=scores[d], contribution=contributions[d]) for d in domains]
    return contributions, entries(best), entries(worst)


def recommend_regions(
    regions: Iterable[RegionScore | Mapping], preferences: RecommendationRequest | Mapping,
) -> RecommendationResult:
    request = RecommendationRequest.model_validate(preferences)
    rows = _regions(regions)
    weights = normalize_weights(request.weights)
    minimum = request.min_scores.model_dump()
    excluded = []
    eligible = []
    warnings = set()
    for row in rows:
        if row.is_mock:
            warnings.add("SYNTHETIC_DATA")
        if not row.sources or any(source.reference_year is None for source in row.sources):
            warnings.add("SOURCE_METADATA_MISSING")
        if row.spatial_unit == "unknown" or any(s.original_spatial_unit == "unknown" for s in row.sources):
            warnings.add("SPATIAL_UNIT_UNKNOWN")
        if row.score_version == "unspecified":
            warnings.add("SCORE_VERSION_UNSPECIFIED")
        scores = row.category_scores.model_dump()
        missing = [d for d in DOMAINS if scores[d] is None and (getattr(request.weights, d) > 0 or minimum[d] is not None)]
        failed = [d for d in DOMAINS if minimum[d] is not None and scores[d] is not None and scores[d] < minimum[d]]
        if missing or failed:
            excluded.append(ExcludedRegion(region_code=row.region_code,
                reason="missing_scores" if missing else "constraint_mismatch", domains=missing or failed))
        else:
            eligible.append(row)
    items = []
    if eligible:
        frame = pd.DataFrame([r.category_scores.model_dump() for r in eligible], columns=DOMAINS)
        totals = np.clip(frame.fillna(0).to_numpy(dtype=float) @ np.array(list(weights.model_dump().values())), 0, 100)
        ordered = sorted(zip(eligible, totals.tolist()), key=lambda pair: (-pair[1], pair[0].region_code))
        for rank, (row, total) in enumerate(ordered[:request.top_k], 1):
            contributions, strengths, weaknesses = _insights(row, weights)
            items.append(RecommendationItem(**row.model_dump(), rank=rank, total_score=round(total, 6),
                contributions=contributions, strengths=strengths, weaknesses=weaknesses))
    return RecommendationResult(normalized_weights=weights, items=items, excluded=excluded,
        warnings=sorted(warnings), score_version=rows[0].score_version if rows else "unspecified",
        spatial_unit=rows[0].spatial_unit if rows else "unknown", is_mock=any(r.is_mock for r in rows) if rows else True)


def compare_regions(
    regions: Iterable[RegionScore | Mapping], region_codes: list[str],
    preferences: RecommendationRequest | Mapping,
) -> ComparisonResult:
    rows = _regions(regions)
    if not 1 <= len(region_codes) <= 5 or len(set(region_codes)) != len(region_codes):
        raise ValueError("compare 1 to 5 unique region codes")
    lookup = {row.region_code: row for row in rows}
    if any(code not in lookup for code in region_codes):
        raise ValueError("comparison region not found")
    selected = [lookup[code] for code in region_codes]
    baseline = selected[0].category_scores.model_dump()
    differences = {}
    for row in selected:
        scores = row.category_scores.model_dump()
        differences[row.region_code] = {d: None if baseline[d] is None or scores[d] is None
            else round(scores[d] - baseline[d], 6) for d in DOMAINS}
    request = RecommendationRequest.model_validate(preferences)
    request = request.model_copy(update={"top_k": len(selected)})
    return ComparisonResult(baseline_region_code=selected[0].region_code, regions=selected,
        recommendation=recommend_regions(selected, request), differences=differences)
