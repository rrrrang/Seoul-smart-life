"""Synthetic scores only, never RAG evidence or actual Seoul statistics."""
from .schemas import DOMAINS, RegionScore


def get_mock_regions() -> list[RegionScore]:
    fixtures = [
        ("MOCK_DONG_001", "가상동 A", [80, 85, 90, 85, 90]),
        ("MOCK_DONG_002", "가상동 B", [85, 80, 85, 85, 85]),
        ("MOCK_DONG_003", "가상동 C", [80, 80, 85, 85, 80]),
        ("MOCK_DONG_004", "가상동 D", [80, 80, 80, 80, 80]),
        ("MOCK_DONG_005", "가상동 E", [75, 75, 80, 80, 80]),
        ("MOCK_DONG_006", "가상동 F", [90, 80, 60, 80, 60]),
        ("MOCK_DONG_007", "가상동 G", [80, 80, 80, 80, None]),
    ]
    return [RegionScore(region_code=code, region_name=name, spatial_unit="administrative_dong",
        score_version="mock-v1", category_scores=dict(zip(DOMAINS, scores)), is_mock=True,
        sources=[{"source": "팀 합성 데이터", "document_title": "추천 인터페이스 테스트용 가상 점수",
                  "reference_year": 2025, "original_spatial_unit": "administrative_dong", "is_mock": True}])
        for code, name, scores in fixtures]
