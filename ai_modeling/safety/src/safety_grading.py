"""Add fixed five-level statistical grades to the existing backend payload.

No training, forecasting, LLM calls, or changes to the input scores.
Run: python safety_grading.py --input original.json --output graded.json
"""
from __future__ import annotations
import argparse, copy, json, math
from pathlib import Path

GRADE_RULES = {
    "method": "fixed_score_intervals",
    "best_grade": 1,
    "worst_grade": 5,
    "score_rounding_before_grading": False,
    "missing_score_grade": None,
    "bands": [
        {"grade": 1, "label": "1등급", "min_score": 80, "max_score": 100, "min_inclusive": True, "max_inclusive": True},
        {"grade": 2, "label": "2등급", "min_score": 60, "max_score": 80, "min_inclusive": True, "max_inclusive": False},
        {"grade": 3, "label": "3등급", "min_score": 40, "max_score": 60, "min_inclusive": True, "max_inclusive": False},
        {"grade": 4, "label": "4등급", "min_score": 20, "max_score": 40, "min_inclusive": True, "max_inclusive": False},
        {"grade": 5, "label": "5등급", "min_score": 0, "max_score": 20, "min_inclusive": True, "max_inclusive": False},
    ],
    "interpretation": "기존 상대 치안점수의 고정 구간 등급. 등급별 인원·동 수를 같게 나누는 방식이 아니며 절대적 안전이나 피해확률을 뜻하지 않음.",
}

def grade_from_score(score):
    if score is None:
        return None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("score must be a finite number in [0, 100] or null")
    for threshold, grade in ((80, 1), (60, 2), (40, 3), (20, 4), (0, 5)):
        if score >= threshold:
            return grade
    raise AssertionError("Unreachable score")

def forbidden_paths(value, path="$."):
    """Forecast fields are disallowed instead of being silently repurposed."""
    hits = []
    if isinstance(value, dict):
        for key, child in value.items():
            if any(token in key.lower() for token in ("forecast", "predict", "예측")):
                hits.append(path + key)
            hits.extend(forbidden_paths(child, path + key + "."))
    elif isinstance(value, list):
        for i, child in enumerate(value):
            hits.extend(forbidden_paths(child, path + str(i) + "."))
    return hits

def apply_grades(payload):
    if forbidden_paths(payload):
        raise ValueError("Input contains forecast fields; select the statistical safety payload")
    result = copy.deepcopy(payload)
    items = result.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Nonempty backend items list is required")
    for item in items:
        grade = grade_from_score(item["scores"]["safety"])
        metadata = item["metadata"]["safety"]
        metadata["grade"] = grade
        metadata["grade_label"] = f"{grade}등급" if grade is not None else None
    metadata = result["metadata"]["safety"]
    metadata["grade_rules"] = copy.deepcopy(GRADE_RULES)
    for profile in metadata.get("profiles", []):
        grade = grade_from_score(profile["score"])
        profile["grade"] = grade
        profile["grade_label"] = f"{grade}등급" if grade is not None else None
    assert not forbidden_paths(result)
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
    result = apply_grades(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
