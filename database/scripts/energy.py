
from pathlib import Path
import pandas as pd

# 프로젝트 경로
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

# 입력 파일
ELECTRICITY_FILE = RAW_DIR / "2024~2026전기 사용량.xlsx"
GAS_FILE = RAW_DIR / "2024~2026가스 사용량.xlsx"

# 출력 파일
OUTPUT_FILE = PROCESSED_DIR / "fact_energy_building.csv"

# 서울시 자치구 코드
DISTRICT_CODES = {
    "종로구": "11110",
    "중구": "11140",
    "용산구": "11170",
    "성동구": "11200",
    "광진구": "11215",
    "동대문구": "11230",
    "중랑구": "11260",
    "성북구": "11290",
    "강북구": "11305",
    "도봉구": "11320",
    "노원구": "11350",
    "은평구": "11380",
    "서대문구": "11410",
    "마포구": "11440",
    "양천구": "11470",
    "강서구": "11500",
    "구로구": "11530",
    "금천구": "11545",
    "영등포구": "11560",
    "동작구": "11590",
    "관악구": "11620",
    "서초구": "11650",
    "강남구": "11680",
    "송파구": "11710",
    "강동구": "11740",
}


def load_energy_file(file_path, energy_type):
    """전기 또는 가스 엑셀을 읽어 자치구별 월간 데이터로 변환한다."""

    if not file_path.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    df = pd.read_excel(file_path, sheet_name="Sheet1")

    # 컬럼명 공백 제거
    df.columns = df.columns.astype(str).str.strip()

    # 자치구 합계 데이터만 선택
    df = df[df["데이터구분"].astype(str).str.strip() == "자치구총합"].copy()

    # 매핑되지 않는 자치구 제거
    df["자치구명"] = df["자치구명"].astype(str).str.strip()
    df = df[df["자치구명"].isin(DISTRICT_CODES)].copy()

    # 연도 및 월 컬럼 설정
    value_columns = [
        f"{month}월_{'MWh' if energy_type == 'electricity' else '천㎥'}"
        for month in range(1, 13)
    ]

    missing_columns = [col for col in value_columns if col not in df.columns]
    if missing_columns:
        raise ValueError(
            f"{file_path.name}에서 월별 컬럼을 찾을 수 없습니다: {missing_columns}"
        )

    # 월별 컬럼을 행으로 변환
    long_df = df.melt(
        id_vars=["연도", "자치구명"],
        value_vars=value_columns,
        var_name="월",
        value_name="사용량",
    )

    # 월 숫자 추출
    long_df["월"] = long_df["월"].str.extract(r"(\d+)").astype(int)

    # 숫자형 변환
    long_df["연도"] = pd.to_numeric(long_df["연도"], errors="raise").astype(int)
    long_df["사용량"] = pd.to_numeric(long_df["사용량"], errors="coerce")

    # 코드 및 연월 생성
    long_df["region_code"] = long_df["자치구명"].map(DISTRICT_CODES)
    long_df["base_ym"] = (
        long_df["연도"].astype(str)
        + long_df["월"].astype(str).str.zfill(2)
    )

    # 전기/가스별 결과 컬럼
    result_column = (
        "electricity_mwh"
        if energy_type == "electricity"
        else "gas_thousand_m3"
    )

    return long_df[
        ["region_code", "base_ym", "사용량"]
    ].rename(columns={"사용량": result_column})


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/3] 전기 데이터 읽는 중...")
    electricity = load_energy_file(ELECTRICITY_FILE, "electricity")

    print("[2/3] 가스 데이터 읽는 중...")
    gas = load_energy_file(GAS_FILE, "gas")

    print("[3/3] 전기·가스 데이터 통합 중...")

    # 지역 코드와 연월 기준으로 병합
    result = pd.merge(
        electricity,
        gas,
        on=["region_code", "base_ym"],
        how="outer",
        validate="one_to_one",
    )

    # 기존 테이블 컬럼 유지
    result["building_count"] = pd.NA
    result["avg_building_age"] = pd.NA
    result["source_level"] = "SGG"

    result = result[
        [
            "region_code",
            "base_ym",
            "electricity_mwh",
            "gas_thousand_m3",
            "building_count",
            "avg_building_age",
            "source_level",
        ]
    ]

    result = result.sort_values(
        ["base_ym", "region_code"]
    ).reset_index(drop=True)

    # 엑셀에서 한글이 깨지지 않도록 UTF-8 BOM으로 저장
    result.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig",
    )

    print(f"\n저장 완료: {OUTPUT_FILE}")
    print(f"총 행 수: {len(result):,}")
    print(f"지역 수: {result['region_code'].nunique()}")
    print(f"연월 범위: {result['base_ym'].min()} ~ {result['base_ym'].max()}")
    print("\n미리보기:")
    print(result.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
