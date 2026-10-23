
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException

# backend/.env에서 인증키 읽기
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(ENV_PATH)

router = APIRouter(prefix="/api/environment", tags=["환경 관측"])

SEOUL_API_URL = "http://openapi.seoul.go.kr:8088"


def parse_number(value):
    """측정값이 없으면 None, 숫자이면 float로 변환."""
    if value is None or str(value).strip() in ("", "-", "점검중"):
        return None

    try:
        return float(value)
    except (ValueError, TypeError):
        return None


@router.get("/air-quality")
def get_air_quality(district: str | None = None):
    """서울시 자치구별 최신 PM2.5·PM10 조회."""
    api_key = os.getenv("SEOUL_OPENAPI_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="서울시 OpenAPI 인증키가 설정되지 않았습니다."
        )

    url = (
        f"{SEOUL_API_URL}/{api_key}/json/"
        "ListAirQualityByDistrictService/1/25/"
    )

    try:
        with urlopen(url, timeout=10) as response:
            data = json.load(response)

    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"서울시 대기환경 API 요청 실패: {type(error).__name__}"
        ) from error

    service = data.get("ListAirQualityByDistrictService")

    if not isinstance(service, dict):
        error_info = data.get("RESULT", {})
        raise HTTPException(
            status_code=502,
            detail={
                "message": "서울시 API 응답 오류",
                "api_result": error_info,
            },
        )

    result = service.get("RESULT", {})
    if result.get("CODE") != "INFO-000":
        raise HTTPException(
            status_code=502,
            detail=f"서울시 API 응답 오류: {result.get('MESSAGE', '확인 필요')}"
        )

    items = []

    for row in service.get("row", []):
        items.append({
            "district": row.get("MSRSTN_NM"),
            "observed_at": row.get("MSRMT_YMD"),
            "pm25": parse_number(row.get("FPM")),
            "pm10": parse_number(row.get("PM")),
        })

    if district:
        items = [
            item for item in items
            if item["district"] == district
        ]

        if not items:
            raise HTTPException(
                status_code=404,
                detail=f"{district}의 대기환경 관측값을 찾을 수 없습니다."
            )

    return {
        "source": "서울시 실시간 자치구별 대기환경 현황",
        "count": len(items),
        "items": items,
    }
