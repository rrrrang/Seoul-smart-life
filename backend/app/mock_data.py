"""가짜(Mock) 데이터.

진짜 데이터가 나오기 전까지 프론트 개발용으로 쓰는 값이에요.
점수는 실제 통계가 아니라 임의로 정한 숫자예요.
지역 코드는 팀 DB 설계(database/ddl)와 프론트에 맞춰 공식 코드를 써요.
- 자치구: 시군구 코드 5자리 (예: 11680 = 강남구)
- 행정동: 행정동 코드 10자리 (예: 1111051500 = 청운효자동)
3글자 코드(gnm 등)는 short_code로 남겨 두어 예전 주소도 동작해요.
"""

import hashlib
import json
from pathlib import Path

# 5개 평가 영역 키 (팀 공통 약속)
DOMAINS = ["economy", "energy", "comfort", "health", "safety"]

# 서울 25개 자치구 (region_code = 시군구 코드 5자리)
REGIONS = [
    {"region_code": "11680", "short_code": "gnm", "name_ko": "강남구", "name_en": "Gangnam"},
    {"region_code": "11740", "short_code": "gnd", "name_ko": "강동구", "name_en": "Gangdong"},
    {"region_code": "11305", "short_code": "gnb", "name_ko": "강북구", "name_en": "Gangbuk"},
    {"region_code": "11500", "short_code": "gns", "name_ko": "강서구", "name_en": "Gangseo"},
    {"region_code": "11620", "short_code": "gwk", "name_ko": "관악구", "name_en": "Gwanak"},
    {"region_code": "11215", "short_code": "gwj", "name_ko": "광진구", "name_en": "Gwangjin"},
    {"region_code": "11530", "short_code": "gro", "name_ko": "구로구", "name_en": "Guro"},
    {"region_code": "11545", "short_code": "gch", "name_ko": "금천구", "name_en": "Geumcheon"},
    {"region_code": "11350", "short_code": "nwn", "name_ko": "노원구", "name_en": "Nowon"},
    {"region_code": "11320", "short_code": "dbg", "name_ko": "도봉구", "name_en": "Dobong"},
    {"region_code": "11230", "short_code": "ddm", "name_ko": "동대문구", "name_en": "Dongdaemun"},
    {"region_code": "11590", "short_code": "djk", "name_ko": "동작구", "name_en": "Dongjak"},
    {"region_code": "11440", "short_code": "map", "name_ko": "마포구", "name_en": "Mapo"},
    {"region_code": "11410", "short_code": "sdm", "name_ko": "서대문구", "name_en": "Seodaemun"},
    {"region_code": "11650", "short_code": "sch", "name_ko": "서초구", "name_en": "Seocho"},
    {"region_code": "11200", "short_code": "sdg", "name_ko": "성동구", "name_en": "Seongdong"},
    {"region_code": "11290", "short_code": "sbk", "name_ko": "성북구", "name_en": "Seongbuk"},
    {"region_code": "11710", "short_code": "spg", "name_ko": "송파구", "name_en": "Songpa"},
    {"region_code": "11470", "short_code": "ycn", "name_ko": "양천구", "name_en": "Yangcheon"},
    {"region_code": "11560", "short_code": "ydp", "name_ko": "영등포구", "name_en": "Yeongdeungpo"},
    {"region_code": "11170", "short_code": "ysn", "name_ko": "용산구", "name_en": "Yongsan"},
    {"region_code": "11380", "short_code": "eyp", "name_ko": "은평구", "name_en": "Eunpyeong"},
    {"region_code": "11110", "short_code": "jno", "name_ko": "종로구", "name_en": "Jongno"},
    {"region_code": "11140", "short_code": "jng", "name_ko": "중구", "name_en": "Jung"},
    {"region_code": "11260", "short_code": "jnn", "name_ko": "중랑구", "name_en": "Jungnang"},
]

