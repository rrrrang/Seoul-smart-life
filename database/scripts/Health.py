from pathlib import Path

import pandas as pd
from sqlalchemy import inspect, text

from etl.db import get_engine


# =========================================================
# 경로 설정
# =========================================================

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"

# True: 적재 전에 테이블을 비우고 다시 넣는다. (여러 번 실행해도 행이 늘지 않는다)
# False: 기존 행 뒤에 추가한다. (실행할 때마다 같은 행이 중복된다)
REPLACE_EXISTING = True

engine = get_engine()


# =========================================================
# 공통 전처리 함수
# =========================================================

def normalize_code(series):

    return (
        series.astype("string")
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace("", pd.NA)
    )


def clean_text(series):

    return series.astype("string").str.strip().replace("", pd.NA)


def to_number(series):

    return pd.to_numeric(
        clean_text(series).str.replace(",", "", regex=False),
        errors="coerce",
    )


def to_integer(series, name=""):

    values = to_number(series)

    fractional = values.notna() & (values % 1 != 0)
    if fractional.any():
        print(f"  [주의] {name}: 소수점이 있는 값 {int(fractional.sum())}개를 반올림합니다")

    return values.round().astype("Int64")


def to_boolean(series, name=""):

    values = clean_text(series).str.lower()

    result = values.map({
        "true": True,
        "false": False,
        "1": True,
        "0": False,
        "y": True,
        "n": False,
    })

    # 변환표에 없는 값은 조용히 결측이 되므로 알려준다.
    unmapped = values.notna() & result.isna()
    if unmapped.any():
        counts = values[unmapped].value_counts().head(5).to_dict()
        print(f"  [주의] {name}: 변환하지 못한 값 {int(unmapped.sum())}개: {counts}")

    return result.astype(object).where(result.notna(), None)


def to_date(series, name=""):

    values = clean_text(series)
    numbers = pd.to_numeric(values, errors="coerce")

    # 숫자가 아닌 값은 비교 결과가 <NA>가 되므로 False로 바꿔서 마스크로 쓴다.
    excel_mask = numbers.between(1000, 100000).fillna(False).astype(bool)
    text_mask = (values.notna() & ~excel_mask).fillna(False).astype(bool)

    result = pd.Series(
        pd.NaT, index=series.index, dtype="datetime64[ns]"
    )

    # Excel 날짜 일련번호
    result.loc[excel_mask] = pd.to_datetime(
        numbers.loc[excel_mask],
        unit="D",
        origin="1899-12-30",
        errors="coerce",
    )

    # 일반 날짜 문자열 (형식이 섞여 있어도 값마다 따로 변환한다)
    result.loc[text_mask] = values.loc[text_mask].map(
        lambda x: pd.to_datetime(x, errors="coerce")
    )

    failed = values.notna() & result.isna()
    if failed.any():
        samples = values[failed].head(5).tolist()
        print(f"  [주의] {name}: 날짜로 변환하지 못한 값 {int(failed.sum())}개: {samples}")

    dates = result.dt.date
    return dates.astype(object).where(result.notna(), None)


def convert_columns(df, dates=(), integers=(), numbers=(), booleans=()):
    """DB 컬럼 타입에 맞게 값을 변환한다. (원본은 모두 문자열이다)"""
    df = df.copy()

    for column in dates:
        if column in df.columns:
            df[column] = to_date(df[column], column)

    for column in integers:
        if column in df.columns:
            df[column] = to_integer(df[column], column)

    for column in numbers:
        if column in df.columns:
            df[column] = to_number(df[column])

    for column in booleans:
        if column in df.columns:
            df[column] = to_boolean(df[column], column)

    return df


def read_csv_file(filename):

    file_path = RAW_DIR / filename

    if not file_path.exists():
        raise FileNotFoundError(
            f"원본 파일을 찾을 수 없습니다: {file_path}"
        )

    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            df = pd.read_csv(
                file_path,
                encoding=encoding,
                dtype="string",
                low_memory=False,
            )
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"CSV 인코딩 확인 필요: {filename}")

    df.columns = df.columns.astype(str).str.strip()

    print(f"[읽기 완료] {filename}: {len(df):,}행")
    print(f"[컬럼 확인] {df.columns.tolist()}")

    return df


def rename_columns(df, column_mapping):

    applicable = {
        old: new
        for old, new in column_mapping.items()
        if old in df.columns
    }

    return df.rename(columns=applicable)


# =========================================================
# 행정동 코드 매핑
# =========================================================

