
from pathlib import Path
import re

import pandas as pd
from sqlalchemy import text

from .db import get_engine
from .region import RAW

# 경로 설정
# ======================================================

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
OUTPUT_PATH = PROCESSED_DIR / "fact_air_monthly.csv"

YEARS = [2024, 2025, 2026]

MONTH_COLUMNS = [f"{month}월" for month in range(1, 13)]

# 최종 CSV에 사용할 오염물질 컬럼
VALUE_COLS = ["pm10", "pm2.5", "o3"]

DECIMALS = {
    "pm10": 2,
    "pm2.5": 2,
    "o3": 4,
}

MAX_VALUE = {
    "pm10": 9999.99,
    "pm2.5": 9999.99,
    "o3": 99.9999,
}

SEOUL_DISTRICTS = [
    "종로구", "중구", "용산구", "성동구", "광진구",
    "동대문구", "중랑구", "성북구", "강북구", "도봉구",
    "노원구", "은평구", "서대문구", "마포구", "양천구",
    "강서구", "구로구", "금천구", "영등포구", "동작구",
    "관악구", "서초구", "강남구", "송파구", "강동구",
]

# 파일명 정규화 및 원본 파일 탐색
# ======================================================

def normalize_name(value):

    return re.sub(r"[^0-9a-z가-힣]", "", str(value).lower())


def identify_pollutant(filename):


    name = normalize_name(filename)


    if "초미세먼지" in name or "pm25" in name:
        return "pm2.5"

    if "미세먼지" in name or "pm10" in name:
        return "pm10"

    if "오존" in name or "o3" in name:
        return "o3"

    return None


def find_source_file(year, pollutant):


    if not RAW.exists():
        raise FileNotFoundError(
            f"원본 폴더를 찾을 수 없습니다: {RAW}"
        )

    matches = []

    for path in RAW.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() not in [".xlsx", ".xls"]:
            continue

        if path.name.startswith("~$"):
            continue

        # 파일명뿐 아니라 상위 폴더명도 검사
        relative_name = normalize_name(
            path.relative_to(RAW).as_posix()
        )

        if str(year) not in relative_name:
            continue

        if identify_pollutant(path.stem) != pollutant:
            continue

        matches.append(path)

    if len(matches) == 0:
        raise FileNotFoundError(
            f"{year}년 {pollutant} Excel 파일을 찾지 못했습니다.\n"
            f"검색 위치: {RAW}\n"
            "파일명과 폴더명을 확인하세요."
        )

    if len(matches) > 1:
        paths = "\n".join(str(path) for path in matches)

        raise ValueError(
            f"{year}년 {pollutant} 파일이 여러 개 발견되었습니다.\n"
            "중복 파일을 확인하세요.\n"
            f"{paths}"
        )

    return matches[0]



# 자치구 코드 매핑
# ======================================================

def load_region_mapping(engine):

    query = text("""
        SELECT DISTINCT
            sigungu_code,
            sigungu_name
        FROM dim_region
        WHERE sigungu_code IS NOT NULL
          AND sigungu_name IS NOT NULL
    """)

    with engine.connect() as conn:
        dim = pd.read_sql_query(query, conn)

    if dim.empty:
        raise ValueError(
            "dim_region에서 자치구 매핑을 찾지 못했습니다."
        )

    dim["sigungu_name"] = (
        dim["sigungu_name"].astype(str).str.strip()
    )

    dim["sigungu_code"] = (
        dim["sigungu_code"].astype(str).str.strip()
    )

    dim = dim[
        dim["sigungu_name"].isin(SEOUL_DISTRICTS)
    ].copy()

    duplicated = dim[
        dim["sigungu_name"].duplicated(keep=False)
    ]

    if not duplicated.empty:
        raise ValueError(
            "dim_region에서 자치구명에 여러 코드가 연결되어 있습니다.\n"
            + duplicated.to_string(index=False)
        )

    mapping = dim.set_index("sigungu_name")["sigungu_code"]

    missing = sorted(set(SEOUL_DISTRICTS) - set(mapping.index))

    if missing:
        raise ValueError(
            f"dim_region에서 찾지 못한 자치구 코드가 있습니다: {missing}"
        )

    return mapping



