"""Seoul Smart Life 백엔드 (시작용 버전).

실행: uvicorn app.main:app --reload
문서: http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.mock_data import DOMAINS, DONGS, MOCK_SCORES, REGIONS

app = FastAPI(title="Seoul Smart Life API", version="0.1.0")

# 프론트(React, Vite 기본 주소)에서 이 서버를 부를 수 있게 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 지역 코드로 빨리 찾을 수 있게 사전으로 바꿔 둠 (자치구 25개 + 행정동 426개)
# 자치구 코드: "gnm" 같은 3글자 / 행정동 코드: "1111051500" 같은 숫자 10자리
REGIONS_BY_CODE = {r["region_code"]: r for r in REGIONS + DONGS}


def find_region(region_code: str) -> dict:
    """지역 코드로 지역을 찾고, 없으면 404 오류를 돌려줌."""
    region = REGIONS_BY_CODE.get(region_code)
    if region is None:
        raise HTTPException(status_code=404, detail=f"'{region_code}' 지역을 찾을 수 없어요.")
    return region


@app.get("/api/health")
def health():
    """서버가 살아 있는지 확인."""
    return {"status": "ok"}


@app.get("/api/regions")
def list_regions(level: str = "district", parent: str | None = None):
    """지역 목록.

    - /api/regions                     → 자치구 25개
    - /api/regions?level=dong           → 행정동 426개 전체
    - /api/regions?level=dong&parent=jno → 종로구의 행정동만
    """
    if level == "district":
        items = REGIONS
    elif level == "dong":
        items = DONGS
        if parent is not None:
            if find_region(parent)["spatial_unit"] != "district":  # 없는 코드면 404
                raise HTTPException(status_code=422, detail="parent에는 자치구 코드(예: jno)를 넣어 주세요.")
            items = [d for d in DONGS if d["parent_region_code"] == parent]
    else:
        raise HTTPException(status_code=422, detail="level은 district(자치구) 또는 dong(행정동)만 쓸 수 있어요.")
    return {"level": level, "count": len(items), "items": items, "is_mock": True}


@app.get("/api/regions/{region_code}")
def get_region(region_code: str):
    """지역(자치구 또는 행정동) 하나의 정보."""
    return find_region(region_code)


@app.get("/api/compare")
def compare_regions(codes: str):
    """여러 지역의 5개 점수를 한 번에 비교 (2~5개). 자치구·행정동 코드 모두 가능.

    예: /api/compare?codes=gnm,map
        /api/compare?codes=1111051500,1111053000
    """
    # "gnm, map" → ["gnm", "map"] (공백 제거, 중복 제거, 순서 유지)
    code_list = list(dict.fromkeys(c.strip() for c in codes.split(",") if c.strip()))
    if not 2 <= len(code_list) <= 5:
        raise HTTPException(status_code=422, detail="비교할 지역은 2~5개를 골라 주세요.")

    items = []
    for code in code_list:
        region = find_region(code)
        scores = MOCK_SCORES[code]
        items.append({"region": region, "scores": {d: scores[d] for d in DOMAINS}})
    return {"domains": DOMAINS, "items": items, "is_mock": True}


@app.get("/api/regions/{region_code}/scores")
def get_region_scores(region_code: str):
    """지역(자치구 또는 행정동) 하나의 5개 영역 점수 (지금은 가짜 점수)."""
    region = find_region(region_code)
    scores = MOCK_SCORES[region_code]
    return {
        "region": region,
        "scores": {d: scores[d] for d in DOMAINS},
        "is_mock": True,
    }