def load_region_mapping():

    query = text("""
        SELECT
            admin_code,
            region_code
        FROM dim_region
        WHERE admin_code IS NOT NULL
    """)

    with engine.connect() as conn:
        mapping = pd.read_sql_query(query, conn)

    # 반드시 normalize_code 함수 정의 후 호출
    mapping["admin_code"] = normalize_code(
        mapping["admin_code"]
    )

    mapping["region_code"] = (
        mapping["region_code"]
        .astype("string")
        .str.strip()
    )

    mapping = mapping.dropna(
        subset=["admin_code", "region_code"]
    )

    # 중복 행정동 코드 확인
    duplicated = mapping[
        mapping.duplicated("admin_code", keep=False)
    ]

    if not duplicated.empty:
        raise ValueError(
            "dim_region에 중복된 admin_code가 있습니다.\n"
            "행정동 코드 매핑을 확인하세요.\n"
            + duplicated.to_string(index=False)
        )

    mapping = mapping.set_index("admin_code")

    print(f"[매핑 완료] 행정동 코드 {len(mapping):,}개")

    return mapping


def apply_region_mapping(df, mapping):

    df = df.copy()

    code_candidates = [
        "행정동코드",
        "행정동 코드",
        "행정동코드10자리",
        "admin_code",
        "admin_dong_code",
    ]

    code_column = next(
        (
            column
            for column in code_candidates
            if column in df.columns
        ),
        None,
    )

    if code_column is None:
        print(
            "[매핑 생략] 행정동 코드 컬럼을 찾을 수 없습니다."
        )
        return df

    df["admin_dong_code"] = normalize_code(
        df[code_column]
    )

    # region_code(6자리)를 붙인다.
    # region_name은 원본의 자치구 이름을 그대로 둔다. (dim_region의 region_name은 행정동명이다)
    code_map = mapping["region_code"].to_dict()
    df["region_code"] = df["admin_dong_code"].map(code_map)

    unmatched = df.loc[
        df["admin_dong_code"].notna()
        & df["region_code"].isna(),
        "admin_dong_code",
    ].drop_duplicates()

    if not unmatched.empty:
        print(
            f"[매핑 확인 필요] 미매핑 코드 {len(unmatched)}개: "
            f"{unmatched.head(20).tolist()}"
        )

    print(
        f"[매핑 결과] 성공 행: "
        f"{df['region_code'].notna().sum():,} / {len(df):,}"
    )

    return df


# =========================================================
# 기존 PostgreSQL 테이블에 적재
# =========================================================

def get_table_columns(table_name):

    inspector = inspect(engine)

    if not inspector.has_table(
        table_name,
        schema="public",
    ):
        raise ValueError(
            f"public.{table_name} 테이블이 존재하지 않습니다."
        )

    columns = inspector.get_columns(
        table_name,
        schema="public",
    )

    return {column["name"] for column in columns}


def load_to_existing_table(df, table_name):

    if df.empty:
        print(f"[적재 생략] {table_name}: 데이터가 없습니다.")
        return

    df = df.copy()

    # 문자열 컬럼의 앞뒤 공백을 지우고 빈 문자열을 NULL로 변환
    for column in df.columns:
        if isinstance(df[column].dtype, pd.StringDtype):
            df[column] = df[column].str.strip()
            df[column] = df[column].replace("", pd.NA)

    target_columns = get_table_columns(table_name)

    selected_columns = [
        column
        for column in df.columns
        if column in target_columns
    ]

    if not selected_columns:
        raise ValueError(
            f"{table_name}과 일치하는 컬럼이 없습니다.\n"
            f"전처리 컬럼: {df.columns.tolist()}\n"
            f"DB 컬럼: {sorted(target_columns)}"
        )

    # 우리가 영문으로 바꾼 컬럼인데 DB에 없으면 적재되지 않으므로 알려준다.
    # (한글 원본 컬럼은 원래 적재 대상이 아니라서 알리지 않는다)
    dropped = [
        column
        for column in df.columns
        if column not in target_columns and column.isascii()
    ]

    if dropped:
        print(f"[DB에 없어서 적재하지 않는 컬럼] {dropped}")

    df = df[selected_columns]

    print(f"[적재 대상] {table_name}")
    print(f"[적재 컬럼] {df.columns.tolist()}")

    # 비우기와 적재를 한 트랜잭션으로 처리한다. (적재가 실패하면 비우기도 취소된다)
    with engine.begin() as conn:
        if REPLACE_EXISTING:
            conn.execute(text(f'TRUNCATE TABLE public."{table_name}"'))

        df.to_sql(
            name=table_name,
            con=conn,
            schema="public",
            if_exists="append",
            index=False,
            chunksize=1000,
            method="multi",
        )

    with engine.connect() as conn:
        total = conn.execute(
            text(f'SELECT COUNT(*) FROM public."{table_name}"')
        ).scalar_one()

    print(
        f"[적재 완료] {table_name}: {len(df):,}행 (테이블 전체 {total:,}행)"
    )


# =========================================================
# 의료기관 데이터
# =========================================================

