"""평가 결과의 공통 지역코드와 점수 형식 검증."""
from pathlib import Path
import csv, math, re

ROOT = Path(__file__).resolve().parents[1]
MASTER_PATH = ROOT / "data/서울_지역_기준.csv"
DOMAINS = {"economy", "safety", "energy", "comfort", "health"}
STATUSES = {"calculated_draft", "calculated", "insufficient_data"}

def load_region_master(path=None):
    path = Path(path) if path else MASTER_PATH
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    master = {}
    for row in rows:
        code, gu = row["region_code"], row["sigungu_code"]
        if not re.fullmatch(r"11\d{8}", code) or not re.fullmatch(r"11\d{3}", gu):
            raise ValueError("기준표 코드 형식 오류")
        if code in master or code[:5] != gu or not row["region_name"]:
            raise ValueError("기준표 중복·이름·자치구 오류")
        master[code] = row
    if len(master) != 427 or len({r["sigungu_code"] for r in rows}) != 25:
        raise ValueError("합의된 기준표는 427행정동·25자치구입니다.")
    return master

def validate_regions(rows, require_all=False, master=None):
    master = load_region_master() if master is None else master
    seen = set()
    for row in rows:
        code = row.get("region_code")
        if not isinstance(code, str) or code not in master:
            raise ValueError("기준표에 없는 region_code: " + str(code))
        if code in seen:
            raise ValueError("duplicate region_code: " + code)
        seen.add(code)
        for key in ("region_name", "sigungu_code"):
            if row.get(key) != master[code][key]:
                raise ValueError(code + ": 기준표와 " + key + " 불일치")
    if require_all and seen != set(master):
        raise ValueError("427개 행정동 누락 또는 초과")
    return True

def validate_evaluation(payload, require_all=False, delivery=False):
    if payload.get("domain") not in DOMAINS:
        raise ValueError("평가 domain 오류")
    rows = payload.get("results")
    if not isinstance(rows, list) or not rows:
        raise ValueError("results 목록 필요")
    validate_regions(rows, require_all=require_all)
    for row in rows:
        if "score" not in row or row.get("status") not in STATUSES:
            raise ValueError("score/status 누락 또는 오류")
        if any(k in row for k in ("safety_score", "economy_score", "dong_code", "dong_name")):
            raise ValueError("이전 결과 항목 이름이 남아 있습니다.")
        value = row["score"]
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) or not 0 <= value <= 100):
            raise ValueError("score는 0~100의 유한한 숫자 또는 null입니다.")
        if (value is None) != (row["status"] == "insufficient_data"):
            raise ValueError("점수 유무와 status가 일치하지 않습니다.")
    if delivery:
        forbidden = {"model_version", "created_at", "crime_forecast",
                     "crime_forecast_metadata", "crime_forecast_regions"}
        def scan(obj):
            if isinstance(obj, dict):
                if forbidden.intersection(obj):
                    raise ValueError("공유용 결과에 제외 항목이 남아 있습니다.")
                for v in obj.values(): scan(v)
            elif isinstance(obj, list):
                for v in obj: scan(v)
        scan(payload)
    return True
