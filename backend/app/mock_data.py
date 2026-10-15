"""가짜(Mock) 데이터.

진짜 데이터가 나오기 전까지 프론트 개발용으로 쓰는 값이에요.
점수는 실제 통계가 아니라 임의로 정한 숫자예요.
지역 코드는 팀 슬랙(희구님, 10/13)의 3글자 코드를 따랐어요.
"""

# 5개 평가 영역 키 (팀 공통 약속)
DOMAINS = ["economy", "energy", "comfort", "health", "safety"]

# 서울 25개 자치구
REGIONS = [
    {"region_code": "gnm", "name_ko": "강남구", "name_en": "Gangnam"},
    {"region_code": "gnd", "name_ko": "강동구", "name_en": "Gangdong"},
    {"region_code": "gnb", "name_ko": "강북구", "name_en": "Gangbuk"},
    {"region_code": "gns", "name_ko": "강서구", "name_en": "Gangseo"},
    {"region_code": "gwk", "name_ko": "관악구", "name_en": "Gwanak"},
    {"region_code": "gwj", "name_ko": "광진구", "name_en": "Gwangjin"},
    {"region_code": "gro", "name_ko": "구로구", "name_en": "Guro"},
    {"region_code": "gch", "name_ko": "금천구", "name_en": "Geumcheon"},
    {"region_code": "nwn", "name_ko": "노원구", "name_en": "Nowon"},
    {"region_code": "dbg", "name_ko": "도봉구", "name_en": "Dobong"},
    {"region_code": "ddm", "name_ko": "동대문구", "name_en": "Dongdaemun"},
    {"region_code": "djk", "name_ko": "동작구", "name_en": "Dongjak"},
    {"region_code": "map", "name_ko": "마포구", "name_en": "Mapo"},
    {"region_code": "sdm", "name_ko": "서대문구", "name_en": "Seodaemun"},
    {"region_code": "sch", "name_ko": "서초구", "name_en": "Seocho"},
    {"region_code": "sdg", "name_ko": "성동구", "name_en": "Seongdong"},
    {"region_code": "sbk", "name_ko": "성북구", "name_en": "Seongbuk"},
    {"region_code": "spg", "name_ko": "송파구", "name_en": "Songpa"},
    {"region_code": "ycn", "name_ko": "양천구", "name_en": "Yangcheon"},
    {"region_code": "ydp", "name_ko": "영등포구", "name_en": "Yeongdeungpo"},
    {"region_code": "ysn", "name_ko": "용산구", "name_en": "Yongsan"},
    {"region_code": "eyp", "name_ko": "은평구", "name_en": "Eunpyeong"},
    {"region_code": "jno", "name_ko": "종로구", "name_en": "Jongno"},
    {"region_code": "jng", "name_ko": "중구", "name_en": "Jung"},
    {"region_code": "jnn", "name_ko": "중랑구", "name_en": "Jungnang"},
]

# 자치구별 가짜 점수 (0~100)
MOCK_SCORES = {
    "gnm": {"economy": 90, "energy": 57, "comfort": 51, "health": 67, "safety": 65},
    "gnd": {"economy": 64, "energy": 58, "comfort": 56, "health": 93, "safety": 84},
    "gnb": {"economy": 55, "energy": 87, "comfort": 77, "health": 52, "safety": 51},
    "gns": {"economy": 55, "energy": 63, "comfort": 64, "health": 82, "safety": 88},
    "gwk": {"economy": 51, "energy": 85, "comfort": 62, "health": 95, "safety": 91},
    "gwj": {"economy": 94, "energy": 84, "comfort": 76, "health": 64, "safety": 78},
    "gro": {"economy": 87, "energy": 67, "comfort": 50, "health": 60, "safety": 94},
    "gch": {"economy": 77, "energy": 71, "comfort": 67, "health": 59, "safety": 63},
    "nwn": {"economy": 71, "energy": 56, "comfort": 55, "health": 74, "safety": 56},
    "dbg": {"economy": 72, "energy": 72, "comfort": 88, "health": 66, "safety": 52},
    "ddm": {"economy": 79, "energy": 84, "comfort": 57, "health": 74, "safety": 55},
    "djk": {"economy": 85, "energy": 68, "comfort": 90, "health": 89, "safety": 73},
    "map": {"economy": 86, "energy": 62, "comfort": 95, "health": 54, "safety": 52},
    "sdm": {"economy": 92, "energy": 64, "comfort": 68, "health": 55, "safety": 64},
    "sch": {"economy": 56, "energy": 74, "comfort": 67, "health": 79, "safety": 90},
    "sdg": {"economy": 73, "energy": 60, "comfort": 73, "health": 72, "safety": 63},
    "sbk": {"economy": 92, "energy": 67, "comfort": 94, "health": 93, "safety": 91},
    "spg": {"economy": 54, "energy": 88, "comfort": 90, "health": 60, "safety": 84},
    "ycn": {"economy": 65, "energy": 60, "comfort": 79, "health": 74, "safety": 67},
    "ydp": {"economy": 90, "energy": 94, "comfort": 85, "health": 64, "safety": 93},
    "ysn": {"economy": 70, "energy": 53, "comfort": 64, "health": 52, "safety": 70},
    "eyp": {"economy": 75, "energy": 67, "comfort": 54, "health": 63, "safety": 86},
    "jno": {"economy": 95, "energy": 70, "comfort": 63, "health": 91, "safety": 81},
    "jng": {"economy": 75, "energy": 91, "comfort": 79, "health": 59, "safety": 66},
    "jnn": {"economy": 58, "energy": 65, "comfort": 85, "health": 84, "safety": 66},
}
