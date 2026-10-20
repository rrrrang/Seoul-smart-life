import re
from datetime import date

import pandas as pd
from sqlalchemy import text

from .db import get_engine
from .region import RAW

# 원본 엑셀의 열 위치 → DB 컬럼명
COLS = {
    2: "cctv_total",            # CCTV 총계
    3: "crime_prev_subtotal",   # 범죄예방 및 수사 소계
    4: "cctv_security",         # 방범
    5: "cctv_school_zone",      # 어린이보호구역
    6: "cctv_park_playground",  # 공원·놀이터
    7: "cctv_illegal_dumping",  # 쓰레기 무단투기
    8: "cctv_facility_safety",  # 시설안전·화재예방
    9: "cctv_traffic_enforce",  # 교통단속
    10: "cctv_traffic_info",    # 교통정보수집·분석
    11: "cctv_other",           # 기타 다른법령
}
NUM_COLS = list(COLS.values())


def find_file():
    files = sorted(RAW.glob("*CCTV*.xlsx"))
    if not files:
        raise FileNotFoundError(f"{RAW} 안에서 CCTV 엑셀 파일을 찾을 수 없음")
    return files[-1]


def parse_base_date(path):
    m = re.search(r"(\d{2})\D+(\d{1,2})\D+(\d{1,2})\D*기준", path.name)
    if not m:
        raise ValueError(f"파일명에서 기준일을 찾을 수 없음: {path.name}")
    y, mo, d = map(int, m.groups())
    return date(2000 + y, mo, d)


def transform_cctv(raw, dim, base_date):
    # '자치구' 행 = 서울 전체 합계, 그 아래가 25개 구
    marker = raw.index[raw[1].astype(str).str.strip() == "자치구"]
    if len(marker) != 1:
        raise ValueError("'자치구' 합계 행을 찾지 못함")
    seoul_total = int(raw.loc[marker[0], 2])

    body = raw.loc[marker[0] + 1:]
    body = body[pd.to_numeric(body[2], errors="coerce").notna()]   # 각주 행 제거
    df = body[[1] + list(COLS)].rename(columns={1: "gu", **COLS}).copy()
    df["gu"] = df["gu"].astype(str).str.strip()
    df[NUM_COLS] = df[NUM_COLS].astype(int)

    # 구 이름 보정: '동대문' → '동대문구'
    df["sigungu_name"] = df["gu"].where(df["gu"].str.endswith("구"), df["gu"] + "구")

    # ---- 검증 ----
    if len(df) != 25:
        raise ValueError(f"구 개수가 25개가 아님: {len(df)}")
    if df["cctv_total"].sum() != seoul_total:
        raise ValueError(f"25개 구 합계({df['cctv_total'].sum():,}) != 서울 총계({seoul_total:,})")
    sub = df[["cctv_security", "cctv_school_zone", "cctv_park_playground", "cctv_illegal_dumping"]].sum(axis=1)
    if (sub != df["crime_prev_subtotal"]).any():
        raise ValueError("범죄예방 소계가 세부 합과 다른 구가 있음")
    tot = df[["crime_prev_subtotal", "cctv_facility_safety", "cctv_traffic_enforce",
              "cctv_traffic_info", "cctv_other"]].sum(axis=1)
    if (tot != df["cctv_total"]).any():
        raise ValueError("총계가 목적별 합과 다른 구가 있음")

    # ---- 구 코드 붙이기 ----
    df = df.merge(dim, on="sigungu_name", how="left")
    if df["sigungu_code"].isna().any():
        raise ValueError("구 코드 매칭 실패: " + str(df[df["sigungu_code"].isna()]["gu"].tolist()))

    df["base_date"] = base_date
    if df.duplicated(["sigungu_code", "base_date"]).any():
        raise ValueError("fact_cctv 키 중복")
    return df[["sigungu_code", "base_date"] + NUM_COLS]


def load_cctv(engine, df):
    cols = list(df.columns)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in NUM_COLS)
    sql = text(f"""
        INSERT INTO fact_cctv ({", ".join(cols)})
        VALUES ({", ".join(":" + c for c in cols)})
        ON CONFLICT (sigungu_code, base_date) DO UPDATE SET {updates}
    """)
    with engine.begin() as conn:
        conn.execute(sql, df.to_dict("records"))


def main(engine=None):
    engine = engine or get_engine()
    path = find_file()
    raw = pd.read_excel(path, header=None)
    dim = pd.read_sql(text("SELECT DISTINCT sigungu_code, sigungu_name FROM dim_region"), engine)
    if dim.empty:
        raise RuntimeError("dim_region이 비어 있음. 먼저 python -m etl.region 을 실행하세요")

    df = transform_cctv(raw, dim, parse_base_date(path))
    load_cctv(engine, df)
    print("fact_cctv", len(df), "행, 합계", f"{df['cctv_total'].sum():,}", "대")


if __name__ == "__main__":
    main()