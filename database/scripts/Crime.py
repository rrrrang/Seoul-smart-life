import re

import pandas as pd
from sqlalchemy import text

from .db import get_engine
from .region import RAW

# 경찰서 → 자치구 대응 (지구대·파출소·치안센터 주소의 구 기준으로 만든 추정표)
STATION_TO_GU = {
    "중부": "중구", "남대문": "중구",
    "종로": "종로구", "혜화": "종로구",
    "용산": "용산구", "성동": "성동구", "광진": "광진구",
    "동대문": "동대문구", "중랑": "중랑구",
    "성북": "성북구", "종암": "성북구",
    "강북": "강북구", "도봉": "도봉구", "노원": "노원구",
    "은평": "은평구", "서부": "은평구",
    "서대문": "서대문구", "마포": "마포구",
    "양천": "양천구", "강서": "강서구", "구로": "구로구", "금천": "금천구",
    "영등포": "영등포구", "동작": "동작구", "관악": "관악구",
    "서초": "서초구", "방배": "서초구",
    "강남": "강남구", "수서": "강남구",
    "송파": "송파구", "강동": "강동구",
}

# 죄종 → DB 컬럼 ('강간'과 '강간,추행'은 같은 항목의 다른 표기)
CRIME_COL = {"살인": "murder", "강도": "robbery", "강간,추행": "sexual_assault",
             "강간": "sexual_assault", "절도": "theft", "폭력": "violence"}
OCCUR = ["murder", "robbery", "sexual_assault", "theft", "violence"]
CLEAR = [c + "_cleared" for c in OCCUR]
NUM_COLS = OCCUR + ["crime_total"] + CLEAR + ["cleared_total"]


def find_files():
    files = sorted(RAW.glob("*경찰서별*5대범죄*.csv"))
    if not files:
        raise FileNotFoundError(f"{RAW} 안에서 경찰서별 5대범죄 CSV를 찾을 수 없음")
    return files


def read_year(path):
    m = re.search(r"_(\d{4})_", path.name)
    if not m:
        raise ValueError(f"파일명에서 연도를 찾을 수 없음: {path.name}")
    df = pd.read_csv(path, encoding="cp949")
    df["base_year"] = int(m.group(1))
    return df


def transform_crime(raw, dim):
    raw = raw.copy()
    raw["crime"] = raw["죄종"].map(CRIME_COL)
    raw["kind"] = raw["발생검거"].map({"발생": "", "검거": "_cleared"})
    if raw["crime"].isna().any() or raw["kind"].isna().any():
        raise ValueError("알 수 없는 죄종 또는 발생/검거 값이 있음")
    raw["col"] = raw["crime"] + raw["kind"]
    if raw.duplicated(["base_year", "구분", "col"]).any():
        raise ValueError("표기를 통일한 뒤 같은 항목이 중복됨")

    unknown = set(raw["구분"]) - set(STATION_TO_GU)
    if unknown:
        raise ValueError(f"자치구 대응표에 없는 경찰서: {sorted(unknown)}")
    raw["sigungu_name"] = raw["구분"].map(STATION_TO_GU)

    wide = raw.pivot_table(index=["sigungu_name", "base_year"], columns="col",
                           values="건수", aggfunc="sum").reindex(columns=OCCUR + CLEAR)
    if wide.isna().any().any():
        raise ValueError("구·연도별로 빠진 항목이 있음")
    wide = wide.astype(int)
    wide["crime_total"] = wide[OCCUR].sum(axis=1)
    wide["cleared_total"] = wide[CLEAR].sum(axis=1)
    out = wide.reset_index()

    # ---- 검증 ----
    if out["sigungu_name"].nunique() != 25:
        raise ValueError(f"구 개수가 25개가 아님: {out['sigungu_name'].nunique()}")
    for year, g in out.groupby("base_year"):
        src = raw[(raw["base_year"] == year) & (raw["발생검거"] == "발생")]["건수"].sum()
        if g["crime_total"].sum() != src:
            raise ValueError(f"{year}년: 구별 합계가 원본 경찰서 합계와 다름")

    out = out.merge(dim, on="sigungu_name", how="left")
    if out["sigungu_code"].isna().any():
        raise ValueError("구 코드 매칭 실패")
    return out[["sigungu_code", "base_year"] + NUM_COLS]


def load_crime(engine, df):
    cols = list(df.columns)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in NUM_COLS)
    sql = text(f"""
        INSERT INTO fact_crime ({", ".join(cols)})
        VALUES ({", ".join(":" + c for c in cols)})
        ON CONFLICT (sigungu_code, base_year) DO UPDATE SET {updates}
    """)
    with engine.begin() as conn:
        conn.execute(sql, df.to_dict("records"))


def main(engine=None):
    engine = engine or get_engine()
    raw = pd.concat([read_year(p) for p in find_files()], ignore_index=True)
    dim = pd.read_sql(text("SELECT DISTINCT sigungu_code, sigungu_name FROM dim_region"), engine)
    if dim.empty:
        raise RuntimeError("dim_region이 비어 있음. 먼저 python -m etl.region 을 실행하세요")

    df = transform_crime(raw, dim)
    load_crime(engine, df)
    for year, g in df.groupby("base_year"):
        print(f"fact_crime {year}년 {len(g)}행 | 발생 {g['crime_total'].sum():,} 검거 {g['cleared_total'].sum():,}")


if __name__ == "__main__":
    main()