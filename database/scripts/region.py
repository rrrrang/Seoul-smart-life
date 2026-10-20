from pathlib import Path

import pandas as pd
from sqlalchemy import text

from .db import get_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / "data" / "raw"


def read_household_raw():
    files = sorted(RAW.glob("행정안전부_지역별*세대수*.csv"))
    if not files:
        raise FileNotFoundError(f"{RAW} 안에서 세대수 CSV를 찾을 수 없음")
    df = pd.read_csv(files[-1], encoding="cp949", dtype={"행정기관코드": str})
    return df[df["시도명"] == "서울특별시"].copy()


def to_short_code(admin_code):
    """10자리 행정기관코드 → 6자리 (시도 2자리와 끝 2자리를 뺀 값)"""
    return admin_code.str[2:8]


def build_dim_region(raw):
    df = raw.rename(columns={"행정기관코드": "admin_code",
                             "읍면동명": "region_name",
                             "시군구명": "sigungu_name"})
    if not df["admin_code"].astype(str).str.fullmatch(r"\d{10}").all():
        raise ValueError("행정기관코드가 10자리 숫자가 아닌 행이 있음. 원본 파일을 쓰고 있는지 확인하세요")
    if df["admin_code"].duplicated().any():
        raise ValueError("행정기관코드 중복")

    df["region_code"] = to_short_code(df["admin_code"])
    if df["region_code"].duplicated().any():
        raise ValueError("6자리 코드 중복")
    df["sigungu_code"] = df["admin_code"].str[:5]
    return df[["region_code", "admin_code", "region_name", "sigungu_code", "sigungu_name"]]


def load_dim_region(engine, df):
    sql = text("""
        INSERT INTO dim_region (region_code, admin_code, region_name, sigungu_code, sigungu_name)
        VALUES (:region_code, :admin_code, :region_name, :sigungu_code, :sigungu_name)
        ON CONFLICT (region_code) DO UPDATE SET
            admin_code   = EXCLUDED.admin_code,
            region_name  = EXCLUDED.region_name,
            sigungu_code = EXCLUDED.sigungu_code,
            sigungu_name = EXCLUDED.sigungu_name
    """)
    with engine.begin() as conn:
        conn.execute(sql, df.to_dict("records"))


def main():
    dim = build_dim_region(read_household_raw())
    load_dim_region(get_engine(), dim)
    print(len(dim), "행 적재 완료")


if __name__ == "__main__":
    main()