def process_healthcare(mapping):
    df = read_csv_file(
        "서울_의료기관_202606_행정동연결.csv"
    )

    df = rename_columns(df, {
        "암호화요양기호": "institution_id",
        "요양기관명": "institution_name",
        "종별코드명": "institution_type",
        "자치구": "region_name",
        "행정동명": "admin_dong_name",
        "주소": "address",
        "전화번호": "phone",
        "개설일자": "opened_date",
        "총의사수": "doctor_count",
        "의과의사수": "medical_doctor_count",
        "일반입원병상수": "general_bed_count",
        "응급실병상수": "emergency_bed_count",
        "좌표(X)": "longitude",
        "좌표(Y)": "latitude",
        "의료자료기준": "source_period",
    })

    df = convert_columns(
        df,
        dates=["opened_date"],
        integers=[
            "doctor_count",
            "medical_doctor_count",
            "general_bed_count",
            "emergency_bed_count",
        ],
        numbers=["longitude", "latitude"],
    )

    df = apply_region_mapping(df, mapping)

    load_to_existing_table(
        df,
        "fact_healthcare_institution",
    )


# =========================================================
# 약국 데이터
# =========================================================

def process_pharmacy(mapping):
    df = read_csv_file(
        "서울_약국_202606_행정동연결.csv"
    )

    df = rename_columns(df, {
        "암호화요양기호": "pharmacy_id",
        "요양기관명": "pharmacy_name",
        "자치구": "region_name",
        "행정동명": "admin_dong_name",
        "주소": "address",
        "전화번호": "phone",
        "개설일자": "opened_date",
        "좌표(X)": "longitude",
        "좌표(Y)": "latitude",
        "의료자료기준": "source_period",
    })

    df = convert_columns(
        df,
        dates=["opened_date"],
        numbers=["longitude", "latitude"],
    )

    df = apply_region_mapping(df, mapping)

    load_to_existing_table(
        df,
        "fact_pharmacy",
    )


# =========================================================
# 응급기관 데이터
# =========================================================

def process_emergency_institution(mapping):
    df = read_csv_file(
        "서울_응급기관_명단연결_20260910.csv"
    )

    # 기관명은 HIRA 기관명을 쓰고, 연결에 실패한 행은 공식 명단의 이름을 쓴다.
    if "요양기관명" in df.columns and "공식명단기관명" in df.columns:
        df["요양기관명"] = df["요양기관명"].fillna(df["공식명단기관명"])

    df = rename_columns(df, {
        "암호화요양기호": "institution_id",
        "요양기관명": "institution_name",
        "응급기관분류": "emergency_type",
        "소아전문표기": "pediatric_specialized",
        "권역외상표기": "trauma_center",
        "자치구": "region_name",
        "행정동명": "admin_dong_name",
        "원본주소": "address",
        "경도": "longitude",
        "위도": "latitude",
        "응급운영시간": "emergency_hours",
        "명단기준일": "source_date",
    })

    df = convert_columns(
        df,
        dates=["source_date"],
        numbers=["longitude", "latitude"],
        booleans=["pediatric_specialized", "trauma_center"],
    )

    df = apply_region_mapping(df, mapping)

    load_to_existing_table(
        df,
        "fact_emergency_institution",
    )


# =========================================================
# 응급기관 운영 안내 데이터
# =========================================================

def process_emergency_operation_guide():
    df = read_csv_file(
        "서울_응급기관_명시적운영안내.csv"
    )

    df = rename_columns(df, {
        "암호화요양기호": "institution_id",
        "공식명단기관명": "institution_name",
        "자치구": "region_name",
        "원문운영표기": "operation_text",
        "운영안내대상": "operation_target",
        "적용맥락": "context_note",
        "출처": "source_url",
    })

    load_to_existing_table(
        df,
        "fact_emergency_operation_guide",
    )


# =========================================================
# 행정동 인구 데이터
# =========================================================

def process_population(mapping):
    df = read_csv_file(
        "서울_행정동_인구_2026Q2.csv"
    )

    df = rename_columns(df, {
        "자치구": "region_name",
        "동별": "admin_dong_name",
        "분기": "base_period",
        "총인구": "total_population",
        "고령인구_65세이상": "elderly_population",
        "아동인구_15세미만": "child_population",
        "고령인구비율_pct": "elderly_population_ratio",
        "아동인구비율_pct": "child_population_ratio",
    })

    df = convert_columns(
        df,
        integers=[
            "total_population",
            "elderly_population",
            "child_population",
        ],
        numbers=[
            "elderly_population_ratio",
            "child_population_ratio",
        ],
    )

    df = apply_region_mapping(df, mapping)

    load_to_existing_table(
        df,
        "fact_population_dong",
    )


# =========================================================
# 전체 실행
# =========================================================

def main():
    print("=" * 60)
    print("Health ETL 시작")
    print("=" * 60)

    mapping = load_region_mapping()

    process_healthcare(mapping)
    process_pharmacy(mapping)
    process_emergency_institution(mapping)
    process_emergency_operation_guide()
    process_population(mapping)

    print("=" * 60)
    print("Health ETL 완료")
    print("=" * 60)


if __name__ == "__main__":
    main()