"""Seoul Smart Life 백엔드 (시작용 버전).

실행: uvicorn app.main:app --reload
문서: http://127.0.0.1:8000/docs
"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
import sys

# Preserve the previous `cd backend; uvicorn app.main:app` launch path.
_project_root = str(Path(__file__).resolve().parents[2])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from .mock_data import DOMAINS, DONGS, MOCK_DOMAINS, MOCK_SCORES, REGIONS, SAFETY_GRADES

legacy_router = APIRouter(tags=["기존 Mock API"])

# 지역 코드로 빨리 찾을 수 있게 사전으로 바꿔 둠 (자치구 25개 + 행정동 427개)
# 자치구 코드: "11680" 같은 숫자 5자리 / 행정동 코드: "1111051500" 같은 숫자 10자리
REGIONS_BY_CODE = {r["region_code"]: r for r in REGIONS + DONGS}
# 예전 3글자 코드("gnm")로 불러도 찾을 수 있게 별명으로 추가
REGIONS_BY_CODE.update({r["short_code"]: r for r in REGIONS})


def find_region(region_code: str) -> dict:
    """지역 코드로 지역을 찾고, 없으면 404 오류를 돌려줌."""
    region = REGIONS_BY_CODE.get(region_code)
    if region is None:
        raise HTTPException(status_code=404, detail=f"'{region_code}' 지역을 찾을 수 없어요.")
    return region


def region_scores(region: dict) -> dict:
    """지역 하나의 5개 점수 + 치안 등급(행정동만, 1등급이 가장 좋음)."""
    scores = MOCK_SCORES[region["region_code"]]
    return {
        "region": region,
        "scores": {d: scores[d] for d in DOMAINS},
        "safety_grade": SAFETY_GRADES.get(region["region_code"]),
    }


@legacy_router.get("/api/health")
def health():
    """서버가 살아 있는지 확인."""
    return {"status": "ok"}


def regions_by_level(level: str, parent: str | None) -> list[dict]:
    """level(district/dong)과 parent(자치구 코드)에 맞는 지역 목록."""
    if level == "district":
        items = REGIONS
    elif level == "dong":
        items = DONGS
        if parent is not None:
            parent_region = find_region(parent)  # 없는 코드면 404
            if parent_region["spatial_unit"] != "district":
                raise HTTPException(status_code=422, detail="parent에는 자치구 코드(예: 11110)를 넣어 주세요.")
            items = [d for d in DONGS if d["parent_region_code"] == parent_region["region_code"]]
    else:
        raise HTTPException(status_code=422, detail="level은 district(자치구) 또는 dong(행정동)만 쓸 수 있어요.")
    return items


@legacy_router.get("/api/regions")
def list_regions(level: str = "district", parent: str | None = None):
    """지역 목록.

    - /api/regions                     → 자치구 25개
    - /api/regions?level=dong           → 행정동 427개 전체
    - /api/regions?level=dong&parent=11110 → 종로구의 행정동만
    """
    items = regions_by_level(level, parent)
    return {"level": level, "count": len(items), "items": items, "is_mock": True}


@legacy_router.get("/api/scores")
def list_scores(level: str = "district", parent: str | None = None):
    """여러 지역의 5개 점수를 한 번에 (순위·지도 색칠용).

    - /api/scores                      → 자치구 25개 점수
    - /api/scores?level=dong            → 행정동 427개 점수
    - /api/scores?level=dong&parent=11110 → 종로구 행정동 점수만
    """
    items = [region_scores(r) for r in regions_by_level(level, parent)]
    return {
        "level": level,
        "domains": DOMAINS,
        "count": len(items),
        "items": items,
        "is_mock": True,
        "mock_domains": MOCK_DOMAINS,
    }


@legacy_router.get("/api/regions/{region_code}")
def get_region(region_code: str):
    """지역(자치구 또는 행정동) 하나의 정보."""
    return find_region(region_code)


@legacy_router.get("/api/compare")
def compare_regions(codes: str):
    """여러 지역의 5개 점수를 한 번에 비교 (2~5개). 자치구·행정동 코드 모두 가능.

    예: /api/compare?codes=11680,11440
        /api/compare?codes=1111051500,1111053000
    """
    # "11680, 11440" → 지역 목록 (공백 제거, 없는 코드면 404)
    regions = [find_region(c.strip()) for c in codes.split(",") if c.strip()]
    # 같은 지역이 두 번 들어가면 하나만 남김 ("gnm"과 "11680"도 같은 지역), 순서는 유지
    regions = list({r["region_code"]: r for r in regions}.values())
    if not 2 <= len(regions) <= 5:
        raise HTTPException(status_code=422, detail="비교할 지역은 서로 다른 2~5개를 골라 주세요.")

    items = [region_scores(r) for r in regions]
    return {"domains": DOMAINS, "items": items, "is_mock": True, "mock_domains": MOCK_DOMAINS}


@legacy_router.get("/api/regions/{region_code}/scores")
def get_region_scores(region_code: str):
    """지역(자치구 또는 행정동) 하나의 5개 영역 점수 (치안만 진짜, 나머지는 가짜)."""
    region = find_region(region_code)
    return {**region_scores(region), "is_mock": True, "mock_domains": MOCK_DOMAINS}


from .recommendation_api import build_app


def create_app(repository=None, explanation_client=None):
    return build_app(legacy_router, repository=repository, explanation_client=explanation_client)


app = create_app()
