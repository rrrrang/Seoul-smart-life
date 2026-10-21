"""Load the two supplied domain scores without assigning other domains a zero."""
from copy import deepcopy
import json
import math
from pathlib import Path
import re

DOMAINS = ("economy", "energy", "comfort", "health", "safety")


def _read_domain(path: Path, domain: str) -> tuple[dict, dict]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if payload.get("is_mock") is not False:
        raise ValueError(f"{domain}: mock 여부가 명시된 실제 결과가 필요합니다.")
    if payload.get("domains") != list(DOMAINS):
        raise ValueError(f"{domain}: 영역 목록이 다릅니다.")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) != 427:
        raise ValueError(f"{domain}: 427개 행정동 결과가 필요합니다.")
    rows = {}
    for item in items:
        region = item["region"]
        code, gu = region.get("region_code"), region.get("sigungu_code")
        if not isinstance(code, str) or re.fullmatch(r"\d{6}", code) is None:
            raise ValueError(f"{domain}: region_code는 6자리 문자열이어야 합니다.")
        if not isinstance(gu, str) or re.fullmatch(r"\d{5}", gu) is None:
            raise ValueError(f"{domain}: sigungu_code는 5자리 문자열이어야 합니다.")
        if code in rows or "region_short_code" in region:
            raise ValueError(f"{domain}: 중복 코드 또는 이전 항목명이 있습니다.")
        if region.get("spatial_unit") != "dong" or not region.get("name_ko"):
            raise ValueError(f"{domain}: 행정동 단위와 이름을 확인하세요.")
        scores = item["scores"]
        value = scores.get(domain)
        if set(scores) != set(DOMAINS):
            raise ValueError(f"{domain}: 영역별 점수 키가 다릅니다.")
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not 0 <= value <= 100):
            raise ValueError(f"{domain}: {code} 점수는 유한한 0~100 숫자여야 합니다.")
        if any(scores[d] is not None for d in DOMAINS if d != domain):
            raise ValueError(f"{domain}: 담당하지 않은 영역의 점수가 포함되었습니다.")
        if domain not in item.get("metadata", {}):
            raise ValueError(f"{domain}: 계산 근거가 누락되었습니다.")
        detail = item["metadata"][domain]
        expected_grade = next(g for threshold, g in ((80, 1), (60, 2), (40, 3), (20, 4), (0, 5))
                              if value >= threshold)
        if (type(detail.get("grade")) is not int or detail["grade"] != expected_grade
                or detail.get("grade_label") != f"{expected_grade}등급"):
            raise ValueError(f"{domain}: {code} 등급은 반올림 전 점수의 20점 구간과 일치해야 합니다.")
        rows[code] = item
    return payload, rows


def load_scores(*, target_month: str, base_dir: str | Path | None = None) -> dict:
    """Return 427 joined rows. The caller supplies the month it intends to show.

    This function does not alter a backend's region identifiers, rank regions,
    or combine economic and safety scores into a recommendation score.
    """
    if not isinstance(target_month, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", target_month):
        raise ValueError("target_month는 YYYY-MM 형식이어야 합니다.")
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    economy, econ = _read_domain(root / "economy/results/economy_scores.json", "economy")
    safety, safe = _read_domain(root / "safety/results/safety_scores.json", "safety")
    if set(econ) != set(safe):
        raise ValueError("경제와 치안의 행정동 목록이 다릅니다.")
    merged = []
    for code in sorted(econ):
        e, s = econ[code], safe[code]
        if e["region"] != s["region"]:
            raise ValueError(f"{code}: 영역 간 행정동 이름 또는 자치구가 다릅니다.")
        detail = e["metadata"]["economy"]
        if detail.get("target_month") != target_month:
            raise ValueError(f"경제 추정월이 {target_month}와 다릅니다. 새 월의 결과를 생성해야 합니다.")
        if detail.get("status") != "estimated":
            raise ValueError("경제 현재월 값에는 estimated 표시가 필요합니다.")
        scores = dict.fromkeys(DOMAINS)
        scores["economy"] = e["scores"]["economy"]
        scores["safety"] = s["scores"]["safety"]
        merged.append({"region": deepcopy(e["region"]), "scores": scores,
                       "metadata": {"economy": deepcopy(detail), "safety": deepcopy(s["metadata"]["safety"])}})
    return {"domains": list(DOMAINS), "items": merged, "is_mock": False,
            "available_domains": ["economy", "safety"],
            "metadata": {"economy": deepcopy(economy.get("metadata", {}).get("economy", {})),
                         "safety": deepcopy(safety.get("metadata", {}).get("safety", {}))}}