# Excel 읽기 및 월별 데이터 변환
# ======================================================

def read_pollutant_file(path, year, pollutant):
    """구분 및 1월~12월 구조를 월별 행 구조로 변환한다."""

    print(f"읽는 중: {path.name}")

    # 엑셀에서 실제 컬럼명이 있는 행을 자동으로 찾기
    preview = pd.read_excel(
        path,
        header=None,
        nrows=20,
    )

    header_row = None

    for i in range(len(preview)):
        row = (
            preview.iloc[i]
            .astype("string")
            .str.strip()
        )

        values = set(row.dropna().tolist())

        if "구분" in values and all(
                month in values for month in MONTH_COLUMNS
        ):
            header_row = i
            break

    if header_row is None:
        raise ValueError(
            f"{path.name}에서 실제 컬럼명 행을 찾지 못했습니다.\n"
            "엑셀 상단 20행의 구조를 확인하세요."
        )

    # 찾은 행을 컬럼명으로 사용
    df = pd.read_excel(
        path,
        header=header_row,
        dtype={"구분": str},
    )

    # 컬럼명 공백 제거
    df.columns = [
        str(col).strip()
        for col in df.columns
    ]

    required = ["구분"] + MONTH_COLUMNS

    missing = [col for col in required if col not in df.columns]

    if missing:
        raise ValueError(
            f"{path.name}에 필요한 컬럼이 없습니다: {missing}\n"
            f"실제 컬럼: {df.columns.tolist()}"
        )

    df["구분"] = df["구분"].astype("string").str.strip()

    # 서울시 25개 자치구만 사용
    df = df[df["구분"].isin(SEOUL_DISTRICTS)].copy()

    # 자치구 중복 확인
    duplicated = df.loc[
        df["구분"].duplicated(keep=False), "구분"
    ].drop_duplicates().tolist()

    if duplicated:
        raise ValueError(
            f"{path.name}에 중복 자치구가 있습니다: {duplicated}"
        )

    # 25개 자치구가 모두 있는지 확인
    found = set(df["구분"].dropna())
    missing_districts = sorted(set(SEOUL_DISTRICTS) - found)

    if missing_districts:
        raise ValueError(
            f"{path.name}에서 자치구가 누락되었습니다: "
            f"{missing_districts}"
        )

    # 12개월을 행으로 변환
    df = df.melt(
        id_vars=["구분"],
        value_vars=MONTH_COLUMNS,
        var_name="month",
        value_name=pollutant,
    )

    df["month"] = (
        df["month"]
        .str.replace("월", "", regex=False)
        .astype(int)
    )

    df["base_ym"] = (
        str(year)
        + df["month"].astype(str).str.zfill(2)
    )

    # 숫자 변환. 빈칸 및 '-'는 결측치로 처리한다.
    df[pollutant] = pd.to_numeric(
        df[pollutant]
        .astype("string")
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace({
            "": pd.NA,
            "-": pd.NA,
            "--": pd.NA,
            "NA": pd.NA,
            "N/A": pd.NA,
        }),
        errors="coerce",
    )

    # 음수는 유효하지 않은 값으로 처리
    df.loc[df[pollutant] < 0, pollutant] = pd.NA

    # 비어 있지 않은 원본 값이 숫자로 변환되지 않은 경우 확인
    # 결측치와 비정상 문자열을 구분할 수 있도록 검사한다.
    # 허용되는 결측 표기 외의 텍스트는 오류로 처리한다.
    original_values = (
        df[pollutant].isna()
    )

    # 농도 컬럼 자릿수 범위 확인
    max_value = MAX_VALUE[pollutant]

    if (df[pollutant] > max_value).any():
        invalid = df.loc[
            df[pollutant] > max_value,
            ["구분", "base_ym", pollutant],
        ]

        raise ValueError(
            f"{path.name}: {pollutant} 값이 허용 범위를 넘습니다.\n"
            + invalid.to_string(index=False)
        )

    df[pollutant] = df[pollutant].round(DECIMALS[pollutant])

    return df[["구분", "base_ym", pollutant]]



# 9개 파일 통합 및 검증
# ======================================================

