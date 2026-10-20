import pandas as pd
from sqlalchemy import text

from .db import get_engine
from .region import RAW


# S-DoT 영문 자치구 이름 → 자치구 코드
district_mapping = {
    "Gangnam-gu": "gnm",
    "Gangdong-gu": "gnd",
    "Gangbuk-gu": "gnb",
    "Gangseo-gu": "gns",
    "Gwanak-gu": "gwk",
    "Gwangjin-gu": "gwj",
    "Guro-gu": "gro",
    "Geumcheon-gu": "gch",
    "Nowon-gu": "nwn",
    "Dobong-gu": "dbg",
    "Dongdaemun-gu": "ddm",
    "Dongjak-gu": "djk",
    "Mapo-gu": "map",
    "Seodaemun-gu": "sdm",
    "Seocho-gu": "sch",
    "Seongdong-gu": "sdg",
    "Seongbuk-gu": "sbk",
    "Songpa-gu": "spg",
    "Yangcheon-gu": "ycn",
    "Yeongdeungpo-gu": "ydp",
    "Yongsan-gu": "ysn",
    "Eunpyeong-gu": "eyp",
    "Jongno-gu": "jno",
    "Jung-gu": "jng",
    "Jungnang-gu": "jnn",
    "Seoul_Grand_Park": "sgp",
}

# 영문 자치구 이름 → 한글 자치구 이름
district_name_mapping = {
    "Gangnam-gu": "강남구",
    "Gangdong-gu": "강동구",
    "Gangbuk-gu": "강북구",
    "Gangseo-gu": "강서구",
    "Gwanak-gu": "관악구",
    "Gwangjin-gu": "광진구",
    "Guro-gu": "구로구",
    "Geumcheon-gu": "금천구",
    "Nowon-gu": "노원구",
    "Dobong-gu": "도봉구",
    "Dongdaemun-gu": "동대문구",
    "Dongjak-gu": "동작구",
    "Mapo-gu": "마포구",
    "Seodaemun-gu": "서대문구",
    "Seocho-gu": "서초구",
    "Seongdong-gu": "성동구",
    "Seongbuk-gu": "성북구",
    "Songpa-gu": "송파구",
    "Yangcheon-gu": "양천구",
    "Yeongdeungpo-gu": "영등포구",
    "Yongsan-gu": "용산구",
    "Eunpyeong-gu": "은평구",
    "Jongno-gu": "종로구",
    "Jung-gu": "중구",
    "Jungnang-gu": "중랑구",
}

EXCLUDE_GU = {"Seoul_Grand_Park"}

COLS = {
    "시리얼": "serial",
    "측정시간": "ts",
    "자치구": "gu_en",
    "온도 최대(℃)": "temp_max",
    "온도 평균(℃)": "temp_avg",
    "온도 최소(℃)": "temp_min",
    "습도 평균(%)": "humidity",
    "자외선 최대(UV)": "uv_max",
    "소음 평균(dB)": "noise",
}

TEMP_ERROR = -40
DAY_HOURS = range(6, 22)


def find_file():
    files = sorted(RAW.glob("*S-DoT*.csv"))

    if not files:
        raise FileNotFoundError(
            f"{RAW} 안에서 S-DoT CSV를 찾을 수 없음"
        )

    return files[-1]


