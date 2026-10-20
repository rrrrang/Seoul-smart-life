import re
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from .db import get_engine

# 1. 경로 및 테이블 설정
# ==================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / "data" / "raw"

SOURCE_FILE = RAW / "환경오염물질+배출시설_20261012175257.csv"
TABLE_NAME = "fact_environment_exposure"



# 원본 CSV 읽기
# ==================================================

def read_source():

    if not SOURCE_FILE.exists():
        raise FileNotFoundError(
            f"원본 파일을 찾을 수 없습니다: {SOURCE_FILE}"
        )

    df = pd.read_csv(
        SOURCE_FILE,
        encoding="utf-8-sig",
        header=None,
        dtype=str,
        keep_default_na=False,
    )

    if len(df) < 4:
        raise ValueError("CSV에 헤더 또는 데이터가 부족합니다.")

    if df.shape[1] < 3:
        raise ValueError("CSV의 컬럼 구조가 예상과 다릅니다.")

    print(f"[원본 읽기] {SOURCE_FILE.name}")
    print(f"[원본 크기] {df.shape[0]}행, {df.shape[1]}열")

    return df

# 환경 유형 변환
# ==================================================

def normalize_pollutant(value):

    value = str(value).strip()

    if value.startswith("001 "):
        return "대기"

    if value.startswith("002 "):
        return "수질"

    if value.startswith("003 "):
        return "소음·진동"

    return None

# 4. 시설 구분 변환
# ==================================================

def normalize_facility_category(value):

    value = str(value).strip()

    if value == "소계":
        return "소계"

    # 예: 001001 1종 -> 1종
    # 예: 003001 정온지역 -> 정온지역
    match = re.match(r"^\d+\s+(.+)$", value)

    if match:
        return match.group(1).strip()

    return value if value else None



# 지역명 변환
# ==================================================

def normalize_region(value):

    value = str(value).strip()

    # 서울시 전체 합계 행
    if value == "소계":
        return "서울특별시"

    # 001001 종로구 -> 종로구
    match = re.match(r"^\d+\s+(.+)$", value)

    if match:
        return match.group(1).strip()

    return value if value else None

# 6. 시설 수 변환
# ==================================================

def normalize_count(value):

    value = str(value).strip().replace(",", "")

    if value in ("", "...", "..", "."):
        return None

    # 통계표의 '-'는 시설 수 0으로 처리
    if value == "-":
        return 0

    number = pd.to_numeric(value, errors="coerce")

    if pd.isna(number):
        return None

    return int(number)

# 7. 원본 데이터를 세로형 데이터로 변환
# ==================================================

def build_fact_environment(df):

    records = []

    for row_idx in range(3, len(df)):
        region_name = normalize_region(df.iloc[row_idx, 1])

        if not region_name:
            continue

        for col_idx in range(2, df.shape[1]):
            year_header = str(df.iloc[0, col_idx]).strip()
            pollutant_header = str(df.iloc[1, col_idx]).strip()
            category_header = str(df.iloc[2, col_idx]).strip()

            # 연도 추출
            year_match = re.search(r"20\d{2}", year_header)

            if not year_match:
                continue

            year = int(year_match.group())

            # 환경 유형 추출
            pollutant_type = normalize_pollutant(
                pollutant_header
            )

            if pollutant_type is None:
                continue

            # 시설 구분 추출
            facility_category = normalize_facility_category(
                category_header
            )

            if facility_category is None:
                continue

            # 시설 수 변환
            facility_count = normalize_count(
                df.iloc[row_idx, col_idx]
            )

            records.append({
                "year": year,
                "region_name": region_name,
                "pollutant_type": pollutant_type,
                "facility_category": facility_category,
                "facility_count": facility_count,
            })

    fact_df = pd.DataFrame(records)

    if fact_df.empty:
        raise ValueError("전처리 결과가 없습니다.")

    print(f"[전처리 완료] {len(fact_df):,}행")
    print(
        f"[연도 범위] "
        f"{fact_df['year'].min()}~{fact_df['year'].max()}"
    )
    print(
        f"[환경 유형] "
        f"{fact_df['pollutant_type'].unique().tolist()}"
    )

    return fact_df

# 8. 행정구역 코드 연결
# ==================================================

def attach_region_code(engine, fact_df):

    query = """
        SELECT DISTINCT
            sigungu_code,
            sigungu_name
        FROM dim_region
        WHERE sigungu_code IS NOT NULL
          AND sigungu_name IS NOT NULL
    """

    region_df = pd.read_sql_query(query, engine)

    region_df["sigungu_code"] = (
        region_df["sigungu_code"].astype(str).str.strip()
    )
    region_df["sigungu_name"] = (
        region_df["sigungu_name"].astype(str).str.strip()
    )

    # 자치구 이름별 코드 매핑
    region_map = (
        region_df.drop_duplicates(subset=["sigungu_name"])
        .set_index("sigungu_name")["sigungu_code"]
        .to_dict()
    )

    # 서울시 전체 합계는 별도 지역 코드 사용
    region_map.setdefault("서울특별시", "11000")

    fact_df["region_code"] = fact_df["region_name"].map(
        region_map
    )

    # 코드가 없는 지역은 조용히 누락하지 않고 오류 발생
    missing_regions = (
        fact_df.loc[
            fact_df["region_code"].isna(),
            "region_name",
        ]
        .drop_duplicates()
        .tolist()
    )

    if missing_regions:
        raise ValueError(
            "dim_region에서 지역 코드를 찾지 못했습니다: "
            f"{missing_regions}"
        )

    fact_df["region_code"] = fact_df["region_code"].astype(str)

    # 테이블 컬럼 순서에 맞게 정렬
    fact_df = fact_df[
        [
            "year",
            "region_code",
            "region_name",
            "pollutant_type",
            "facility_category",
            "facility_count",
        ]
    ]

    print("[지역 코드 연결 완료]")

    return fact_df

# PostgreSQL 테이블 적재
# ==================================================

def load_fact_environment(engine, fact_df):

    with engine.begin() as conn:
        # 테이블은 DBeaver에서 미리 생성되어 있어야 한다.
        conn.execute(
            text(f"DELETE FROM {TABLE_NAME}")
        )

        fact_df.to_sql(
            name=TABLE_NAME,
            con=conn,
            if_exists="append",
            index=False,
            chunksize=1000,
            method="multi",
        )

    print(
        f"[적재 완료] {TABLE_NAME}: "
        f"{len(fact_df):,}행"
    )



# 실행
# ==================================================

def main():
    print("=" * 50)
    print("환경오염물질 및 배출시설 데이터 ETL 시작")
    print("=" * 50)

    engine = get_engine()

    try:
        # 1) CSV 읽기
        source_df = read_source()

        # 2) 전처리
        fact_df = build_fact_environment(source_df)

        # 3) 지역 코드 연결
        fact_df = attach_region_code(engine, fact_df)

        # 4) DB 적재
        load_fact_environment(engine, fact_df)

        # 5) 최종 결과 확인
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {TABLE_NAME}"
                )
            ).scalar_one()

        print(f"[최종 확인] DB 적재 건수: {result:,}행")
        print("환경 데이터 ETL 정상 종료")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