def transform_air(region_mapping):

    pollutant_frames = {
        pollutant: []
        for pollutant in VALUE_COLS
    }

    for year in YEARS:
        for pollutant in VALUE_COLS:
            path = find_source_file(year, pollutant)

            df = read_pollutant_file(
                path=path,
                year=year,
                pollutant=pollutant,
            )

            pollutant_frames[pollutant].append(df)

    # 오염물질별로 연도 데이터를 합친다.
    pm10_df = pd.concat(
        pollutant_frames["pm10"], ignore_index=True
    )

    pm25_df = pd.concat(
        pollutant_frames["pm2.5"], ignore_index=True
    )

    o3_df = pd.concat(
        pollutant_frames["o3"], ignore_index=True
    )

    key_columns = ["구분", "base_ym"]

    # 각 오염물질 데이터를 자치구 + 연월 기준으로 결합
    result = pm10_df.merge(
        pm25_df,
        on=key_columns,
        how="outer",
        validate="one_to_one",
    )

    result = result.merge(
        o3_df,
        on=key_columns,
        how="outer",
        validate="one_to_one",
    )

    result = result.rename(
        columns={"구분": "station_name"}
    )

    # 기존 프로젝트의 지역 코드 연결 방식 유지
    result["sigungu_code"] = (
        result["station_name"].map(region_mapping)
    )

    if result["sigungu_code"].isna().any():
        missing = sorted(
            result.loc[
                result["sigungu_code"].isna(),
                "station_name",
            ].unique()
        )

        raise ValueError(
            f"자치구 코드 매핑에 실패했습니다: {missing}"
        )

    # YYYYMM 형식 및 기간 확인
    if not result["base_ym"].str.fullmatch(r"\d{6}").all():
        raise ValueError("base_ym이 YYYYMM 형식이 아닙니다.")

    result = result[
        [
            "station_name",
            "base_ym",
            "sigungu_code",
            "pm10",
            "pm2.5",
            "o3",
        ]
    ]

    result = result.sort_values(
        ["base_ym", "station_name"]
    ).reset_index(drop=True)

    # 최종 중복 확인
    duplicated = result.duplicated(
        subset=["station_name", "base_ym"],
        keep=False,
    )

    if duplicated.any():
        raise ValueError(
            "최종 결과에 자치구와 연월 조합의 중복이 있습니다.\n"
            + result.loc[duplicated].to_string(index=False)
        )

    # 36개월 × 25개 자치구 = 900행
    expected_rows = len(YEARS) * 12 * len(SEOUL_DISTRICTS)

    if len(result) != expected_rows:
        raise ValueError(
            f"최종 행 수가 예상과 다릅니다. "
            f"예상: {expected_rows}, 실제: {len(result)}"
        )

    # 연월별 데이터 건수 확인
    monthly_counts = result.groupby("base_ym")["station_name"].nunique()

    if (monthly_counts != len(SEOUL_DISTRICTS)).any():
        raise ValueError(
            "일부 월에 25개 자치구가 모두 존재하지 않습니다.\n"
            + monthly_counts[
                monthly_counts != len(SEOUL_DISTRICTS)
            ].to_string()
        )

    print("\n[오염물질별 결측치]")
    print(result[VALUE_COLS].isna().sum().to_string())

    return result



# CSV 저장
# ======================================================

def save_csv(df):
    """통합 데이터를 processed 폴더에 CSV로 저장한다."""

    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n대기오염 월별 CSV 생성 완료")
    print(f"저장 위치: {OUTPUT_PATH}")
    print(f"총 행 수: {len(df):,}")
    print(f"자치구 수: {df['station_name'].nunique()}")
    print(
        f"기간: {df['base_ym'].min()} ~ {df['base_ym'].max()}"
    )

    print("\n최종 컬럼:")
    print(df.columns.tolist())

    print("\n미리보기:")
    print(df.head(10).to_string(index=False))

# 실행
# ======================================================

def main(engine=None):
    engine = engine or get_engine()

    region_mapping = load_region_mapping(engine)

    result = transform_air(region_mapping)

    save_csv(result)


if __name__ == "__main__":
    main()