def transform_sdot(raw, dim):
    # 컬럼명 변경
    df = raw.rename(columns=COLS)

    # 자치구 누락 및 서울대공원 제외
    df = df[
        df["gu_en"].notna()
        & ~df["gu_en"].isin(EXCLUDE_GU)
    ].copy()

    # 대응표에 없는 자치구 확인
    unknown = (
        set(df["gu_en"].unique())
        - set(district_name_mapping.keys())
    )

    if unknown:
        raise ValueError(
            f"대응표에 없는 자치구 이름: {sorted(unknown)}"
        )

    # 영문 자치구를 한글 자치구 이름으로 변환
    df["sigungu_name"] = df["gu_en"].map(
        district_name_mapping
    )

    # 측정시간 처리
    ts = pd.to_datetime(
        df["ts"].astype(str).str.replace(
            "_", " ", regex=False
        ),
        errors="coerce",
    )

    if ts.isna().any():
        raise ValueError("측정시간을 읽지 못한 행이 있음")

    df["base_date"] = ts.dt.date
    df["hour"] = ts.dt.hour

    # 센서 오류값 처리 및 숫자형 변환
    for c in ("temp_max", "temp_avg", "temp_min"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
        df.loc[df[c] == TEMP_ERROR, c] = pd.NA

    for c in ("humidity", "uv_max", "noise"):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 주간 및 야간 소음 분리
    df["is_day"] = df["hour"].isin(DAY_HOURS)
    df["noise_day"] = df["noise"].where(df["is_day"])
    df["noise_night"] = df["noise"].where(~df["is_day"])

    # 센서별 일 최고·최저기온 및 UV 집계
    per_sensor = (
        df.groupby(
            ["sigungu_name", "base_date", "serial"],
            dropna=False,
        )
        .agg(
            max_temp=("temp_max", "max"),
            min_temp=("temp_min", "min"),
            uv_index=("uv_max", "max"),
        )
        .reset_index()
    )

    # 자치구별 일평균
    extreme = (
        per_sensor.groupby(["sigungu_name", "base_date"])[
            ["max_temp", "min_temp", "uv_index"]
        ]
        .mean()
    )

    mean_part = df.groupby(
        ["sigungu_name", "base_date"]
    ).agg(
        avg_temp=("temp_avg", "mean"),
        humidity=("humidity", "mean"),
        noise_day_db=("noise_day", "mean"),
        noise_night_db=("noise_night", "mean"),
    )

    daily = mean_part.join(extreme).reset_index()

    # 소수점 정리
    daily = daily.round({
        "avg_temp": 2,
        "max_temp": 2,
        "min_temp": 2,
        "humidity": 2,
        "uv_index": 1,
        "noise_day_db": 2,
        "noise_night_db": 2,
    })

    # 검증: 25개 자치구
    n_gu = daily["sigungu_name"].nunique()

    if n_gu != 25:
        raise ValueError(
            f"구 개수가 25개가 아님: {n_gu}"
        )

    # 자치구·날짜 중복 검증
    if daily.duplicated(
        ["sigungu_name", "base_date"]
    ).any():
        raise ValueError("구·날짜 중복")

    # dim_region의 자치구 이름과 일치하는지 확인
    dim = dim.copy()
    dim["sigungu_name"] = (
        dim["sigungu_name"].astype(str).str.strip()
    )
    daily["sigungu_name"] = (
        daily["sigungu_name"].astype(str).str.strip()
    )

    dim_names = set(dim["sigungu_name"].unique())
    daily_names = set(daily["sigungu_name"].unique())

    missing_gu = daily_names - dim_names

    if missing_gu:
        raise ValueError(
            "dim_region에서 찾을 수 없는 자치구: "
            f"{sorted(missing_gu)}"
        )

    # 자치구의 일별 값을 해당 자치구의 모든 행정동에 연결
    out = daily.merge(
        dim[["region_code", "sigungu_name"]].drop_duplicates(),
        on="sigungu_name",
        how="left",
        validate="many_to_many",
    )

    if out["region_code"].isna().any():
        raise ValueError("행정동 매칭 실패")

    out["source_level"] = "SGG"

    return out


def _upsert(engine, table, df, cols):
    all_cols = (
        ["region_code", "base_date"]
        + cols
        + ["source_level"]
    )

    updates = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in cols
    )

    sql = text(f"""
        INSERT INTO {table} ({", ".join(all_cols)})
        VALUES ({", ".join(":" + c for c in all_cols)})
        ON CONFLICT (region_code, base_date)
        DO UPDATE SET {updates}
        WHERE {table}.source_level = 'SGG'
    """)

    records = (
        df[all_cols]
        .astype(object)
        .where(df[all_cols].notna(), None)
        .to_dict("records")
    )

    with engine.begin() as conn:
        conn.execute(sql, records)


def main(engine=None):
    engine = engine or get_engine()

    # S-DoT CSV 읽기
    raw = pd.read_csv(
        find_file(),
        encoding="cp949",
        usecols=list(COLS),
    )

    # 행정구역 차원 테이블 읽기
    dim = pd.read_sql(
        text("""
            SELECT region_code, sigungu_name
            FROM dim_region
        """),
        engine,
    )

    if dim.empty:
        raise RuntimeError(
            "dim_region이 비어 있음. "
            "먼저 python -m etl.region 을 실행하세요"
        )

    # 변환
    out = transform_sdot(raw, dim)

    # 기상 데이터 적재
    _upsert(
        engine,
        "fact_weather",
        out,
        [
            "avg_temp",
            "max_temp",
            "min_temp",
            "humidity",
            "uv_index",
        ],
    )

    # 소음 데이터 적재
    _upsert(
        engine,
        "fact_noise",
        out,
        [
            "noise_day_db",
            "noise_night_db",
        ],
    )

    n_days = out["base_date"].nunique()
    n_regions = out["region_code"].nunique()

    print(
        "fact_weather / fact_noise 적재 완료: "
        f"각 {len(out)}행 "
        f"(행정동 {n_regions}개 × {n_days}일)"
    )


if __name__ == "__main__":
    main()
