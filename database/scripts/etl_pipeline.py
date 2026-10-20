import pandas as pd
from sqlalchemy import text

from .db import get_engine
from .region import RAW, build_dim_region, load_dim_region, read_household_raw, to_short_code


def latest(pattern):
    files = sorted(RAW.glob(pattern))
    if not files:
        raise FileNotFoundError(f"{RAW} 안에서 '{pattern}' 파일을 찾을 수 없음")
    return files[-1]


# ---------- 세대수 ----------
def transform_households(raw):
    size_cols = ["1인세대", "2인세대", "3인세대", "4인세대", "5인세대",
                 "6인세대", "7인세대", "8인세대", "9인세대", "10인이상세대"]
    if (raw[size_cols].sum(axis=1) != raw["전체세대수"]).any():
        raise ValueError("세대원수별 합계와 전체세대수가 다른 행이 있음")

    df = raw.rename(columns={"행정기관코드": "region_code",
                             "전체세대수": "households",
                             "1인세대": "hh_1person"}).copy()
    df["region_code"] = to_short_code(raw["행정기관코드"])       # 10자리 → 6자리
    df["base_ym"] = pd.to_datetime(raw["기준연월"]).dt.strftime("%Y%m")
    df = df[["region_code", "base_ym", "households", "hh_1person"]]
    if df.duplicated(["region_code", "base_ym"]).any():
        raise ValueError("fact_households 키 중복")
    return df


def load_households(engine, df):
    sql = text("""
        INSERT INTO fact_households (region_code, base_ym, households, hh_1person)
        VALUES (:region_code, :base_ym, :households, :hh_1person)
        ON CONFLICT (region_code, base_ym) DO UPDATE SET
            households = EXCLUDED.households,
            hh_1person = EXCLUDED.hh_1person
    """)
    with engine.begin() as conn:
        conn.execute(sql, df.to_dict("records"))


# ---------- 주택수 ----------
def transform_housing_stock(dim):
    path = latest("연면적별+주택현황*.csv")
    df = pd.read_csv(path, encoding="utf-8-sig", skiprows=[1, 2])
    year_col = df.columns[3]                     # '2025' (소계 열)
    base_year = int(str(year_col).split(".")[0])

    df = df[(df["연면적별(1)"] == "계") & (df["자치구별(2)"] != "소계")].copy()
    df["housing_units"] = pd.to_numeric(df[year_col], errors="coerce")

    gu = dim[["sigungu_code", "sigungu_name"]].drop_duplicates()
    df = df.merge(gu, left_on="자치구별(2)", right_on="sigungu_name", how="left")
    if df["sigungu_code"].isna().any():
        raise ValueError("구 코드 매칭 실패: " + str(df[df["sigungu_code"].isna()]["자치구별(2)"].tolist()))
    if df["housing_units"].isna().any():
        raise ValueError("주택수 결측 있음")

    df["base_year"] = base_year
    return df[["sigungu_code", "base_year", "housing_units"]]


def load_housing_stock(engine, df):
    sql = text("""
        INSERT INTO fact_housing_stock (sigungu_code, base_year, housing_units)
        VALUES (:sigungu_code, :base_year, :housing_units)
        ON CONFLICT (sigungu_code, base_year) DO UPDATE SET
            housing_units = EXCLUDED.housing_units
    """)
    with engine.begin() as conn:
        conn.execute(sql, df.to_dict("records"))


# ---------- 실행 ----------
def main(engine=None):
    engine = engine or get_engine()
    raw = read_household_raw()
    dim = build_dim_region(raw)

    load_dim_region(engine, dim)                 # 지역 기준표 (먼저!)
    print("dim_region", len(dim), "행")

    hh = transform_households(raw)
    load_households(engine, hh)
    print("fact_households", len(hh), "행, 합계", f"{hh['households'].sum():,}")

    stock = transform_housing_stock(dim)
    load_housing_stock(engine, stock)
    print("fact_housing_stock", len(stock), "행, 합계", f"{stock['housing_units'].sum():,}")


if __name__ == "__main__":
    main()