# 자치구별 가짜 점수 (0~100)
MOCK_SCORES = {
    "11680": {"economy": 90, "energy": 57, "comfort": 51, "health": 67, "safety": 65},
    "11740": {"economy": 64, "energy": 58, "comfort": 56, "health": 93, "safety": 84},
    "11305": {"economy": 55, "energy": 87, "comfort": 77, "health": 52, "safety": 51},
    "11500": {"economy": 55, "energy": 63, "comfort": 64, "health": 82, "safety": 88},
    "11620": {"economy": 51, "energy": 85, "comfort": 62, "health": 95, "safety": 91},
    "11215": {"economy": 94, "energy": 84, "comfort": 76, "health": 64, "safety": 78},
    "11530": {"economy": 87, "energy": 67, "comfort": 50, "health": 60, "safety": 94},
    "11545": {"economy": 77, "energy": 71, "comfort": 67, "health": 59, "safety": 63},
    "11350": {"economy": 71, "energy": 56, "comfort": 55, "health": 74, "safety": 56},
    "11320": {"economy": 72, "energy": 72, "comfort": 88, "health": 66, "safety": 52},
    "11230": {"economy": 79, "energy": 84, "comfort": 57, "health": 74, "safety": 55},
    "11590": {"economy": 85, "energy": 68, "comfort": 90, "health": 89, "safety": 73},
    "11440": {"economy": 86, "energy": 62, "comfort": 95, "health": 54, "safety": 52},
    "11410": {"economy": 92, "energy": 64, "comfort": 68, "health": 55, "safety": 64},
    "11650": {"economy": 56, "energy": 74, "comfort": 67, "health": 79, "safety": 90},
    "11200": {"economy": 73, "energy": 60, "comfort": 73, "health": 72, "safety": 63},
    "11290": {"economy": 92, "energy": 67, "comfort": 94, "health": 93, "safety": 91},
    "11710": {"economy": 54, "energy": 88, "comfort": 90, "health": 60, "safety": 84},
    "11470": {"economy": 65, "energy": 60, "comfort": 79, "health": 74, "safety": 67},
    "11560": {"economy": 90, "energy": 94, "comfort": 85, "health": 64, "safety": 93},
    "11170": {"economy": 70, "energy": 53, "comfort": 64, "health": 52, "safety": 70},
    "11380": {"economy": 75, "energy": 67, "comfort": 54, "health": 63, "safety": 86},
    "11110": {"economy": 95, "energy": 70, "comfort": 63, "health": 91, "safety": 81},
    "11140": {"economy": 75, "energy": 91, "comfort": 79, "health": 59, "safety": 66},
    "11260": {"economy": 58, "energy": 65, "comfort": 85, "health": 84, "safety": 66},
}

# 각 자치구에 "자치구 단위"라는 표시를 붙임
for _r in REGIONS:
    _r["spatial_unit"] = "district"

# 서울 행정동 426개 (코드는 행정안전부 10자리 행정동 코드)
# 출처: vuski/admdongkor 2025-01-01 기준 행정동 목록
DONGS = json.loads((Path(__file__).parent / "data" / "seoul_dongs.json").read_text(encoding="utf-8"))
for _d in DONGS:
    _d["spatial_unit"] = "dong"


def _mock_offset(code: str, domain: str) -> int:
    """코드마다 항상 같은 -10~+10 사이 숫자를 만듦 (실행할 때마다 바뀌지 않게)."""
    digest = hashlib.md5(f"{code}:{domain}".encode()).digest()
    return digest[0] % 21 - 10


# 행정동 가짜 점수: 소속 자치구 점수에서 조금씩(-10~+10) 다르게
for _d in DONGS:
    _parent = MOCK_SCORES[_d["parent_region_code"]]
    MOCK_SCORES[_d["region_code"]] = {
        dom: max(0, min(100, _parent[dom] + _mock_offset(_d["region_code"], dom))) for dom in DOMAINS
    }
