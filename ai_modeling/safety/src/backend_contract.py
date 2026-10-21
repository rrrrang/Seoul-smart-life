"""점수·근거를 보존하는 백엔드 형식 변환."""
from copy import deepcopy
import math
from evaluation_contract import load_region_master, validate_evaluation
DOMAINS = ["economy", "energy", "comfort", "health", "safety"]
ROW_CORE = {"region_code", "region_name", "sigungu_code", "score"}

def convert(source, master):
    validate_evaluation(source, require_all=True, delivery=True)
    if source["domain"] != "safety":
        raise ValueError("치안 결과만 변환할 수 있습니다.")
    items = []
    for row in source["results"]:
        ref = master[row["region_code"]]
        scores = dict.fromkeys(DOMAINS, None)
        scores["safety"] = row["score"]
        items.append({
            "region": {
                "region_code": ref["region_code"],
                "name_ko": ref["region_name"],
                "sigungu_code": ref["sigungu_code"],
                "spatial_unit": "dong",
            },
            "scores": scores,
            "metadata": {"safety": {k: deepcopy(v) for k, v in row.items()
                                     if k not in ROW_CORE}},
        })
    # metadata는 기존 API의 필수 항목이 아니라 계산 근거 보존용 확장이다.
    return {
        "domains": list(DOMAINS),
        "items": items,
        "is_mock": False,
        "metadata": {"safety": {k: deepcopy(v) for k, v in source.items()
                                 if k not in {"domain", "results"}}},
    }

def validate_backend(payload, source, master):
    if payload["domains"] != DOMAINS or payload["is_mock"] is not False:
        raise ValueError("백엔드 영역 키 또는 is_mock 오류")
    if len(payload["items"]) != 427:
        raise ValueError("427개 행정동이 필요합니다.")
    restored = {"domain": "safety", **deepcopy(payload["metadata"]["safety"]), "results": []}
    codes = set()
    for item in payload["items"]:
        region, scores = item["region"], item["scores"]
        code = region["region_code"]
        if not isinstance(code, str) or len(code) != 6 or code not in master or code in codes:
            raise ValueError("행정동 코드·중복 오류: " + str(code))
        codes.add(code)
        expected = {
            "region_code": code, "name_ko": master[code]["region_name"],
            "sigungu_code": master[code]["sigungu_code"], "spatial_unit": "dong",
        }
        if region != expected:
            raise ValueError("지역 기준표 불일치: " + code)
        if set(scores) != set(DOMAINS):
            raise ValueError("5개 영역 키 불일치")
        if any(scores[d] is not None for d in DOMAINS if d != "safety"):
            raise ValueError("다른 영역 점수는 전달받기 전까지 null이어야 합니다.")
        score = scores["safety"]
        if score is not None and (isinstance(score, bool) or not isinstance(score, (int, float))
                                  or not math.isfinite(score) or not 0 <= score <= 100):
            raise ValueError("치안점수 범위·자료형 오류")
        restored["results"].append({
            "region_code": code, "region_name": region["name_ko"],
            "sigungu_code": region["sigungu_code"], "score": score,
            **deepcopy(item["metadata"]["safety"]),
        })
    if codes != set(master):
        raise ValueError("행정동 누락 또는 초과")
    # 역변환하면 원래 JSON과 완전히 같아야 한다. 점수·상태·기간·근거도 검사한다.
    if restored != source:
        raise ValueError("변환 중 점수 또는 근거가 바뀌거나 누락됐습니다.")
    validate_evaluation(restored, require_all=True, delivery=True)
    return True
